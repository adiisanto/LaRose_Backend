"""IAM Module Package."""

from src.modules.iam.dependencies import get_current_user, require_role
from src.modules.iam.models import User, UserRole
from src.modules.iam.router import router

__all__ = [
    "User",
    "UserRole",
    "get_current_user",
    "require_role",
    "router",
]
