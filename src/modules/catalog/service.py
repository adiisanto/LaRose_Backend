from uuid import UUID

from src.core.exceptions import AppException, ResourceNotFoundException
from src.core.pagination import PaginatedData, PaginationParams
from src.modules.catalog.models import BOMComponent, Product, ProductType
from src.modules.catalog.repository import CatalogRepository
from src.modules.catalog.schemas import (
    BOMComponentItem,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)


class CatalogService:
    """Business logic service for catalog products and BOM recipes."""

    def __init__(self, repository: CatalogRepository) -> None:
        self._repo = repository

    def _to_response_dto(self, product: Product) -> ProductResponse:
        """Convert a Product ORM model to a ProductResponse DTO."""
        bom_items: list[BOMComponentItem] | None = None
        if product.product_type == ProductType.BOUQUET_ARRANGEMENT and product.bom_components:
            bom_items = [
                BOMComponentItem(
                    material_id=comp.material_id,
                    material_name=comp.material.name if comp.material else None,
                    material_sku=comp.material.sku if comp.material else None,
                    storage_bin=comp.material.storage_bin if comp.material else None,
                    quantity_required=comp.quantity_required,
                )
                for comp in product.bom_components
            ]

        return ProductResponse(
            id=product.id,
            sku=product.sku,
            name=product.name,
            description=product.description,
            product_type=product.product_type,
            price=product.price,
            storage_bin=product.storage_bin,
            is_premade=product.is_premade,
            is_active=product.is_active,
            available_stock=None,
            bom_components=bom_items,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    async def _validate_bom_components(
        self,
        bouquet_id: UUID | None,
        components: list[BOMComponentItem],
    ) -> list[BOMComponent]:
        """Validate BOM items against business constraints (anti-looping, single item only)."""
        if not components:
            return []

        # Check for duplicates in input
        material_ids = [c.material_id for c in components]
        if len(material_ids) != len(set(material_ids)):
            raise AppException(
                status_code=400,
                code="DUPLICATE_BOM_COMPONENT",
                message="Duplicate raw materials detected in BOM components list.",
            )

        # Check self-reference
        if bouquet_id is not None and bouquet_id in material_ids:
            raise AppException(
                status_code=400,
                code="SELF_REFERENCING_BOM",
                message="A bouquet cannot include itself as a component material.",
            )

        # Fetch materials from repository
        materials = await self._repo.get_products_by_ids(material_ids)
        materials_by_id = {m.id: m for m in materials}

        # Check all materials exist
        missing_ids = set(material_ids) - set(materials_by_id.keys())
        if missing_ids:
            raise AppException(
                status_code=400,
                code="MATERIAL_NOT_FOUND",
                message=f"Material IDs {list(missing_ids)} do not exist in catalog.",
            )

        validated_components: list[BOMComponent] = []
        for c in components:
            mat = materials_by_id[c.material_id]
            if mat.product_type != ProductType.SINGLE_ITEM:
                raise AppException(
                    status_code=400,
                    code="INVALID_BOM_MATERIAL_TYPE",
                    message=(
                        f"Component '{mat.name}' ({mat.sku}) is a bouquet. "
                        "Only SINGLE_ITEM materials can be used in BOM recipes."
                    ),
                )
            if not mat.is_active:
                raise AppException(
                    status_code=400,
                    code="INACTIVE_BOM_MATERIAL",
                    message=(
                        f"Component '{mat.name}' ({mat.sku}) is inactive "
                        "and cannot be added to a recipe."
                    ),
                )
            if c.quantity_required <= 0:
                raise AppException(
                    status_code=400,
                    code="INVALID_QUANTITY",
                    message=f"Quantity required for '{mat.name}' must be greater than 0.",
                )

            validated_components.append(
                BOMComponent(
                    material_id=c.material_id,
                    quantity_required=c.quantity_required,
                )
            )

        return validated_components

    async def create_product(self, dto: ProductCreate) -> ProductResponse:
        """Create a new product (single material or bouquet arrangement)."""
        existing = await self._repo.get_by_sku(dto.sku)
        if existing:
            raise AppException(
                status_code=409,
                code="SKU_ALREADY_EXISTS",
                message=f"Product with SKU '{dto.sku}' already exists.",
            )

        if dto.product_type == ProductType.SINGLE_ITEM and dto.bom_components:
            raise AppException(
                status_code=400,
                code="INVALID_BOM_ASSIGNMENT",
                message="Single item products cannot have BOM components.",
            )

        bom_models: list[BOMComponent] | None = None
        if dto.product_type == ProductType.BOUQUET_ARRANGEMENT and dto.bom_components:
            bom_models = await self._validate_bom_components(None, dto.bom_components)

        product = Product(
            sku=dto.sku,
            name=dto.name,
            description=dto.description,
            product_type=dto.product_type,
            price=dto.price,
            storage_bin=dto.storage_bin,
            is_premade=dto.is_premade,
        )

        created = await self._repo.create_product(product, bom_models)
        return self._to_response_dto(created)

    async def get_product_by_id(self, product_id: UUID) -> ProductResponse:
        """Retrieve a product by its unique UUID."""
        product = await self._repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)
        return self._to_response_dto(product)

    async def get_product_by_sku(self, sku: str) -> ProductResponse:
        """Retrieve a product by its SKU."""
        product = await self._repo.get_by_sku(sku)
        if not product:
            raise ResourceNotFoundException("Product", sku)
        return self._to_response_dto(product)

    async def list_products(
        self,
        params: PaginationParams,
        product_type: ProductType | None = None,
        is_active: bool | None = True,
        search: str | None = None,
    ) -> PaginatedData[ProductResponse]:
        """Retrieve a paginated list of products."""
        items, total = await self._repo.list_products(
            product_type=product_type,
            is_active=is_active,
            search=search,
            offset=params.offset,
            limit=params.page_size,
        )
        dtos = [self._to_response_dto(p) for p in items]
        return PaginatedData.create(items=dtos, total=total, params=params)

    async def update_product(self, product_id: UUID, dto: ProductUpdate) -> ProductResponse:
        """Update product metadata or replace its BOM recipe."""
        product = await self._repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        if dto.name is not None:
            product.name = dto.name
        if dto.description is not None:
            product.description = dto.description
        if dto.price is not None:
            product.price = dto.price
        if dto.storage_bin is not None:
            product.storage_bin = dto.storage_bin
        if dto.is_premade is not None:
            product.is_premade = dto.is_premade
        if dto.is_active is not None:
            product.is_active = dto.is_active

        bom_models: list[BOMComponent] | None = None
        if dto.bom_components is not None:
            if product.product_type != ProductType.BOUQUET_ARRANGEMENT:
                raise AppException(
                    status_code=400,
                    code="INVALID_BOM_ASSIGNMENT",
                    message="Cannot assign BOM components to a SINGLE_ITEM product.",
                )
            bom_models = await self._validate_bom_components(product.id, dto.bom_components)

        updated = await self._repo.update_product(product, bom_models)
        return self._to_response_dto(updated)

    async def delete_product(self, product_id: UUID) -> ProductResponse:
        """Soft-delete a product by setting is_active=False."""
        product = await self._repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        deleted = await self._repo.soft_delete_product(product)
        return self._to_response_dto(deleted)
