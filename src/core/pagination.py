import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base Pydantic model with automatic camelCase serialization for APIs."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class APIResponse(CamelModel, Generic[T]):
    """Standard unified response envelope."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    error: Any | None = None


class PaginationParams(CamelModel):
    """Standard query parameters for paginated endpoints."""

    page: int = Field(1, ge=1, description="Page number starting from 1")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedData(CamelModel, Generic[T]):
    """Container for paginated items and metadata."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        params: PaginationParams,
    ) -> "PaginatedData[T]":
        total_pages = math.ceil(total / params.page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
        )
