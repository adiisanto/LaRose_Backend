from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.catalog.models import BOMComponent, Product
from src.modules.orders.models import AssemblyTask, Order, OrderItem, TaskStatus


class AssemblyRepository:
    """Data access repository for assembly queue tasks and staff fulfillment."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_queue(
        self,
        status: TaskStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AssemblyTask], int]:
        """Fetch prioritized task queue sorted by delivery_date ASC, created_at ASC."""
        base_query = (
            select(AssemblyTask)
            .join(Order, AssemblyTask.order_id == Order.id)
            .options(
                selectinload(AssemblyTask.order).selectinload(Order.items),
                selectinload(AssemblyTask.assigned_staff),
            )
        )

        if status is not None:
            base_query = base_query.where(AssemblyTask.status == status)
        else:
            base_query = base_query.where(
                AssemblyTask.status.in_([TaskStatus.QUEUED, TaskStatus.IN_PROGRESS])
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self._db.execute(count_query)).scalar_one()

        items_query = (
            base_query.order_by(Order.delivery_date.asc(), Order.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(items_query)
        return list(result.scalars().all()), total

    async def get_by_id(self, task_id: UUID) -> AssemblyTask | None:
        """Fetch task details including full order, products, and BOM components."""
        query = (
            select(AssemblyTask)
            .options(
                selectinload(AssemblyTask.assigned_staff),
                selectinload(AssemblyTask.order)
                .selectinload(Order.items)
                .selectinload(OrderItem.product)
                .selectinload(Product.bom_components)
                .selectinload(BOMComponent.material),
            )
            .where(AssemblyTask.id == task_id)
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def update_task(self, task: AssemblyTask) -> AssemblyTask:
        """Persist task status and timestamp mutations."""
        task.updated_at = datetime.now(UTC)
        self._db.add(task)
        await self._db.flush()
        return task
