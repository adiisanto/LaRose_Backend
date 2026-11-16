"""Dependencies for Reports and Analytics module."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.reports.service import ReportsService


async def get_reports_service(
    session: AsyncSession = Depends(get_db),
) -> ReportsService:
    """Provide initialized ReportsService instance with request-scoped session."""
    return ReportsService(session)
