from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.catalog.repository import CatalogRepository
from src.modules.inventory.repository import InventoryRepository
from src.modules.inventory.service import InventoryService
from src.modules.orders.repository import OrderRepository
from src.modules.orders.service import OrderService


def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    """Provide an OrderService instance wired with async database session."""
    cat_repo = CatalogRepository(db)
    inv_repo = InventoryRepository(db)
    inv_service = InventoryService(inventory_repo=inv_repo, catalog_repo=cat_repo)
    return OrderService(
        order_repo=OrderRepository(db),
        catalog_repo=cat_repo,
        inventory_service=inv_service,
    )
