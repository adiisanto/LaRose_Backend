from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.pagination import APIResponse, PaginatedData, PaginationParams
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.models import ProductType
from src.modules.catalog.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from src.modules.catalog.service import CatalogService
from src.modules.iam.dependencies import get_current_user, require_role
from src.modules.iam.models import UserRole

router = APIRouter(prefix="/catalog", tags=["Catalog & BOM"])


@router.post(
    "/products",
    response_model=APIResponse[ProductResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new single item or bouquet product",
)
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[ProductResponse]:
    """Create a new catalog item (Requires OWNER or ADMIN role)."""
    product = await service.create_product(payload)
    return APIResponse(
        success=True,
        data=product,
        message="Product created successfully.",
    )


@router.get(
    "/products",
    response_model=APIResponse[PaginatedData[ProductResponse]],
    summary="List products with filtering and pagination",
)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    product_type: ProductType | None = Query(None, description="Filter by product type"),
    is_active: bool | None = Query(True, description="Filter by active status"),
    search: str | None = Query(None, description="Search term for name or SKU"),
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(get_current_user),
) -> APIResponse[PaginatedData[ProductResponse]]:
    """List catalog items (Available for all authenticated studio roles)."""
    params = PaginationParams(page=page, page_size=page_size)
    paginated = await service.list_products(
        params=params,
        product_type=product_type,
        is_active=is_active,
        search=search,
    )
    return APIResponse(
        success=True,
        data=paginated,
        message="Products fetched successfully.",
    )


@router.get(
    "/products/{product_id}",
    response_model=APIResponse[ProductResponse],
    summary="Get product detail by ID",
)
async def get_product_by_id(
    product_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(get_current_user),
) -> APIResponse[ProductResponse]:
    """Get single product details with BOM components if bouquet."""
    product = await service.get_product_by_id(product_id)
    return APIResponse(
        success=True,
        data=product,
        message="Product retrieved successfully.",
    )


@router.get(
    "/products/sku/{sku}",
    response_model=APIResponse[ProductResponse],
    summary="Get product detail by SKU",
)
async def get_product_by_sku(
    sku: str,
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(get_current_user),
) -> APIResponse[ProductResponse]:
    """Get single product details by SKU."""
    product = await service.get_product_by_sku(sku)
    return APIResponse(
        success=True,
        data=product,
        message="Product retrieved successfully.",
    )


@router.put(
    "/products/{product_id}",
    response_model=APIResponse[ProductResponse],
    summary="Update product details or BOM recipe",
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[ProductResponse]:
    """Update product details or replace BOM components (Requires OWNER or ADMIN role)."""
    product = await service.update_product(product_id, payload)
    return APIResponse(
        success=True,
        data=product,
        message="Product updated successfully.",
    )


@router.delete(
    "/products/{product_id}",
    response_model=APIResponse[ProductResponse],
    summary="Soft delete a product",
)
async def delete_product(
    product_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
    _: None = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
) -> APIResponse[ProductResponse]:
    """Soft delete a product (Requires OWNER or ADMIN role)."""
    product = await service.delete_product(product_id)
    return APIResponse(
        success=True,
        data=product,
        message="Product deleted successfully.",
    )
