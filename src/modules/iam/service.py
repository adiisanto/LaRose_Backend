from datetime import UTC, datetime
from uuid import UUID

import jwt
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    UnauthorizedException,
)
from src.core.pagination import PaginatedData, PaginationParams
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.modules.iam.models import User, UserRole
from src.modules.iam.repository import UserRepository
from src.modules.iam.schemas import TokenResponse, UserCreate, UserResponse, UserUpdate


class IAMService:
    """Application service handling authentication, JWT tokens, and user lifecycle."""

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    @staticmethod
    def _is_user_enabled(user: User | None) -> bool:
        return user is not None and user.is_active and user.deleted_at is None

    @staticmethod
    def _build_token_response(user: User) -> TokenResponse:
        claims = {"sub": str(user.id), "role": user.role.value}
        access_token = create_access_token(claims)
        refresh_token = create_refresh_token(claims)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    @staticmethod
    def _parse_user_id(sub: object) -> UUID:
        try:
            return UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise UnauthorizedException("Invalid token subject.") from exc

    async def authenticate_user(self, identifier: str, password: str) -> TokenResponse:
        """Verify user credentials and issue access and refresh JWT tokens."""
        user = await self.repository.get_by_username_or_email(identifier)
        if not self._is_user_enabled(user) or not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid credentials or inactive account.")
        return self._build_token_response(user)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Validate a refresh token and issue a fresh token pair."""
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedException("Invalid or expired refresh token.") from exc

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type; expected refresh token.")

        user_id = self._parse_user_id(payload.get("sub"))
        user = await self.repository.get_by_id(user_id)
        if not self._is_user_enabled(user):
            raise UnauthorizedException("User account is inactive or no longer exists.")

        return self._build_token_response(user)

    async def get_active_user_from_access_token(self, token: str) -> User:
        """Validate a bearer access token and load the corresponding active user."""
        try:
            payload = decode_token(token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedException("Invalid or expired access token.") from exc

        if payload.get("type") != "access":
            raise UnauthorizedException("Invalid token type; expected access token.")

        user_id = self._parse_user_id(payload.get("sub"))
        user = await self.repository.get_by_id(user_id)
        if not self._is_user_enabled(user):
            raise UnauthorizedException("User account is inactive or no longer exists.")

        return user

    async def create_user(self, payload: UserCreate) -> User:
        """Register a new internal user with bcrypt password hashing."""
        if await self.repository.get_by_username(payload.username) is not None:
            raise ConflictException(
                code="CONFLICT",
                message=f"Username '{payload.username}' is already registered.",
            )
        if await self.repository.get_by_email(payload.email) is not None:
            raise ConflictException(
                code="CONFLICT",
                message=f"Email '{payload.email}' is already registered.",
            )

        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
            is_active=True,
        )
        try:
            return await self.repository.create(user)
        except IntegrityError as exc:
            await self.repository.session.rollback()
            raise ConflictException(
                code="CONFLICT",
                message="A user with the same username or email already exists.",
            ) from exc

    async def get_user_by_id(self, user_id: UUID) -> User:
        """Fetch an existing user by UUID or raise 404."""
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException("User", user_id)
        return user

    async def list_users(
        self,
        pagination: PaginationParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> PaginatedData[UserResponse]:
        """List users with optional role/active filters and pagination."""
        users, total = await self.repository.list_users(
            offset=pagination.offset,
            limit=pagination.page_size,
            role=role,
            is_active=is_active,
        )
        items = [UserResponse.model_validate(user) for user in users]
        return PaginatedData.create(items=items, total=total, params=pagination)

    async def update_user(
        self,
        user_id: UUID,
        payload: UserUpdate,
        *,
        actor_id: UUID,
    ) -> User:
        """Update user attributes, role, or activation state."""
        user = await self.get_user_by_id(user_id)

        if payload.is_active is False and user.id == actor_id:
            raise ConflictException(
                code="SELF_DEACTIVATION_NOT_ALLOWED",
                message="You cannot deactivate your own active account.",
            )

        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.role is not None:
            user.role = payload.role
        if payload.is_active is not None:
            user.is_active = payload.is_active
            user.deleted_at = None if payload.is_active else (user.deleted_at or datetime.now(UTC))

        return await self.repository.update(user)

    async def deactivate_user(self, user_id: UUID, *, actor_id: UUID) -> User:
        """Soft-delete a user by marking them inactive and setting deleted_at."""
        user = await self.get_user_by_id(user_id)
        if user.id == actor_id:
            raise ConflictException(
                code="SELF_DEACTIVATION_NOT_ALLOWED",
                message="You cannot deactivate your own active account.",
            )

        user.is_active = False
        user.deleted_at = user.deleted_at or datetime.now(UTC)
        return await self.repository.update(user)
