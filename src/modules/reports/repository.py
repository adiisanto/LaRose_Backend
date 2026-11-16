"""Repository for executing performant analytical aggregation queries."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog.models import Product
from src.modules.inventory.models import Inventory
from src.modules.orders.models import Order, OrderItem, OrderStatus


class ReportsRepository:
    """Async repository providing aggregated queries for Executive Analytics & Reporting."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_orders_by_status_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate order counts and financial sums grouped by OrderStatus."""
        stmt = select(
            Order.status,
            func.count(Order.id).label("status_count"),
            func.coalesce(func.sum(Order.total_amount), 0.0).label("status_sum"),
        ).group_by(Order.status)

        if start_date:
            stmt = stmt.where(Order.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Order.created_at <= end_date)

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "status": row.status,
                "count": row.status_count,
                "total_amount": Decimal(str(row.status_sum)),
            }
            for row in rows
        ]

    async def get_top_selling_products(
        self,
        limit: int = 5,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top products by units sold across valid (non-cancelled) orders."""
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku,
                Product.name,
                Product.product_type,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.subtotal).label("revenue_sum"),
            )
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status != OrderStatus.CANCELLED)
        )

        if start_date:
            stmt = stmt.where(Order.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Order.created_at <= end_date)

        stmt = (
            stmt.group_by(
                Product.id,
                Product.sku,
                Product.name,
                Product.product_type,
            )
            .order_by(desc("units_sold"))
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "product_id": row.product_id,
                "sku": row.sku,
                "name": row.name,
                "product_type": row.product_type,
                "total_units_sold": int(row.units_sold),
                "total_revenue": Decimal(str(row.revenue_sum)),
            }
            for row in rows
        ]

    async def get_inventory_valuation_data(self) -> list[dict[str, Any]]:
        """Compute warehouse working capital valuation for active products."""
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku,
                Product.name,
                Product.product_type,
                Product.price,
                Product.storage_bin,
                func.coalesce(Inventory.quantity_on_hand, 0).label("quantity_on_hand"),
                func.coalesce(Inventory.quantity_reserved, 0).label("quantity_reserved"),
            )
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .where(
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
            .order_by(Product.sku.asc())
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        valuation_items = []
        for row in rows:
            qty_on_hand = int(row.quantity_on_hand)
            qty_reserved = int(row.quantity_reserved)
            avail = qty_on_hand - qty_reserved
            unit_price = Decimal(str(row.price))
            total_val = unit_price * Decimal(qty_on_hand)

            valuation_items.append(
                {
                    "product_id": row.product_id,
                    "sku": row.sku,
                    "name": row.name,
                    "product_type": row.product_type,
                    "storage_bin": row.storage_bin,
                    "quantity_on_hand": qty_on_hand,
                    "quantity_reserved": qty_reserved,
                    "available_quantity": avail,
                    "unit_cost_estimate": unit_price,
                    "total_valuation": total_val,
                }
            )

        return valuation_items

    async def get_low_stock_inventory_items(self) -> list[dict[str, Any]]:
        """Retrieve inventory items where available quantity is at or below reorder point."""
        on_hand_col = func.coalesce(Inventory.quantity_on_hand, 0)
        reserved_col = func.coalesce(Inventory.quantity_reserved, 0)
        reorder_col = func.coalesce(Inventory.reorder_point, 10)
        avail_expr = on_hand_col - reserved_col

        stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku,
                Product.name,
                Product.storage_bin,
                on_hand_col.label("quantity_on_hand"),
                reserved_col.label("quantity_reserved"),
                reorder_col.label("reorder_point"),
                avail_expr.label("available_quantity"),
            )
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .where(
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
                avail_expr <= reorder_col,
            )
            .order_by(avail_expr.asc(), Product.sku.asc())
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        alerts = []
        for row in rows:
            avail = int(row.available_quantity)
            reorder = int(row.reorder_point)
            # Recommended reorder: at least 2 * reorder_point or minimum 20 units
            target_buffer = max(reorder * 2, 20)
            rec_qty = max(target_buffer - avail, 10)
            alert_level = "CRITICAL" if avail <= 0 else "WARNING"

            alerts.append(
                {
                    "product_id": row.product_id,
                    "sku": row.sku,
                    "name": row.name,
                    "storage_bin": row.storage_bin,
                    "quantity_on_hand": int(row.quantity_on_hand),
                    "quantity_reserved": int(row.quantity_reserved),
                    "available_quantity": avail,
                    "reorder_point": reorder,
                    "recommended_reorder_qty": rec_qty,
                    "alert_level": alert_level,
                }
            )

        return alerts
