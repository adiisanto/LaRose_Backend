from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.modules.iam.models import User, UserRole


async def _seed_user(
    db_session: AsyncSession,
    *,
    username: str,
    email: str,
    password: str = "SecretPass123!",
    full_name: str = "Studio User",
    role: UserRole = UserRole.STAFF_PACKING,
    is_active: bool = True,
    deleted_at: datetime | None = None,
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=is_active,
        deleted_at=deleted_at,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _login_oauth2(
    client: AsyncClient,
    username: str,
    password: str = "SecretPass123!",
) -> dict:
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_oauth2_token_login_success_and_swagger_fields(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """OAuth2 login returns both top-level Swagger token fields and camelCase APIResponse."""
    await _seed_user(
        db_session,
        username="owner_larose",
        email="owner@larose.studio",
        full_name="Alex Owner",
        role=UserRole.OWNER,
    )

    body = await _login_oauth2(client_with_db, "owner_larose")

    # Swagger UI OAuth2 compatibility fields
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["token_type"] == "bearer"

    # Standard APIResponse + CamelModel contract
    assert body["success"] is True
    data = body["data"]
    assert data["accessToken"] == body["access_token"]
    assert isinstance(data["refreshToken"], str) and data["refreshToken"]
    assert data["tokenType"] == "bearer"
    assert data["expiresInSeconds"] == 3600
    assert data["user"]["username"] == "owner_larose"
    assert data["user"]["fullName"] == "Alex Owner"
    assert data["user"]["role"] == "OWNER"
    assert data["user"]["isActive"] is True
    assert data["user"]["createdAt"].endswith("Z")
    assert "passwordHash" not in data["user"]
    assert "password_hash" not in data["user"]


@pytest.mark.asyncio
async def test_json_login_by_email_success(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """JSON login endpoint supports login using email and returns APIResponse."""
    await _seed_user(
        db_session,
        username="admin_larose",
        email="admin@larose.studio",
        full_name="Bella Admin",
        role=UserRole.ADMIN,
    )

    response = await client_with_db.post(
        "/api/v1/auth/login",
        json={"username": "ADMIN@larose.studio", "password": "SecretPass123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["username"] == "admin_larose"
    assert body["data"]["user"]["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_login_failures_wrong_password_and_inactive_user(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Wrong password, unknown user, and inactive user all return 401 AUTHENTICATION_REQUIRED."""
    await _seed_user(
        db_session,
        username="staff_active",
        email="staff1@larose.studio",
        role=UserRole.STAFF_PACKING,
    )
    await _seed_user(
        db_session,
        username="staff_inactive",
        email="staff2@larose.studio",
        role=UserRole.STAFF_PACKING,
        is_active=False,
        deleted_at=datetime.now(UTC),
    )

    for username, password in [
        ("staff_active", "WrongPassword!"),
        ("nonexistent_user", "SecretPass123!"),
        ("staff_inactive", "SecretPass123!"),
    ]:
        res = await client_with_db.post(
            "/api/v1/auth/token",
            data={"username": username, "password": password},
        )
        assert res.status_code == 401
        err_body = res.json()
        assert err_body["success"] is False
        assert err_body["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_refresh_token_flow_and_validation(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Refresh endpoint exchanges valid refresh token and rejects access/invalid tokens."""
    await _seed_user(
        db_session,
        username="staff_refresh",
        email="refresh@larose.studio",
        role=UserRole.STAFF_PACKING,
    )

    login_body = await _login_oauth2(client_with_db, "staff_refresh")
    access_token = login_body["data"]["accessToken"]
    refresh_token = login_body["data"]["refreshToken"]

    # Valid refresh token succeeds
    refresh_res = await client_with_db.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": refresh_token},
    )
    assert refresh_res.status_code == 200
    refreshed = refresh_res.json()
    assert refreshed["success"] is True
    assert refreshed["data"]["user"]["username"] == "staff_refresh"

    # Using access token as refresh token fails with 401
    wrong_type_res = await client_with_db.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": access_token},
    )
    assert wrong_type_res.status_code == 401
    assert wrong_type_res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Invalid token fails with 401
    invalid_res = await client_with_db.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": "not.a.valid.jwt"},
    )
    assert invalid_res.status_code == 401
    assert invalid_res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_auth_me_requires_valid_access_token(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """GET /auth/me returns profile for valid access token and 401 otherwise."""
    user = await _seed_user(
        db_session,
        username="me_user",
        email="me@larose.studio",
        role=UserRole.ADMIN,
    )
    login_body = await _login_oauth2(client_with_db, "me_user")
    access_token = login_body["data"]["accessToken"]
    refresh_token = login_body["data"]["refreshToken"]

    # Unauthenticated -> 401 standard envelope
    no_auth = await client_with_db.get("/api/v1/auth/me")
    assert no_auth.status_code == 401
    assert no_auth.json()["success"] is False
    assert no_auth.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Refresh token used as Bearer -> 401
    refresh_as_bearer = await client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert refresh_as_bearer.status_code == 401

    # Expired access token -> 401
    expired_token = create_access_token(
        {"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(minutes=-5),
    )
    expired_res = await client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired_res.status_code == 401

    # Valid access token -> 200
    me_res = await client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["data"]["username"] == "me_user"
    assert me_res.json()["data"]["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_rbac_blocks_non_owner_on_user_management(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN and STAFF_PACKING receive 403 INSUFFICIENT_PERMISSIONS on /users routes."""
    await _seed_user(
        db_session,
        username="admin_user",
        email="admin_rbac@larose.studio",
        role=UserRole.ADMIN,
    )
    await _seed_user(
        db_session,
        username="staff_user",
        email="staff_rbac@larose.studio",
        role=UserRole.STAFF_PACKING,
    )

    for username in ["admin_user", "staff_user"]:
        token = (await _login_oauth2(client_with_db, username))["data"]["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}

        list_res = await client_with_db.get("/api/v1/users", headers=headers)
        assert list_res.status_code == 403
        assert list_res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

        create_res = await client_with_db.post(
            "/api/v1/users",
            headers=headers,
            json={
                "username": "new_staff",
                "email": "new@larose.studio",
                "password": "Password123!",
                "fullName": "New Staff",
                "role": "STAFF_PACKING",
            },
        )
        assert create_res.status_code == 403
        assert create_res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
async def test_owner_user_lifecycle_create_list_update_and_soft_delete(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """OWNER can create, list, filter, update, and soft-deactivate internal users."""
    owner = await _seed_user(
        db_session,
        username="owner_main",
        email="owner_main@larose.studio",
        full_name="Owner Main",
        role=UserRole.OWNER,
    )
    owner_token = (await _login_oauth2(client_with_db, "owner_main"))["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {owner_token}"}

    # 1. Create user -> 201 Created
    create_res = await client_with_db.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "packer_one",
            "email": "Packer.One@LaRose.Studio",
            "password": "StrongPassword1!",
            "fullName": "Citra Packer",
            "role": "STAFF_PACKING",
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()["data"]
    created_id = created["id"]
    assert created["username"] == "packer_one"
    assert created["email"] == "packer.one@larose.studio"
    assert created["role"] == "STAFF_PACKING"
    assert created["isActive"] is True

    # 2. Duplicate username or email -> 409 CONFLICT
    dup_username = await client_with_db.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "packer_one",
            "email": "other@larose.studio",
            "password": "StrongPassword1!",
            "fullName": "Duplicate User",
            "role": "ADMIN",
        },
    )
    assert dup_username.status_code == 409
    assert dup_username.json()["error"]["code"] == "CONFLICT"

    dup_email = await client_with_db.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "packer_two",
            "email": "packer.one@larose.studio",
            "password": "StrongPassword1!",
            "fullName": "Duplicate Email",
            "role": "ADMIN",
        },
    )
    assert dup_email.status_code == 409

    # 3. List users with pagination (both snake_case & camelCase) and filters
    list_res = await client_with_db.get(
        "/api/v1/users?page=1&page_size=10&role=STAFF_PACKING",
        headers=headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["total"] == 1
    assert list_data["page"] == 1
    assert list_data["pageSize"] == 10
    assert list_data["totalPages"] == 1
    assert len(list_data["items"]) == 1

    camel_list_res = await client_with_db.get(
        "/api/v1/users?page=1&pageSize=5&isActive=true",
        headers=headers,
    )
    assert camel_list_res.status_code == 200
    assert camel_list_res.json()["data"]["pageSize"] == 5
    assert camel_list_res.json()["data"]["total"] == 2

    # 4. Get user detail & 404 for unknown UUID
    detail_res = await client_with_db.get(f"/api/v1/users/{created_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["fullName"] == "Citra Packer"

    missing_res = await client_with_db.get(f"/api/v1/users/{uuid4()}", headers=headers)
    assert missing_res.status_code == 404
    assert missing_res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # 5. Update user role & fullName
    patch_res = await client_with_db.patch(
        f"/api/v1/users/{created_id}",
        headers=headers,
        json={"fullName": "Citra Senior Admin", "role": "ADMIN"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["fullName"] == "Citra Senior Admin"
    assert patch_res.json()["data"]["role"] == "ADMIN"

    # 6. Prevent owner self-deactivation
    self_del = await client_with_db.delete(f"/api/v1/users/{owner.id}", headers=headers)
    assert self_del.status_code == 409
    assert self_del.json()["error"]["code"] == "SELF_DEACTIVATION_NOT_ALLOWED"

    # 7. Soft-deactivate target user and confirm login is blocked afterwards
    del_res = await client_with_db.delete(f"/api/v1/users/{created_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["isActive"] is False

    blocked_login = await client_with_db.post(
        "/api/v1/auth/token",
        data={"username": "packer_one", "password": "StrongPassword1!"},
    )
    assert blocked_login.status_code == 401
