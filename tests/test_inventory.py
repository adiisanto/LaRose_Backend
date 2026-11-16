import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.modules.iam.models import User, UserRole


async def _seed_user(
    db_session: AsyncSession,
    *,
    username: str,
    email: str,
    role: UserRole,
    password: str = "SecretPass123!",
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=f"{role.value} User",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _get_auth_headers(
    client: AsyncClient,
    username: str,
    password: str = "SecretPass123!",
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_restock_inbound_and_movement_ledger(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Admin can restock single item inventory and verify movement ledger records entry."""
    await _seed_user(db_session, username="admin_inv", email="admin@inv.com", role=UserRole.ADMIN)
    headers = await _get_auth_headers(client_with_db, "admin_inv")

    # 1. Create single item product
    prod_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-EUCALYPTUS",
            "name": "Artificial Silver Dollar Eucalyptus",
            "productType": "SINGLE_ITEM",
            "price": 25000.00,
            "storageBin": "Rak E1",
        },
        headers=headers,
    )
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["data"]["id"]

    # 2. Restock 50 stems
    restock_payload = {
        "productId": prod_id,
        "quantity": 50,
        "notes": "Initial batch from floral supplier",
        "referenceId": "PO-202611-01",
    }
    restock_res = await client_with_db.post(
        "/api/v1/inventory/restock",
        json=restock_payload,
        headers=headers,
    )
    assert restock_res.status_code == 200
    inv_data = restock_res.json()["data"]
    assert inv_data["quantityOnHand"] == 50
    assert inv_data["quantityReserved"] == 0
    assert inv_data["quantityAvailable"] == 50
    assert inv_data["isLowStock"] is False

    # 3. Check movements ledger
    mov_res = await client_with_db.get(
        f"/api/v1/inventory/{prod_id}/movements",
        headers=headers,
    )
    assert mov_res.status_code == 200
    mov_data = mov_res.json()["data"]
    assert mov_data["total"] == 1
    item = mov_data["items"][0]
    assert item["movementType"] == "INBOUND_RESTOCK"
    assert item["deltaQuantity"] == 50
    assert item["referenceId"] == "PO-202611-01"


@pytest.mark.asyncio
async def test_inventory_low_stock_filter(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Listing inventory balances filters low stock items (quantity_available <= reorder_point)."""
    await _seed_user(db_session, username="owner_inv", email="owner@inv.com", role=UserRole.OWNER)
    headers = await _get_auth_headers(client_with_db, "owner_inv")

    # Product A: 5 on hand (reorder point default is 10 -> low stock)
    prod_a = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-LOW",
            "name": "Low Stock Daisy",
            "productType": "SINGLE_ITEM",
            "price": 5000,
        },
        headers=headers,
    )
    pid_a = prod_a.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": pid_a, "quantity": 5},
        headers=headers,
    )

    # Product B: 100 on hand (not low stock)
    prod_b = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-HIGH",
            "name": "High Stock Rose",
            "productType": "SINGLE_ITEM",
            "price": 5000,
        },
        headers=headers,
    )
    pid_b = prod_b.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": pid_b, "quantity": 100},
        headers=headers,
    )

    # Filter is_low_stock=true
    res = await client_with_db.get("/api/v1/inventory?is_low_stock=true", headers=headers)
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    skus = [i["productSku"] for i in items]
    assert "MAT-LOW" in skus
    assert "MAT-HIGH" not in skus


@pytest.mark.asyncio
async def test_staff_packing_cannot_restock(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Staff Packing role is forbidden from adding physical restock (403)."""
    await _seed_user(
        db_session,
        username="admin_st",
        email="admin_st@inv.com",
        role=UserRole.ADMIN,
    )
    await _seed_user(
        db_session,
        username="staff_st",
        email="staff_st@inv.com",
        role=UserRole.STAFF_PACKING,
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_st")
    staff_headers = await _get_auth_headers(client_with_db, "staff_st")

    prod_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-TEST-ST",
            "name": "Test Flower",
            "productType": "SINGLE_ITEM",
            "price": 5000,
        },
        headers=admin_headers,
    )
    prod_id = prod_res.json()["data"]["id"]

    # Staff Packing attempts restock -> 403 Forbidden
    res = await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": prod_id, "quantity": 10},
        headers=staff_headers,
    )
    assert res.status_code == 403
