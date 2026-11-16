from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.catalog.models import BOMComponent, Product, ProductType


class CatalogRepository:
    """Data access repository for products and BOM components."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(
        self,
        product_id: UUID,
        include_inactive: bool = True,
    ) -> Product | None:
        """Fetch a single product by UUID with eager-loaded BOM components and material details."""
        query = (
            select(Product)
            .options(
                selectinload(Product.bom_components).selectinload(BOMComponent.material),
            )
            .where(Product.id == product_id)
        )
        if not include_inactive:
            query = query.where(Product.is_active.is_(True))

        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_sku(self, sku: str) -> Product | None:
        """Fetch a product by unique SKU."""
        query = (
            select(Product)
            .options(
                selectinload(Product.bom_components).selectinload(BOMComponent.material),
            )
            .where(func.upper(Product.sku) == sku.upper())
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_products_by_ids(self, product_ids: list[UUID]) -> list[Product]:
        """Fetch multiple products by IDs."""
        if not product_ids:
            return []
        query = (
            select(Product)
            .options(
                selectinload(Product.bom_components).selectinload(BOMComponent.material),
            )
            .where(Product.id.in_(product_ids))
        )
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def list_products(
        self,
        product_type: ProductType | None = None,
        is_active: bool | None = True,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Product], int]:
        """Fetch a paginated list of products with optional filters."""
        base_query = select(Product)

        if product_type is not None:
            base_query = base_query.where(Product.product_type == product_type)

        if is_active is not None:
            base_query = base_query.where(Product.is_active == is_active)

        if search:
            search_pattern = f"%{search.strip().lower()}%"
            base_query = base_query.where(
                or_(
                    func.lower(Product.name).like(search_pattern),
                    func.lower(Product.sku).like(search_pattern),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self._db.execute(count_query)).scalar_one()

        # Fetch records
        items_query = (
            base_query.options(
                selectinload(Product.bom_components).selectinload(BOMComponent.material),
            )
            .order_by(Product.name.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(items_query)
        items = list(result.scalars().all())

        return items, total

    async def create_product(
        self,
        product: Product,
        bom_components: list[BOMComponent] | None = None,
    ) -> Product:
        """Persist a new product and optional BOM components."""
        self._db.add(product)
        await self._db.flush()

        if bom_components:
            for comp in bom_components:
                comp.bouquet_id = product.id
                self._db.add(comp)
            await self._db.flush()

        await self._db.commit()
        return await self.get_by_id(product.id)  # type: ignore

    async def update_product(
        self,
        product: Product,
        new_bom_components: list[BOMComponent] | None = None,
    ) -> Product:
        """Update existing product fields and replace BOM components if provided."""
        product.updated_at = datetime.now(UTC)
        self._db.add(product)

        if new_bom_components is not None:
            # Delete existing BOM components
            await self._db.execute(
                delete(BOMComponent).where(BOMComponent.bouquet_id == product.id)
            )
            for comp in new_bom_components:
                comp.bouquet_id = product.id
                self._db.add(comp)

        await self._db.commit()
        return await self.get_by_id(product.id)  # type: ignore

    async def soft_delete_product(self, product: Product) -> Product:
        """Perform soft delete by marking is_active=False and setting deleted_at."""
        now = datetime.now(UTC)
        product.is_active = False
        product.deleted_at = now
        product.updated_at = now
        self._db.add(product)
        await self._db.commit()
        return product
