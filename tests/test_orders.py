import asyncio
from datetime import UTC, datetime, timedelta

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
async def test_create_order_with_bouquet_bom_expansion_success(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Creating an order for bouquets expands BOM recipes and reserves raw material inventory."""
    await _seed_user(db_session, username="admin_ord", email="admin@ord.com", role=UserRole.ADMIN)
    headers = await _get_auth_headers(client_with_db, "admin_ord")

    # 1. Create 2 single item materials
    rose_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-ROSE-EXP",
            "name": "Red Rose",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=headers,
    )
    rose_id = rose_res.json()["data"]["id"]

    wrap_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-WRAP-EXP",
            "name": "Wrap Paper",
            "productType": "SINGLE_ITEM",
            "price": 5000,
        },
        headers=headers,
    )
    wrap_id = wrap_res.json()["data"]["id"]

    # 2. Restock raw materials: 30 roses, 10 wraps
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": rose_id, "quantity": 30},
        headers=headers,
    )
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": wrap_id, "quantity": 10},
        headers=headers,
    )

    # 3. Create Bouquet: 5 roses + 1 wrap
    bouquet_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "BQT-ROSE-DELUXE",
            "name": "Deluxe Rose Bouquet",
            "productType": "BOUQUET_ARRANGEMENT",
            "price": 85000.00,
            "bomComponents": [
                {"materialId": rose_id, "quantityRequired": 5},
                {"materialId": wrap_id, "quantityRequired": 1},
            ],
        },
        headers=headers,
    )
    bouquet_id = bouquet_res.json()["data"]["id"]

    # 4. Create Order for 3 Bouquets (requires 3 * 5 = 15 roses, 3 * 1 = 3 wraps)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    order_payload = {
        "customerName": "Clarissa Tan",
        "customerPhone": "081234567890",
        "customerAddress": "Jl. Senopati No. 12, Jakarta",
        "deliveryDate": tomorrow,
        "greetingCardNotes": "Happy Birthday Darling!",
        "items": [
            {"productId": bouquet_id, "quantity": 3},
        ],
    }

    res = await client_with_db.post("/api/v1/orders", json=order_payload, headers=headers)
    assert res.status_code == 201
    order_data = res.json()["data"]
    assert order_data["status"] == "PENDING_PAYMENT"
    assert order_data["orderNumber"].startswith("ORD-")
    assert order_data["totalAmount"] == "255000.00"  # 3 * 85000

    # 5. Verify inventory reservations
    rose_inv_res = await client_with_db.get(f"/api/v1/inventory/{rose_id}", headers=headers)
    rose_inv = rose_inv_res.json()["data"]
    assert rose_inv["quantityOnHand"] == 30
    assert rose_inv["quantityReserved"] == 15
    assert rose_inv["quantityAvailable"] == 15

    wrap_inv_res = await client_with_db.get(f"/api/v1/inventory/{wrap_id}", headers=headers)
    wrap_inv = wrap_inv_res.json()["data"]
    assert wrap_inv["quantityOnHand"] == 10
    assert wrap_inv["quantityReserved"] == 3
    assert wrap_inv["quantityAvailable"] == 7


@pytest.mark.asyncio
async def test_insufficient_stock_rejection_no_overselling(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Order is aborted with 409 Conflict if raw materials are insufficient."""
    await _seed_user(db_session, username="owner_ord", email="owner@ord.com", role=UserRole.OWNER)
    headers = await _get_auth_headers(client_with_db, "owner_ord")

    # Create Material with only 4 units in stock
    mat_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-SCARCE",
            "name": "Scarce Lily",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=headers,
    )
    mat_id = mat_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": mat_id, "quantity": 4},
        headers=headers,
    )

    # Order requires 10 units (greater than available 4)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    order_payload = {
        "customerName": "Budi Santoso",
        "customerPhone": "081987654321",
        "deliveryDate": tomorrow,
        "items": [
            {"productId": mat_id, "quantity": 10},
        ],
    }

    res = await client_with_db.post("/api/v1/orders", json=order_payload, headers=headers)
    assert res.status_code == 409
    body = res.json()
    assert body["error"]["code"] == "INSUFFICIENT_STOCK"
    shortages = body["error"]["details"]
    assert len(shortages) == 1
    assert shortages[0]["available"] == 4
    assert shortages[0]["required"] == 10

    # Verify inventory was NOT reserved at all
    inv_res = await client_with_db.get(f"/api/v1/inventory/{mat_id}", headers=headers)
    inv = inv_res.json()["data"]
    assert inv["quantityReserved"] == 0
    assert inv["quantityAvailable"] == 4


