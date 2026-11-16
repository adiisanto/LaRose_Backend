from datetime import UTC, datetime
from uuid import UUID

from src.core.exceptions import InsufficientStockException, ResourceNotFoundException
from src.core.pagination import PaginatedData, PaginationParams
from src.modules.catalog.repository import CatalogRepository
from src.modules.inventory.models import Inventory, MovementType, StockMovement
from src.modules.inventory.repository import InventoryRepository
from src.modules.inventory.schemas import (
    InventoryResponse,
    RestockInput,
    StockMovementResponse,
)


class InventoryService:
    """Service orchestrating stock balances, locking transactions, and audit records."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        catalog_repo: CatalogRepository,
    ) -> None:
        self._inv_repo = inventory_repo
        self._cat_repo = catalog_repo

    def _to_response_dto(self, inv: Inventory) -> InventoryResponse:
        available = inv.quantity_on_hand - inv.quantity_reserved
        return InventoryResponse(
            id=inv.id,
            product_id=inv.product_id,
            product_sku=inv.product.sku if inv.product else "",
            product_name=inv.product.name if inv.product else "",
            storage_bin=inv.product.storage_bin if inv.product else None,
            quantity_on_hand=inv.quantity_on_hand,
            quantity_reserved=inv.quantity_reserved,
            quantity_available=available,
            reorder_point=inv.reorder_point,
            is_low_stock=available <= inv.reorder_point,
            updated_at=inv.updated_at,
        )

    def _to_movement_dto(self, movement: StockMovement) -> StockMovementResponse:
        return StockMovementResponse(
            id=movement.id,
            inventory_id=movement.inventory_id,
            movement_type=movement.movement_type,
            delta_quantity=movement.delta_quantity,
            reference_id=movement.reference_id,
            notes=movement.notes,
            created_by_username=movement.created_by.username if movement.created_by else None,
            created_at=movement.created_at,
        )

    async def restock(
        self,
        dto: RestockInput,
        user_id: UUID | None = None,
    ) -> InventoryResponse:
        """Add physical inventory for a single material product and append ledger entry."""
        product = await self._cat_repo.get_by_id(dto.product_id)
        if not product:
            raise ResourceNotFoundException("Product", dto.product_id)

        inv = await self._inv_repo.get_or_create(dto.product_id)
        inv.quantity_on_hand += dto.quantity
        inv.updated_at = datetime.now(UTC)

        movement = StockMovement(
            inventory_id=inv.id,
            movement_type=MovementType.INBOUND_RESTOCK,
            delta_quantity=dto.quantity,
            reference_id=dto.reference_id,
            notes=dto.notes,
            created_by_user_id=user_id,
        )
        await self._inv_repo.record_movement(movement)
        await self._inv_repo._db.commit()

        reloaded = await self._inv_repo.get_by_product_id(dto.product_id)
        return self._to_response_dto(reloaded)  # type: ignore

    async def reserve_stock_atomic(
        self,
        requirements: dict[UUID, int],
        reference_id: str,
        user_id: UUID | None = None,
    ) -> None:
        """Lock required material rows deterministically and reserve quantities."""
        if not requirements:
            return

        sorted_ids = sorted(requirements.keys())
        locked_inventories = await self._inv_repo.get_locked_inventories(sorted_ids)
        inv_by_product = {inv.product_id: inv for inv in locked_inventories}

        # Check for missing inventory records or insufficient stock
        shortages: list[dict[str, object]] = []
        for pid, needed in requirements.items():
            inv = inv_by_product.get(pid)
            if not inv:
                # If no inventory record exists yet, available is 0
                shortages.append(
                    {
                        "productId": str(pid),
                        "available": 0,
                        "required": needed,
                    }
                )
                continue

            available = inv.quantity_on_hand - inv.quantity_reserved
            if available < needed:
                shortages.append(
                    {
                        "productId": str(pid),
                        "productName": inv.product.name if inv.product else "",
                        "productSku": inv.product.sku if inv.product else "",
                        "available": available,
                        "required": needed,
                    }
                )

        if shortages:
            raise InsufficientStockException(
                details=shortages,
                message="Cannot fulfill order: insufficient inventory for required materials.",
            )

        # Allocate reservations
        now = datetime.now(UTC)
        for pid, needed in requirements.items():
            inv = inv_by_product[pid]
            inv.quantity_reserved += needed
            inv.updated_at = now

    async def release_stock_atomic(
        self,
        requirements: dict[UUID, int],
        reference_id: str,
        user_id: UUID | None = None,
    ) -> None:
        """Release previously reserved inventory allocations upon order cancellation."""
        if not requirements:
            return

        sorted_ids = sorted(requirements.keys())
        locked_inventories = await self._inv_repo.get_locked_inventories(sorted_ids)
        now = datetime.now(UTC)
        for inv in locked_inventories:
            qty_to_release = requirements.get(inv.product_id, 0)
            if qty_to_release > 0:
                inv.quantity_reserved = max(0, inv.quantity_reserved - qty_to_release)
                inv.updated_at = now

    async def get_by_product_id(self, product_id: UUID) -> InventoryResponse:
        """Retrieve inventory record by product UUID."""
        inv = await self._inv_repo.get_by_product_id(product_id)
        if not inv:
            raise ResourceNotFoundException("Inventory for product", product_id)
        return self._to_response_dto(inv)

    async def list_inventories(
        self,
        params: PaginationParams,
        is_low_stock: bool | None = None,
    ) -> PaginatedData[InventoryResponse]:
        """Retrieve paginated inventory balances."""
        items, total = await self._inv_repo.list_inventories(
            is_low_stock=is_low_stock,
            offset=params.offset,
            limit=params.page_size,
        )
        dtos = [self._to_response_dto(i) for i in items]
        return PaginatedData.create(items=dtos, total=total, params=params)

    async def list_movements(
        self,
        product_id: UUID,
        params: PaginationParams,
    ) -> PaginatedData[StockMovementResponse]:
        """Retrieve paginated movement audit trail for a product."""
        inv = await self._inv_repo.get_by_product_id(product_id)
        if not inv:
            raise ResourceNotFoundException("Inventory for product", product_id)

        items, total = await self._inv_repo.list_movements(
            inventory_id=inv.id,
            offset=params.offset,
            limit=params.page_size,
        )
        dtos = [self._to_movement_dto(m) for m in items]
        return PaginatedData.create(items=dtos, total=total, params=params)
