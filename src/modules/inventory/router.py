from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.pagination import APIResponse, PaginatedData, PaginationParams
from src.modules.iam.dependencies import get_current_user, require_role
from src.modules.iam.models import User, UserRole
from src.modules.inventory.dependencies import get_inventory_service
from src.modules.inventory.schemas import (
    InventoryResponse,
    RestockInput,
    StockMovementResponse,
)
from src.modules.inventory.service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventory Management"])


@router.post(
    "/restock",
    response_model=APIResponse[InventoryResponse],
    status_code=status.HTTP_200_OK,
    summary="Record inbound physical restock",
)
async def restock(
    payload: RestockInput,
    service: InventoryService = Depends(get_inventory_service),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[InventoryResponse]:
    """Record physical inbound delivery and append ledger mutation (Requires OWNER or ADMIN)."""
    inv = await service.restock(payload, user_id=current_user.id)
    return APIResponse(
        success=True,
        data=inv,
        message="Stock restocked successfully.",
    )


@router.get(
    "",
    response_model=APIResponse[PaginatedData[InventoryResponse]],
    summary="List inventory balances and alerts",
)
async def list_inventories(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    is_low_stock: bool | None = Query(None, description="Filter low stock items only"),
    service: InventoryService = Depends(get_inventory_service),
    _: User = Depends(get_current_user),
) -> APIResponse[PaginatedData[InventoryResponse]]:
    """List inventory balances across products with available quantities and alert states."""
    params = PaginationParams(page=page, page_size=page_size)
    paginated = await service.list_inventories(params=params, is_low_stock=is_low_stock)
    return APIResponse(
        success=True,
        data=paginated,
        message="Inventory balances retrieved successfully.",
    )


@router.get(
    "/{product_id}",
    response_model=APIResponse[InventoryResponse],
    summary="Get inventory balance for a product",
)
async def get_inventory(
    product_id: UUID,
    service: InventoryService = Depends(get_inventory_service),
    _: User = Depends(get_current_user),
) -> APIResponse[InventoryResponse]:
    """Retrieve detailed inventory balance by product UUID."""
    inv = await service.get_by_product_id(product_id)
    return APIResponse(
        success=True,
        data=inv,
        message="Inventory retrieved successfully.",
    )


@router.get(
    "/{product_id}/movements",
    response_model=APIResponse[PaginatedData[StockMovementResponse]],
    summary="Get stock movement audit history for a product",
)
async def list_movements(
    product_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: InventoryService = Depends(get_inventory_service),
    _: User = Depends(get_current_user),
) -> APIResponse[PaginatedData[StockMovementResponse]]:
    """Retrieve paginated immutable audit log of stock movements for a product."""
    params = PaginationParams(page=page, page_size=page_size)
    paginated = await service.list_movements(product_id=product_id, params=params)
    return APIResponse(
        success=True,
        data=paginated,
        message="Stock movements retrieved successfully.",
    )