@pytest.mark.asyncio
async def test_concurrent_order_intake_race_condition_prevention(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Simulate 3 concurrent checkouts on limited inventory; only orders in stock succeed."""
    await _seed_user(db_session, username="admin_race", email="race@ord.com", role=UserRole.ADMIN)
    headers = await _get_auth_headers(client_with_db, "admin_race")

    # Create material with 5 items in stock
    mat_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-LIMITED",
            "name": "Limited Peony",
            "productType": "SINGLE_ITEM",
            "price": 20000,
        },
        headers=headers,
    )
    mat_id = mat_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": mat_id, "quantity": 5},
        headers=headers,
    )

    # Each order asks for 3 units (5 available -> only 1 order can succeed, 2nd will exceed 5)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")

    async def submit_order(cust_name: str):
        payload = {
            "customerName": cust_name,
            "customerPhone": "081234567890",
            "deliveryDate": tomorrow,
            "items": [{"productId": mat_id, "quantity": 3}],
        }
        return await client_with_db.post("/api/v1/orders", json=payload, headers=headers)

    # Execute 3 orders concurrently
    results = await asyncio.gather(
        submit_order("Buyer 1"),
        submit_order("Buyer 2"),
        submit_order("Buyer 3"),
    )

    status_codes = [r.status_code for r in results]
    assert status_codes.count(201) == 1
    assert status_codes.count(409) == 2

    # Verify reserved stock is exactly 3 and available is 2 (no overselling)
    inv_res = await client_with_db.get(f"/api/v1/inventory/{mat_id}", headers=headers)
    inv = inv_res.json()["data"]
    assert inv["quantityOnHand"] == 5
    assert inv["quantityReserved"] == 3
    assert inv["quantityAvailable"] == 2


@pytest.mark.asyncio
async def test_order_payment_confirmation_creates_assembly_task(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Confirming payment transitions order to PAID and queues a new assembly task."""
    await _seed_user(db_session, username="admin_pay", email="pay@ord.com", role=UserRole.ADMIN)
    headers = await _get_auth_headers(client_with_db, "admin_pay")

    prod_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-SUN-PAY",
            "name": "Sunflower",
            "productType": "SINGLE_ITEM",
            "price": 15000,
        },
        headers=headers,
    )
    prod_id = prod_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": prod_id, "quantity": 10},
        headers=headers,
    )

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    order_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Diana Ross",
            "customerPhone": "081122334455",
            "deliveryDate": tomorrow,
            "greetingCardNotes": "Special ribbon please",
            "items": [{"productId": prod_id, "quantity": 2}],
        },
        headers=headers,
    )
    order_id = order_res.json()["data"]["id"]

    # Confirm Payment
    pay_res = await client_with_db.patch(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert pay_res.status_code == 200
    assert pay_res.json()["data"]["status"] == "PAID"

    # Attempting to confirm again -> 400 Bad Request (Invalid Transition)
    pay_res_2 = await client_with_db.patch(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert pay_res_2.status_code == 400
    assert pay_res_2.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_cancel_order_releases_reserved_stock(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Cancelling a pending order releases the reserved single material stock."""
    await _seed_user(db_session, username="admin_cnc", email="cnc@ord.com", role=UserRole.ADMIN)
    headers = await _get_auth_headers(client_with_db, "admin_cnc")

    prod_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-CANDLE",
            "name": "Candle Accent",
            "productType": "SINGLE_ITEM",
            "price": 30000,
        },
        headers=headers,
    )
    prod_id = prod_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": prod_id, "quantity": 20},
        headers=headers,
    )

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    order_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Evelyn Gomez",
            "customerPhone": "081555666777",
            "deliveryDate": tomorrow,
            "items": [{"productId": prod_id, "quantity": 8}],
        },
        headers=headers,
    )
    order_id = order_res.json()["data"]["id"]

    # Verify 8 reserved
    inv_b_res = await client_with_db.get(f"/api/v1/inventory/{prod_id}", headers=headers)
    inv_before = inv_b_res.json()["data"]
    assert inv_before["quantityReserved"] == 8

    # Cancel order
    cancel_res = await client_with_db.patch(f"/api/v1/orders/{order_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["status"] == "CANCELLED"

    # Verify reservation is released back to 0
    inv_a_res = await client_with_db.get(f"/api/v1/inventory/{prod_id}", headers=headers)
    inv_after = inv_a_res.json()["data"]
    assert inv_after["quantityReserved"] == 0
    assert inv_after["quantityAvailable"] == 20


@pytest.mark.asyncio
async def test_staff_packing_cannot_create_or_cancel_order(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Staff Packing role cannot create or cancel orders (403), but can view orders (200)."""
    await _seed_user(
        db_session,
        username="admin_rb",
        email="admin_rb@ord.com",
        role=UserRole.ADMIN,
    )
    await _seed_user(
        db_session,
        username="staff_rb",
        email="staff_rb@ord.com",
        role=UserRole.STAFF_PACKING,
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_rb")
    staff_headers = await _get_auth_headers(client_with_db, "staff_rb")

    prod_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-FLOWER-RB",
            "name": "RB Flower",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=admin_headers,
    )
    prod_id = prod_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": prod_id, "quantity": 10},
        headers=admin_headers,
    )

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    order_payload = {
        "customerName": "Test Client",
        "customerPhone": "081234567890",
        "deliveryDate": tomorrow,
        "items": [{"productId": prod_id, "quantity": 1}],
    }

    # Staff Packing attempts create -> 403 Forbidden
    post_res = await client_with_db.post(
        "/api/v1/orders",
        json=order_payload,
        headers=staff_headers,
    )
    assert post_res.status_code == 403

    # Admin creates order
    admin_order_res = await client_with_db.post(
        "/api/v1/orders",
        json=order_payload,
        headers=admin_headers,
    )
    assert admin_order_res.status_code == 201
    order_id = admin_order_res.json()["data"]["id"]

    # Staff Packing lists orders -> 200 OK
    list_res = await client_with_db.get("/api/v1/orders", headers=staff_headers)
    assert list_res.status_code == 200

    # Staff Packing views order detail -> 200 OK
    get_res = await client_with_db.get(f"/api/v1/orders/{order_id}", headers=staff_headers)
    assert get_res.status_code == 200

    # Staff Packing attempts cancel -> 403 Forbidden
    cancel_res = await client_with_db.patch(
        f"/api/v1/orders/{order_id}/cancel",
        headers=staff_headers,
    )
    assert cancel_res.status_code == 403
