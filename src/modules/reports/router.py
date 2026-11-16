"""Reports & Executive Analytics API Router."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from src.core.pagination import APIResponse
from src.modules.iam.dependencies import require_role
from src.modules.iam.models import User, UserRole
from src.modules.reports.dependencies import get_reports_service
from src.modules.reports.schemas import (
    ExecutiveDashboardResponse,
    InventoryValuationResponse,
    LowStockAlertsResponse,
)
from src.modules.reports.service import ReportsService

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


@router.get(
    "/executive-dashboard",
    response_model=APIResponse[ExecutiveDashboardResponse],
    status_code=status.HTTP_200_OK,
    summary="Get executive revenue, sales performance, and order lifecycle metrics",
)
async def get_executive_dashboard(
    start_date: datetime | None = Query(
        None,
        description="Filter orders created on or after this timestamp (ISO 8601)",
    ),
    end_date: datetime | None = Query(
        None,
        description="Filter orders created on or before this timestamp (ISO 8601)",
    ),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
    service: ReportsService = Depends(get_reports_service),
) -> APIResponse[ExecutiveDashboardResponse]:
    """Retrieve executive metrics including revenue, orders by status, and best-selling products."""
    data = await service.get_executive_dashboard(start_date=start_date, end_date=end_date)
    return APIResponse(
        success=True,
        data=data,
        message="Executive dashboard metrics retrieved successfully",
    )


@router.get(
    "/inventory-valuation",
    response_model=APIResponse[InventoryValuationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get working capital inventory valuation and stock levels",
)
async def get_inventory_valuation(
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
    service: ReportsService = Depends(get_reports_service),
) -> APIResponse[InventoryValuationResponse]:
    """Calculate warehouse inventory valuation, physical units on-hand, and reserved allocations."""
    data = await service.get_inventory_valuation()
    return APIResponse(
        success=True,
        data=data,
        message="Inventory valuation metrics calculated successfully",
    )


@router.get(
    "/low-stock-alerts",
    response_model=APIResponse[LowStockAlertsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get critical stock alerts with reorder recommendations",
)
async def get_low_stock_alerts(
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
    service: ReportsService = Depends(get_reports_service),
) -> APIResponse[LowStockAlertsResponse]:
    """Retrieve list of materials whose available inventory is below reorder thresholds."""
    data = await service.get_low_stock_alerts()
    return APIResponse(
        success=True,
        data=data,
        message="Critical stock alerts retrieved successfully",
    )
