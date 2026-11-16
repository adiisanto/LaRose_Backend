from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, field_validator

from src.core.pagination import CamelModel
from src.modules.inventory.models import MovementType


def _normalize_utc(value: datetime) -> datetime:
    """Ensure datetimes returned from any database backend are timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RestockInput(CamelModel):
    """Payload for registering physical inbound inventory."""

    product_id: UUID
    quantity: int = Field(..., gt=0, description="Inbound restock quantity (> 0)")
    notes: str | None = None
    reference_id: str | None = None


class InventoryResponse(CamelModel):
    """Schema representing inventory balances for a product."""

    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    storage_bin: str | None = None
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    reorder_point: int
    is_low_stock: bool
    updated_at: datetime

    @field_validator("updated_at", mode="after")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class StockMovementResponse(CamelModel):
    """Schema representing an immutable stock ledger audit record."""

    id: UUID
    inventory_id: UUID
    movement_type: MovementType
    delta_quantity: int
    reference_id: str | None = None
    notes: str | None = None
    created_by_username: str | None = None
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_utc(value)
