from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.security import oauth2_scheme
from src.modules.iam.models import User, UserRole
from src.modules.iam.repository import UserRepository
from src.modules.iam.service import IAMService


def get_iam_service(db: AsyncSession = Depends(get_db)) -> IAMService:
    """Provide an IAMService instance wired with an async database session."""
    return IAMService(UserRepository(db))


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    service: IAMService = Depends(get_iam_service),
) -> User:
    """Resolve and validate the currently authenticated active user from JWT bearer token."""
    if not token:
        raise UnauthorizedException("Authentication credentials were not provided.")
    return await service.get_active_user_from_access_token(token)


def require_role(
    allowed_roles: Sequence[UserRole],
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Create a FastAPI dependency enforcing that the current user has an allowed role."""
    allowed_set = frozenset(allowed_roles)

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_set:
            raise ForbiddenException(
                "You do not have sufficient permissions to perform this operation."
            )
        return current_user

    return role_checker
