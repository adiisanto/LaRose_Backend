from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from src.core.pagination import CamelModel
from src.modules.orders.models import OrderStatus, TaskStatus


def _normalize_utc(value: datetime) -> datetime:
    """Ensure datetimes returned from any database backend are timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OrderItemInput(CamelModel):
    """Line item item in order creation request."""

    product_id: UUID
    quantity: int = Field(..., gt=0, description="Quantity ordered (> 0)")


class OrderCreate(CamelModel):
    """Payload for submitting a customer order."""

    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_phone: str = Field(..., min_length=8, max_length=30)
    customer_address: str | None = None
    delivery_date: date
    greeting_card_notes: str | None = None
    internal_notes: str | None = None
    items: list[OrderItemInput] = Field(..., min_length=1, description="List of items in order")

    @field_validator("customer_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Customer name must be at least 2 characters.")
        return cleaned

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("Customer phone must be at least 8 characters.")
        return cleaned


class OrderItemResponse(CamelModel):
    """Line item detail in order response."""

    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderResponse(CamelModel):
    """Full detail response for an order."""

    id: UUID
    order_number: str
    customer_name: str
    customer_phone: str
    customer_address: str | None = None
    delivery_date: date
    status: OrderStatus
    total_amount: Decimal
    greeting_card_notes: str | None = None
    internal_notes: str | None = None
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def normalize_dates(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class AssemblyTaskSummaryResponse(CamelModel):
    """Summary of fulfillment task created from confirmed order."""

    id: UUID
    order_id: UUID
    order_number: str
    delivery_date: date
    status: TaskStatus
    custom_instructions: str | None = None
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_utc(value)
