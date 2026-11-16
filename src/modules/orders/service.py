from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from src.core.exceptions import AppException, ResourceNotFoundException
from src.core.pagination import PaginatedData, PaginationParams
from src.modules.catalog.models import ProductType
from src.modules.catalog.repository import CatalogRepository
from src.modules.inventory.service import InventoryService
from src.modules.orders.models import AssemblyTask, Order, OrderItem, OrderStatus, TaskStatus
from src.modules.orders.repository import OrderRepository
from src.modules.orders.schemas import (
    OrderCreate,
    OrderItemResponse,
    OrderResponse,
)


class OrderService:
    """Service orchestrating order intake, BOM expansion, stock reservation, and payment FSM."""

    def __init__(
        self,
        order_repo: OrderRepository,
        catalog_repo: CatalogRepository,
        inventory_service: InventoryService,
    ) -> None:
        self._order_repo = order_repo
        self._cat_repo = catalog_repo
        self._inv_service = inventory_service

    def _to_response_dto(self, order: Order) -> OrderResponse:
        items = [
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.sku if item.product else "",
                product_name=item.product.name if item.product else "",
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
            )
            for item in order.items
        ]
        return OrderResponse(
            id=order.id,
            order_number=order.order_number,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            customer_address=order.customer_address,
            delivery_date=order.delivery_date,
            status=order.status,
            total_amount=order.total_amount,
            greeting_card_notes=order.greeting_card_notes,
            internal_notes=order.internal_notes,
            items=items,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    def _expand_material_requirements(
        self,
        items: list[OrderItem],
        products_by_id: dict[UUID, object],
    ) -> dict[UUID, int]:
        """Expand ordered products into atomic single material requirements via BOM recipes."""
        requirements: dict[UUID, int] = defaultdict(int)

        for item in items:
            product: any = products_by_id[item.product_id]
            if product.product_type == ProductType.SINGLE_ITEM:
                requirements[product.id] += item.quantity
            elif product.product_type == ProductType.BOUQUET_ARRANGEMENT:
                if not product.bom_components:
                    raise AppException(
                        status_code=400,
                        code="EMPTY_BOM_RECIPE",
                        message=f"Bouquet '{product.name}' has no BOM recipe configured.",
                    )
                for comp in product.bom_components:
                    requirements[comp.material_id] += comp.quantity_required * item.quantity

        return dict(requirements)

    async def create_order(
        self,
        dto: OrderCreate,
        user_id: UUID | None = None,
    ) -> OrderResponse:
        """Create a new order, expand BOM recipes, and lock stock deterministically."""
        # 1. Fetch and validate all ordered products
        product_ids = [item.product_id for item in dto.items]
        products = await self._cat_repo.get_products_by_ids(product_ids)
        products_by_id = {p.id: p for p in products}

        missing_ids = set(product_ids) - set(products_by_id.keys())
        if missing_ids:
            raise AppException(
                status_code=400,
                code="PRODUCT_NOT_FOUND",
                message=f"Product IDs {list(missing_ids)} do not exist in catalog.",
            )

        for p in products:
            if not p.is_active:
                raise AppException(
                    status_code=400,
                    code="INACTIVE_PRODUCT",
                    message=f"Product '{p.name}' is inactive and cannot be ordered.",
                )

        # 2. Build order items & calculate financial subtotal
        order_items: list[OrderItem] = []
        total_amount = Decimal("0.00")

        for item_dto in dto.items:
            product = products_by_id[item_dto.product_id]
            subtotal = Decimal(str(item_dto.quantity)) * product.price
            total_amount += subtotal

            order_items.append(
                OrderItem(
                    product_id=item_dto.product_id,
                    quantity=item_dto.quantity,
                    unit_price=product.price,
                    subtotal=subtotal,
                )
            )

        # 3. Expand BOM and compute raw material requirements
        material_requirements = self._expand_material_requirements(order_items, products_by_id)

        # 4. Generate order number
        order_number = await self._order_repo.generate_order_number()

        # 5. Pessimistic Locking & Atomic Reservation
        # This executes SELECT ... FOR UPDATE ordered by product_id ASC in the active transaction
        await self._inv_service.reserve_stock_atomic(
            requirements=material_requirements,
            reference_id=order_number,
            user_id=user_id,
        )

        # 6. Save Order
        order = Order(
            order_number=order_number,
            customer_name=dto.customer_name,
            customer_phone=dto.customer_phone,
            customer_address=dto.customer_address,
            delivery_date=dto.delivery_date,
            status=OrderStatus.PENDING_PAYMENT,
            total_amount=total_amount,
            greeting_card_notes=dto.greeting_card_notes,
            internal_notes=dto.internal_notes,
            created_by_user_id=user_id,
            items=order_items,
        )

        await self._order_repo.create_order(order)
        await self._order_repo._db.commit()

        reloaded = await self._order_repo.get_by_id(order.id)
        return self._to_response_dto(reloaded)  # type: ignore

    async def confirm_payment(self, order_id: UUID) -> OrderResponse:
        """Confirm customer payment: transition order to PAID and create assembly task."""
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        if order.status != OrderStatus.PENDING_PAYMENT:
            raise AppException(
                status_code=400,
                code="INVALID_STATE_TRANSITION",
                message=f"Order cannot be confirmed. Current status: '{order.status}'.",
            )

        order.status = OrderStatus.PAID
        await self._order_repo.update_order(order)

        # Create Assembly Task
        task = AssemblyTask(
            order_id=order.id,
            status=TaskStatus.QUEUED,
            custom_instructions=order.greeting_card_notes,
        )
        await self._order_repo.create_assembly_task(task)
        await self._order_repo._db.commit()

        reloaded = await self._order_repo.get_by_id(order.id)
        return self._to_response_dto(reloaded)  # type: ignore

    async def cancel_order(
        self,
        order_id: UUID,
        user_id: UUID | None = None,
    ) -> OrderResponse:
        """Cancel order and release reserved single materials back to inventory."""
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise AppException(
                status_code=400,
                code="ORDER_NOT_CANCELLABLE",
                message=f"Order with status '{order.status}' cannot be cancelled.",
            )

        # Expand BOM to calculate component materials
        products_by_id = {item.product.id: item.product for item in order.items}
        material_requirements = self._expand_material_requirements(order.items, products_by_id)

        if order.status == OrderStatus.READY_FOR_DELIVERY:
            # Physical items were deducted during finish_assembly -> return them via disassembly
            await self._inv_service.disassemble_stock_atomic(
                requirements=material_requirements,
                reference_id=order.order_number,
                user_id=user_id,
            )
        else:
            # Order was PENDING_PAYMENT, PAID, or PROCESSING -> release reservation
            await self._inv_service.release_stock_atomic(
                requirements=material_requirements,
                reference_id=order.order_number,
                user_id=user_id,
            )

        order.status = OrderStatus.CANCELLED
        await self._order_repo.update_order(order)

        # Update assembly task if exists
        task = await self._order_repo.get_assembly_task_by_order_id(order.id)
        if task:
            task.status = TaskStatus.CANCELLED
            self._order_repo._db.add(task)

        await self._order_repo._db.commit()

        reloaded = await self._order_repo.get_by_id(order.id)
        return self._to_response_dto(reloaded)  # type: ignore

    async def get_order_by_id(self, order_id: UUID) -> OrderResponse:
        """Fetch order details by UUID."""
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)
        return self._to_response_dto(order)

    async def list_orders(
        self,
        params: PaginationParams,
        status: OrderStatus | None = None,
    ) -> PaginatedData[OrderResponse]:
        """Fetch paginated orders."""
        items, total = await self._order_repo.list_orders(
            status=status,
            offset=params.offset,
            limit=params.page_size,
        )
        dtos = [self._to_response_dto(o) for o in items]
        return PaginatedData.create(items=dtos, total=total, params=params)
