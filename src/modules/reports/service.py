"""Business logic service for Studio Analytics, Metrics, and Alerts."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.orders.models import OrderStatus
from src.modules.reports.repository import ReportsRepository
from src.modules.reports.schemas import (
    ExecutiveDashboardResponse,
    InventoryValuationItem,
    InventoryValuationResponse,
    LowStockAlertItem,
    LowStockAlertsResponse,
    OrderStatusCount,
    TopSellingProduct,
)


class ReportsService:
    """Service providing aggregated analytical calculations for Studio Owner & Admins."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ReportsRepository(session)

    async def get_executive_dashboard(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ExecutiveDashboardResponse:
        """Calculate high-level sales revenue, status breakdowns, and best-sellers."""
        status_data = await self.repository.get_orders_by_status_summary(start_date, end_date)
        top_sellers_data = await self.repository.get_top_selling_products(
            limit=5,
            start_date=start_date,
            end_date=end_date,
        )

        total_orders = 0
        total_revenue = Decimal("0.00")
        completed_count = 0
        cancelled_count = 0

        status_counts = []
        for item in status_data:
            st = item["status"]
            cnt = item["count"]
            amt = item["total_amount"]
            total_orders += cnt

            if st in (
                OrderStatus.PAID,
                OrderStatus.PROCESSING,
                OrderStatus.READY_FOR_DELIVERY,
                OrderStatus.COMPLETED,
            ):
                total_revenue += amt

            if st == OrderStatus.COMPLETED:
                completed_count = cnt
            elif st == OrderStatus.CANCELLED:
                cancelled_count = cnt

            status_counts.append(
                OrderStatusCount(
                    status=st,
                    count=cnt,
                    total_amount=amt,
                )
            )

        cancellation_rate = 0.0
        if total_orders > 0:
            cancellation_rate = round((cancelled_count / total_orders) * 100.0, 2)

        top_sellers = [TopSellingProduct(**ts) for ts in top_sellers_data]

        return ExecutiveDashboardResponse(
            period_start=start_date,
            period_end=end_date,
            total_revenue=total_revenue,
            total_orders=total_orders,
            completed_orders_count=completed_count,
            cancelled_orders_count=cancelled_count,
            cancellation_rate=cancellation_rate,
            orders_by_status=status_counts,
            top_selling_products=top_sellers,
        )

    async def get_inventory_valuation(self) -> InventoryValuationResponse:
        """Calculate total inventory assets and working capital locked in warehouse."""
        items_data = await self.repository.get_inventory_valuation_data()

        total_tracked = len(items_data)
        total_units_on_hand = sum(item["quantity_on_hand"] for item in items_data)
        total_units_reserved = sum(item["quantity_reserved"] for item in items_data)
        total_val = sum(item["total_valuation"] for item in items_data)

        items = [InventoryValuationItem(**item) for item in items_data]

        return InventoryValuationResponse(
            total_tracked_items=total_tracked,
            total_units_on_hand=total_units_on_hand,
            total_units_reserved=total_units_reserved,
            total_working_capital_valuation=Decimal(str(total_val)),
            items=items,
        )

    async def get_low_stock_alerts(self) -> LowStockAlertsResponse:
        """Retrieve real-time list of critical items needing reorder."""
        alerts_data = await self.repository.get_low_stock_inventory_items()

        total_alerts = len(alerts_data)
        critical_count = sum(1 for a in alerts_data if a["alert_level"] == "CRITICAL")
        warning_count = sum(1 for a in alerts_data if a["alert_level"] == "WARNING")

        alerts = [LowStockAlertItem(**a) for a in alerts_data]

        return LowStockAlertsResponse(
            total_alert_items=total_alerts,
            critical_items_count=critical_count,
            warning_items_count=warning_count,
            alerts=alerts,
        )
