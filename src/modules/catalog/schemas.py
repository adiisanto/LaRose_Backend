from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from src.core.pagination import CamelModel
from src.modules.catalog.models import ProductType


def _normalize_utc(value: datetime) -> datetime:
    """Ensure datetimes returned from any database backend are timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class BOMComponentItem(CamelModel):
    """Schema for a single BOM component item within a bouquet recipe."""

    material_id: UUID
    material_name: str | None = None
    material_sku: str | None = None
    storage_bin: str | None = None
    quantity_required: int = Field(..., gt=0, description="Quantity of material required (> 0)")


class ProductCreate(CamelModel):
    """Request payload for creating a single item or bouquet product."""

    sku: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = None
    product_type: ProductType
    price: Decimal = Field(..., ge=0)
    storage_bin: str | None = Field(None, max_length=50)
    is_premade: bool = False
    bom_components: list[BOMComponentItem] | None = None

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) < 2 or any(ch.isspace() for ch in cleaned):
            raise ValueError("SKU must be at least 2 characters without spaces.")
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned

    @field_validator("storage_bin")
    @classmethod
    def validate_storage_bin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProductUpdate(CamelModel):
    """Request payload for updating an existing product."""

    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    storage_bin: str | None = Field(None, max_length=50)
    is_premade: bool | None = None
    is_active: bool | None = None
    bom_components: list[BOMComponentItem] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned

    @field_validator("storage_bin")
    @classmethod
    def validate_storage_bin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProductResponse(CamelModel):
    """Response payload representing detailed product information."""

    id: UUID
    sku: str
    name: str
    description: str | None = None
    product_type: ProductType
    price: Decimal
    storage_bin: str | None = None
    is_premade: bool
    is_active: bool
    available_stock: int | None = None
    bom_components: list[BOMComponentItem] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def normalize_created_updated(cls, value: datetime) -> datetime:
        return _normalize_utc(value)
