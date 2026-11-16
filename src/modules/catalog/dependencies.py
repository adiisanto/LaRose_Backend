from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.catalog.repository import CatalogRepository
from src.modules.catalog.service import CatalogService


def get_catalog_service(db: AsyncSession = Depends(get_db)) -> CatalogService:
    """Provide a CatalogService instance wired with an async database session."""
    return CatalogService(CatalogRepository(db))
