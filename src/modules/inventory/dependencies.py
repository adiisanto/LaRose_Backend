from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.catalog.repository import CatalogRepository
from src.modules.inventory.repository import InventoryRepository
from src.modules.inventory.service import InventoryService


def get_inventory_service(db: AsyncSession = Depends(get_db)) -> InventoryService:
    """Provide an InventoryService instance wired with async database session."""
    return InventoryService(
        inventory_repo=InventoryRepository(db),
        catalog_repo=CatalogRepository(db),
    )
