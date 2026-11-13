from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from src.core.pagination import APIResponse, PaginatedData, PaginationParams
from src.modules.iam.dependencies import get_current_user, get_iam_service, require_role
from src.modules.iam.models import User, UserRole
from src.modules.iam.schemas import (
    LoginRequest,
    OAuth2TokenResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.modules.iam.service import IAMService

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])


def get_pagination_params(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int | None = Query(
        None,
        ge=1,
        le=100,
        alias="pageSize",
        description="Items per page (max 100)",
    ),
    page_size_snake: int | None = Query(
        None,
        ge=1,
        le=100,
        alias="page_size",
        include_in_schema=False,
    ),
) -> PaginationParams:
    """Build PaginationParams accepting both camelCase (pageSize) and snake_case (page_size)."""
    resolved_size = page_size if page_size is not None else (page_size_snake or 20)
    return PaginationParams(page=page, page_size=resolved_size)


@auth_router.post(
    "/token",
    response_model=OAuth2TokenResponse,
    summary="OAuth2 password login (Swagger UI & form clients)",
)
async def login_with_oauth2_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: IAMService = Depends(get_iam_service),
) -> OAuth2TokenResponse:
    """Authenticate user via OAuth2 Password Request Form and issue JWT tokens."""
    token_data = await service.authenticate_user(form_data.username, form_data.password)
    return OAuth2TokenResponse(
        success=True,
        data=token_data,
        message="Authentication successful.",
        access_token=token_data.access_token,
        token_type=token_data.token_type,
    )


@auth_router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    summary="JSON credential login",
)
async def login_with_json(
    payload: LoginRequest,
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[TokenResponse]:
    """Authenticate user via JSON payload and return standard APIResponse envelope."""
    token_data = await service.authenticate_user(payload.username, payload.password)
    return APIResponse(
        success=True,
        data=token_data,
        message="Authentication successful.",
    )


@auth_router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    summary="Refresh JWT access token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[TokenResponse]:
    """Exchange a valid refresh token for a new access and refresh token pair."""
    token_data = await service.refresh_access_token(payload.refresh_token)
    return APIResponse(
        success=True,
        data=token_data,
        message="Token refreshed successfully.",
    )


@auth_router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get current authenticated user profile",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserResponse]:
    """Return the profile of the currently authenticated user."""
    return APIResponse(
        success=True,
        data=UserResponse.model_validate(current_user),
        message="User profile retrieved successfully.",
    )


@users_router.get(
    "",
    response_model=APIResponse[PaginatedData[UserResponse]],
    summary="List internal users (Owner only)",
)
async def list_users(
    pagination: PaginationParams = Depends(get_pagination_params),
    role: UserRole | None = Query(None, description="Filter users by RBAC role"),
    is_active: bool | None = Query(
        None,
        alias="isActive",
        description="Filter users by active status",
    ),
    is_active_snake: bool | None = Query(
        None,
        alias="is_active",
        include_in_schema=False,
    ),
    _: User = Depends(require_role([UserRole.OWNER])),
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[PaginatedData[UserResponse]]:
    """Return a paginated list of internal users for Owner management."""
    resolved_active = is_active if is_active is not None else is_active_snake
    paginated_users = await service.list_users(
        pagination,
        role=role,
        is_active=resolved_active,
    )
    return APIResponse(
        success=True,
        data=paginated_users,
        message="Users retrieved successfully.",
    )


@users_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[UserResponse],
    summary="Create internal user account (Owner only)",
)
async def create_user(
    payload: UserCreate,
    _: User = Depends(require_role([UserRole.OWNER])),
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[UserResponse]:
    """Create a new internal studio user account."""
    user = await service.create_user(payload)
    return APIResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User created successfully.",
    )


@users_router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Get user detail by ID (Owner only)",
)
async def get_user_detail(
    user_id: UUID,
    _: User = Depends(require_role([UserRole.OWNER])),
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[UserResponse]:
    """Retrieve a single user's profile by UUID."""
    user = await service.get_user_by_id(user_id)
    return APIResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User retrieved successfully.",
    )


@users_router.patch(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Update user profile, role, or status (Owner only)",
)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_owner: User = Depends(require_role([UserRole.OWNER])),
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[UserResponse]:
    """Update an existing user's full name, role, or active status."""
    user = await service.update_user(user_id, payload, actor_id=current_owner.id)
    return APIResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User updated successfully.",
    )


@users_router.delete(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Soft-deactivate user account (Owner only)",
)
async def deactivate_user(
    user_id: UUID,
    current_owner: User = Depends(require_role([UserRole.OWNER])),
    service: IAMService = Depends(get_iam_service),
) -> APIResponse[UserResponse]:
    """Soft-delete a user by setting is_active=False and recording deleted_at."""
    user = await service.deactivate_user(user_id, actor_id=current_owner.id)
    return APIResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User deactivated successfully.",
    )


router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
