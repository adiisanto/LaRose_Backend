from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from src.core.exceptions import AppException, InsufficientStockException, ResourceNotFoundException
from src.core.pagination import PaginatedData, PaginationParams
from src.modules.assembly.repository import AssemblyRepository
from src.modules.assembly.schemas import (
    AssemblyTaskDetailResponse,
    AssemblyTaskQueueItem,
    RequiredMaterialItem,
    ScrapReportInput,
)
from src.modules.catalog.models import Product, ProductType
from src.modules.inventory.models import MovementType, StockMovement
from src.modules.inventory.repository import InventoryRepository
from src.modules.orders.models import AssemblyTask, OrderStatus, TaskStatus
from src.modules.orders.repository import OrderRepository


class AssemblyService:
    """Service handling tablet packing queue, state transitions, and scrap reporting."""

    def __init__(
        self,
        assembly_repo: AssemblyRepository,
        inventory_repo: InventoryRepository,
        order_repo: OrderRepository,
    ) -> None:
        self._assembly_repo = assembly_repo
        self._inv_repo = inventory_repo
        self._order_repo = order_repo

    def _extract_material_checklist(
        self,
        task: AssemblyTask,
    ) -> tuple[list[RequiredMaterialItem], dict[UUID, int]]:
        """Extract and aggregate required materials from BOM recipes for the order."""
        requirements_qty: dict[UUID, int] = defaultdict(int)
        materials_meta: dict[UUID, Product] = {}

        for item in task.order.items:
            product = item.product
            if product.product_type == ProductType.SINGLE_ITEM:
                requirements_qty[product.id] += item.quantity
                materials_meta[product.id] = product
            elif product.product_type == ProductType.BOUQUET_ARRANGEMENT:
                for comp in product.bom_components:
                    requirements_qty[comp.material_id] += comp.quantity_required * item.quantity
                    materials_meta[comp.material_id] = comp.material

        checklist = [
            RequiredMaterialItem(
                material_id=mid,
                material_name=materials_meta[mid].name,
                material_sku=materials_meta[mid].sku,
                storage_bin=materials_meta[mid].storage_bin,
                quantity_required=qty,
            )
            for mid, qty in requirements_qty.items()
        ]
        return checklist, dict(requirements_qty)

    def _to_detail_dto(self, task: AssemblyTask) -> AssemblyTaskDetailResponse:
        checklist, _ = self._extract_material_checklist(task)
        return AssemblyTaskDetailResponse(
            id=task.id,
            order_id=task.order_id,
            order_number=task.order.order_number,
            customer_name=task.order.customer_name,
            delivery_date=task.order.delivery_date,
            status=task.status,
            assigned_staff_id=task.assigned_staff_id,
            assigned_staff_name=task.assigned_staff.full_name if task.assigned_staff else None,
            custom_instructions=task.custom_instructions,
            required_materials=checklist,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
        )

    async def list_queue(
        self,
        params: PaginationParams,
        status: TaskStatus | None = None,
    ) -> PaginatedData[AssemblyTaskQueueItem]:
        """Fetch prioritized task queue sorted by delivery_date ASC."""
        items, total = await self._assembly_repo.list_queue(
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
        dtos = [
            AssemblyTaskQueueItem(
                id=t.id,
                order_id=t.order_id,
                order_number=t.order.order_number,
                customer_name=t.order.customer_name,
                delivery_date=t.order.delivery_date,
                status=t.status,
                assigned_staff_name=t.assigned_staff.full_name if t.assigned_staff else None,
                custom_instructions=t.custom_instructions,
                item_count=len(t.order.items),
                created_at=t.created_at,
                started_at=t.started_at,
            )
            for t in items
        ]
        return PaginatedData.create(items=dtos, total=total, params=params)

    async def get_by_id(self, task_id: UUID) -> AssemblyTaskDetailResponse:
        """Fetch full assembly task detail and material checklist."""
        task = await self._assembly_repo.get_by_id(task_id)
        if not task:
            raise ResourceNotFoundException("AssemblyTask", task_id)
        return self._to_detail_dto(task)

    async def start_assembly(
        self,
        task_id: UUID,
        staff_user_id: UUID,
    ) -> AssemblyTaskDetailResponse:
        """Staff claims a queued task to begin arrangement work."""
        task = await self._assembly_repo.get_by_id(task_id)
        if not task:
            raise ResourceNotFoundException("AssemblyTask", task_id)

        if task.status != TaskStatus.QUEUED:
            raise AppException(
                status_code=400,
                code="INVALID_TASK_STATE",
                message=f"Cannot start task with status '{task.status}'. Must be 'QUEUED'.",
            )

        now = datetime.now(UTC)
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_staff_id = staff_user_id
        task.started_at = now

        task.order.status = OrderStatus.PROCESSING
        task.order.updated_at = now

        await self._assembly_repo.update_task(task)
        await self._assembly_repo._db.commit()

        reloaded = await self._assembly_repo.get_by_id(task_id)
        return self._to_detail_dto(reloaded)  # type: ignore

    async def finish_assembly(self, task_id: UUID) -> AssemblyTaskDetailResponse:
        """Complete assembly: deduct physical inventory and advance order to READY_FOR_DELIVERY."""
        task = await self._assembly_repo.get_by_id(task_id)
        if not task:
            raise ResourceNotFoundException("AssemblyTask", task_id)

        if task.status != TaskStatus.IN_PROGRESS:
            raise AppException(
                status_code=400,
                code="INVALID_TASK_STATE",
                message=f"Cannot finish task with status '{task.status}'. Must be 'IN_PROGRESS'.",
            )

        _, requirements_qty = self._extract_material_checklist(task)
        sorted_ids = sorted(requirements_qty.keys())
        locked_inventories = await self._inv_repo.get_locked_inventories(sorted_ids)

        now = datetime.now(UTC)
        for inv in locked_inventories:
            needed = requirements_qty[inv.product_id]
            inv.quantity_on_hand -= needed
            inv.quantity_reserved -= needed
            inv.updated_at = now

            movement = StockMovement(
                inventory_id=inv.id,
                movement_type=MovementType.ASSEMBLY_DEDUCTED,
                delta_quantity=-needed,
                reference_id=task.order.order_number,
                created_by_user_id=task.assigned_staff_id,
            )
            await self._inv_repo.record_movement(movement)

        task.status = TaskStatus.PACKED
        task.completed_at = now

        task.order.status = OrderStatus.READY_FOR_DELIVERY
        task.order.updated_at = now

        await self._assembly_repo.update_task(task)
        await self._assembly_repo._db.commit()

        reloaded = await self._assembly_repo.get_by_id(task_id)
        return self._to_detail_dto(reloaded)  # type: ignore

    async def report_scrap(
        self,
        task_id: UUID,
        dto: ScrapReportInput,
        staff_user_id: UUID,
    ) -> AssemblyTaskDetailResponse:
        """Report damaged material, deduct scrap, and reserve replacement atomically."""
        task = await self._assembly_repo.get_by_id(task_id)
        if not task:
            raise ResourceNotFoundException("AssemblyTask", task_id)

        if task.status != TaskStatus.IN_PROGRESS:
            raise AppException(
                status_code=400,
                code="INVALID_TASK_STATE",
                message=(
                    f"Cannot report scrap on task with status '{task.status}'. "
                    "Must be 'IN_PROGRESS'."
                ),
            )

        _, requirements_qty = self._extract_material_checklist(task)
        if dto.material_id not in requirements_qty:
            raise AppException(
                status_code=400,
                code="INVALID_SCRAP_MATERIAL",
                message="Reported damaged material is not part of this bouquet arrangement recipe.",
            )

        # Lock inventory of the damaged material
        locked = await self._inv_repo.get_locked_inventories([dto.material_id])
        if not locked:
            raise ResourceNotFoundException("Inventory for material", dto.material_id)

        inv = locked[0]
        available = inv.quantity_on_hand - inv.quantity_reserved
        if available < dto.quantity:
            raise InsufficientStockException(
                details=[
                    {
                        "productId": str(inv.product_id),
                        "productName": inv.product.name if inv.product else "",
                        "available": available,
                        "required": dto.quantity,
                    }
                ],
                message="Insufficient free stock in studio inventory to allocate replacement.",
            )

        now = datetime.now(UTC)
        # 1. Deduct damaged item from physical inventory
        inv.quantity_on_hand -= dto.quantity
        inv.updated_at = now

        movement = StockMovement(
            inventory_id=inv.id,
            movement_type=MovementType.SCRAP_DAMAGED,
            delta_quantity=-dto.quantity,
            reference_id=task.order.order_number,
            notes=dto.reason or "Reported scrap during assembly",
            created_by_user_id=staff_user_id,
        )
        await self._inv_repo.record_movement(movement)

        # 2. Reserve replacement item for this order
        inv.quantity_reserved += dto.quantity

        await self._inv_repo._db.commit()

        reloaded = await self._assembly_repo.get_by_id(task_id)
        return self._to_detail_dto(reloaded)  # type: ignore
