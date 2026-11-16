from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.orders.models import AssemblyTask, Order, OrderItem, OrderStatus


class OrderRepository:
    """Data access repository for orders, order items, and assembly fulfillment tasks."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def generate_order_number(self) -> str:
        """Generate unique deterministic studio order number (e.g. ORD-202611-0001)."""
        now = datetime.now(UTC)
        prefix = f"ORD-{now.strftime('%Y%m')}-"

        # Count orders created with this prefix
        query = select(func.count()).select_from(Order).where(Order.order_number.like(f"{prefix}%"))
        count = (await self._db.execute(query)).scalar_one()
        return f"{prefix}{count + 1:04d}"

    async def get_by_id(self, order_id: UUID) -> Order | None:
        """Fetch order by UUID with eager-loaded items and product details."""
        query = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.created_by),
                selectinload(Order.assembly_task),
            )
            .where(Order.id == order_id)
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_order_number(self, order_number: str) -> Order | None:
        """Fetch order by unique order number."""
        query = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.created_by),
                selectinload(Order.assembly_task),
            )
            .where(Order.order_number == order_number)
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        status: OrderStatus | None = None,
        delivery_date: date | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Order], int]:
        """Fetch paginated orders sorted by delivery_date ASC, created_at ASC."""
        base_query = select(Order).options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.created_by),
        )

        if status is not None:
            base_query = base_query.where(Order.status == status)

        if delivery_date is not None:
            base_query = base_query.where(Order.delivery_date == delivery_date)

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self._db.execute(count_query)).scalar_one()

        items_query = (
            base_query.order_by(Order.delivery_date.asc(), Order.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(items_query)
        return list(result.scalars().all()), total

    async def create_order(self, order: Order) -> Order:
        """Persist a new order entity within the active transaction."""
        self._db.add(order)
        await self._db.flush()
        return order

    async def update_order(self, order: Order) -> Order:
        """Save updated order status/fields."""
        order.updated_at = datetime.now(UTC)
        self._db.add(order)
        await self._db.flush()
        return order

    async def create_assembly_task(self, task: AssemblyTask) -> AssemblyTask:
        """Persist a new assembly queue task."""
        self._db.add(task)
        await self._db.flush()
        return task

    async def get_assembly_task_by_order_id(self, order_id: UUID) -> AssemblyTask | None:
        """Fetch assembly task linked to an order."""
        query = select(AssemblyTask).where(AssemblyTask.order_id == order_id)
        result = await self._db.execute(query)
        return result.scalar_one_or_none()
