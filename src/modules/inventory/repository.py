from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.inventory.models import Inventory, StockMovement


class InventoryRepository:
    """Repository handling inventory queries, locking engine, and ledger records."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_product_id(self, product_id: UUID) -> Inventory | None:
        """Fetch inventory balance record for a single product."""
        query = (
            select(Inventory)
            .options(selectinload(Inventory.product))
            .where(Inventory.product_id == product_id)
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(self, product_id: UUID, reorder_point: int = 10) -> Inventory:
        """Fetch existing inventory or initialize a zero-balance record."""
        existing = await self.get_by_product_id(product_id)
        if existing:
            return existing

        inv = Inventory(
            product_id=product_id,
            quantity_on_hand=0,
            quantity_reserved=0,
            reorder_point=reorder_point,
        )
        self._db.add(inv)
        await self._db.flush()
        return await self.get_by_product_id(product_id)  # type: ignore

    async def get_locked_inventories(self, sorted_product_ids: list[UUID]) -> list[Inventory]:
        """Lock inventory rows via SELECT ... FOR UPDATE sorted by product_id."""
        if not sorted_product_ids:
            return []

        # Order deterministically to prevent deadlocks across concurrent sessions
        query = (
            select(Inventory)
            .options(selectinload(Inventory.product))
            .where(Inventory.product_id.in_(sorted_product_ids))
            .with_for_update()
            .order_by(Inventory.product_id.asc())
        )
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def list_inventories(
        self,
        is_low_stock: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Inventory], int]:
        """Fetch paginated inventory balances with optional low-stock filter."""
        base_query = select(Inventory).options(selectinload(Inventory.product))

        if is_low_stock is True:
            # Low stock: quantity_on_hand - quantity_reserved <= reorder_point
            base_query = base_query.where(
                (Inventory.quantity_on_hand - Inventory.quantity_reserved)
                <= Inventory.reorder_point
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self._db.execute(count_query)).scalar_one()

        items_query = base_query.order_by(Inventory.product_id.asc()).offset(offset).limit(limit)
        result = await self._db.execute(items_query)
        return list(result.scalars().all()), total

    async def record_movement(self, movement: StockMovement) -> StockMovement:
        """Append an immutable mutation record to the stock movements ledger."""
        self._db.add(movement)
        await self._db.flush()
        return movement

    async def list_movements(
        self,
        inventory_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[StockMovement], int]:
        """Fetch paginated stock movement audit trail for an inventory item."""
        base_query = (
            select(StockMovement)
            .options(selectinload(StockMovement.created_by))
            .where(StockMovement.inventory_id == inventory_id)
        )
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self._db.execute(count_query)).scalar_one()

        items_query = (
            base_query.order_by(StockMovement.created_at.desc()).offset(offset).limit(limit)
        )
        result = await self._db.execute(items_query)
        return list(result.scalars().all()), total
