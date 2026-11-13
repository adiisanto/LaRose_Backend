import re
from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, field_validator

from src.core.config import settings
from src.core.pagination import APIResponse, CamelModel
from src.modules.iam.models import UserRole

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_utc(value: datetime) -> datetime:
    """Ensure datetimes returned from any database backend are timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class UserCreate(CamelModel):
    """Request payload for creating an internal studio user."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole = UserRole.STAFF_PACKING

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3 or any(ch.isspace() for ch in cleaned):
            raise ValueError("Username must be at least 3 characters without spaces.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValueError("Invalid email address format.")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned


class UserUpdate(CamelModel):
    """Request payload for updating user profile, role, or activation status."""

    full_name: str | None = Field(None, min_length=2, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned


class UserResponse(CamelModel):
    """Public user representation omitting sensitive credentials."""

    id: UUID
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def ensure_utc_created_at(cls, value: datetime) -> datetime:
        if isinstance(value, datetime):
            return _normalize_utc(value)
        return value


class LoginRequest(CamelModel):
    """JSON login payload for frontend clients."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(CamelModel):
    """JWT authentication payload containing access/refresh tokens and user details."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = Field(
        default_factory=lambda: settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    user: UserResponse


class OAuth2TokenResponse(APIResponse[TokenResponse]):
    """Unified envelope plus top-level OAuth2 fields for Swagger UI compatibility."""

    access_token: str = Field(..., serialization_alias="access_token")
    token_type: str = Field("bearer", serialization_alias="token_type")


class RefreshTokenRequest(CamelModel):
    """Request payload for exchanging a refresh token for a new token pair."""

    refresh_token: str = Field(..., min_length=1)
