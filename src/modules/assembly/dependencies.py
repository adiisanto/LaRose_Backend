from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.assembly.repository import AssemblyRepository
from src.modules.assembly.service import AssemblyService
from src.modules.inventory.repository import InventoryRepository
from src.modules.orders.repository import OrderRepository


def get_assembly_service(db: AsyncSession = Depends(get_db)) -> AssemblyService:
    """Provide an AssemblyService instance wired with async database session."""
    return AssemblyService(
        assembly_repo=AssemblyRepository(db),
        inventory_repo=InventoryRepository(db),
        order_repo=OrderRepository(db),
    )
