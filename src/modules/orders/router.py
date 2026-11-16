from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.pagination import APIResponse, PaginatedData, PaginationParams
from src.modules.iam.dependencies import get_current_user, require_role
from src.modules.iam.models import User, UserRole
from src.modules.orders.dependencies import get_order_service
from src.modules.orders.models import OrderStatus
from src.modules.orders.schemas import (
    OrderCreate,
    OrderResponse,
)
from src.modules.orders.service import OrderService

router = APIRouter(prefix="/orders", tags=["Order Management"])


@router.post(
    "",
    response_model=APIResponse[OrderResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new customer order with atomic BOM stock reservation",
)
async def create_order(
    payload: OrderCreate,
    service: OrderService = Depends(get_order_service),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[OrderResponse]:
    """Submit customer order and lock inventory atomically (Requires OWNER or ADMIN)."""
    order = await service.create_order(payload, user_id=current_user.id)
    return APIResponse(
        success=True,
        data=order,
        message="Order created and inventory reserved successfully.",
    )


@router.get(
    "",
    response_model=APIResponse[PaginatedData[OrderResponse]],
    summary="List customer orders",
)
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    order_status: OrderStatus | None = Query(None, alias="status", description="Filter by status"),
    service: OrderService = Depends(get_order_service),
    _: User = Depends(get_current_user),
) -> APIResponse[PaginatedData[OrderResponse]]:
    """List orders ordered by delivery_date ASC (Available to all studio roles)."""
    params = PaginationParams(page=page, page_size=page_size)
    paginated = await service.list_orders(params=params, status=order_status)
    return APIResponse(
        success=True,
        data=paginated,
        message="Orders retrieved successfully.",
    )


@router.get(
    "/{order_id}",
    response_model=APIResponse[OrderResponse],
    summary="Get customer order detail",
)
async def get_order_by_id(
    order_id: UUID,
    service: OrderService = Depends(get_order_service),
    _: User = Depends(get_current_user),
) -> APIResponse[OrderResponse]:
    """Retrieve full order details including line items."""
    order = await service.get_order_by_id(order_id)
    return APIResponse(
        success=True,
        data=order,
        message="Order retrieved successfully.",
    )


@router.patch(
    "/{order_id}/payment",
    response_model=APIResponse[OrderResponse],
    summary="Confirm order payment and queue assembly fulfillment task",
)
async def confirm_payment(
    order_id: UUID,
    service: OrderService = Depends(get_order_service),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[OrderResponse]:
    """Confirm payment: transition order to PAID and create assembly task."""
    order = await service.confirm_payment(order_id)
    return APIResponse(
        success=True,
        data=order,
        message="Payment confirmed and assembly task queued successfully.",
    )


@router.patch(
    "/{order_id}/cancel",
    response_model=APIResponse[OrderResponse],
    summary="Cancel order and rollback reserved raw materials",
)
async def cancel_order(
    order_id: UUID,
    service: OrderService = Depends(get_order_service),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[OrderResponse]:
    """Cancel order and release reserved stock back to single items (Requires OWNER or ADMIN)."""
    order = await service.cancel_order(order_id, user_id=current_user.id)
    return APIResponse(
        success=True,
        data=order,
        message="Order cancelled and stock reservation released successfully.",
    )
