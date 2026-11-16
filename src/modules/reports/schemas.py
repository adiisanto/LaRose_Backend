"""Pydantic schemas and response contracts for Reports and Analytics."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from src.core.pagination import CamelModel
from src.modules.catalog.models import ProductType
from src.modules.orders.models import OrderStatus


class OrderStatusCount(CamelModel):
    """Aggregate count and financial value for orders in a specific lifecycle state."""

    status: OrderStatus
    count: int = Field(0, description="Total number of orders in this status")
    total_amount: Decimal = Field(Decimal("0.00"), description="Total monetary sum")


class TopSellingProduct(CamelModel):
    """Product performance metric in sales reports."""

    product_id: UUID
    sku: str
    name: str
    product_type: ProductType
    total_units_sold: int
    total_revenue: Decimal


class ExecutiveDashboardResponse(CamelModel):
    """Executive metrics summary for Studio Owner and Admins."""

    period_start: datetime | None = None
    period_end: datetime | None = None
    total_revenue: Decimal = Field(
        Decimal("0.00"),
        description="Gross revenue from confirmed/paid/completed orders",
    )
    total_orders: int = Field(0, description="Total orders across all statuses in period")
    completed_orders_count: int = Field(0, description="Total completed orders")
    cancelled_orders_count: int = Field(0, description="Total cancelled orders")
    cancellation_rate: float = Field(
        0.0,
        description="Percentage of cancelled orders relative to total orders",
    )
    orders_by_status: list[OrderStatusCount] = Field(default_factory=list)
    top_selling_products: list[TopSellingProduct] = Field(default_factory=list)


class InventoryValuationItem(CamelModel):
    """Valuation item representing working capital locked in warehouse inventory."""

    product_id: UUID
    sku: str
    name: str
    product_type: ProductType
    storage_bin: str | None = None
    quantity_on_hand: int
    quantity_reserved: int
    available_quantity: int
    unit_cost_estimate: Decimal = Field(
        ...,
        description="Estimated valuation cost per unit based on retail price",
    )
    total_valuation: Decimal = Field(
        ...,
        description="Valuation (quantity_on_hand * unit_cost_estimate)",
    )


class InventoryValuationResponse(CamelModel):
    """Warehouse inventory valuation summary."""

    total_tracked_items: int
    total_units_on_hand: int
    total_units_reserved: int
    total_working_capital_valuation: Decimal
    items: list[InventoryValuationItem] = Field(default_factory=list)


class LowStockAlertItem(CamelModel):
    """Critical low stock alert item indicating need for supplier reordering."""

    product_id: UUID
    sku: str
    name: str
    storage_bin: str | None = None
    quantity_on_hand: int
    quantity_reserved: int
    available_quantity: int
    reorder_point: int
    recommended_reorder_qty: int
    alert_level: str = Field(
        ..., description="CRITICAL (0 available) or WARNING (<= reorder_point)"
    )


class LowStockAlertsResponse(CamelModel):
    """Critical stock alerts summary."""

    total_alert_items: int
    critical_items_count: int
    warning_items_count: int
    alerts: list[LowStockAlertItem] = Field(default_factory=list)
