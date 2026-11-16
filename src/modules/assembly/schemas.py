from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import Field, field_validator

from src.core.pagination import CamelModel
from src.modules.orders.models import TaskStatus


def _normalize_utc(value: datetime) -> datetime:
    """Ensure datetimes returned from any database backend are timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ScrapReportInput(CamelModel):
    """Payload for reporting damaged material during bouquet arrangement."""

    material_id: UUID
    quantity: int = Field(1, gt=0, description="Damaged item quantity (> 0)")
    reason: str | None = Field(None, max_length=255, description="Reason for damage/scrap")


class RequiredMaterialItem(CamelModel):
    """Checklist item showing material, quantity, and storage bin location in studio."""

    material_id: UUID
    material_name: str
    material_sku: str
    storage_bin: str | None = None
    quantity_required: int


class AssemblyTaskQueueItem(CamelModel):
    """Item in tablet queue ordered by delivery_date ASC."""

    id: UUID
    order_id: UUID
    order_number: str
    customer_name: str
    delivery_date: date
    status: TaskStatus
    assigned_staff_name: str | None = None
    custom_instructions: str | None = None
    item_count: int
    created_at: datetime
    started_at: datetime | None = None

    @field_validator("created_at", "started_at", mode="after")
    @classmethod
    def normalize_dates(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value) if value else None


class AssemblyTaskDetailResponse(CamelModel):
    """Full detail of an assembly task including raw material checklist from BOM recipes."""

    id: UUID
    order_id: UUID
    order_number: str
    customer_name: str
    delivery_date: date
    status: TaskStatus
    assigned_staff_id: UUID | None = None
    assigned_staff_name: str | None = None
    custom_instructions: str | None = None
    required_materials: list[RequiredMaterialItem]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    @field_validator("created_at", "started_at", "completed_at", mode="after")
    @classmethod
    def normalize_dates(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value) if value else None
