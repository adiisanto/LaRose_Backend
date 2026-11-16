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
async def test_assembly_queue_prioritization(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Queue sorts tasks deterministically by delivery_date ASC, created_at ASC."""
    await _seed_user(db_session, username="admin_as_q", email="as_q@asm.com", role=UserRole.ADMIN)
    await _seed_user(
        db_session, username="staff_as_q", email="st_q@asm.com", role=UserRole.STAFF_PACKING
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_as_q")
    staff_headers = await _get_auth_headers(client_with_db, "staff_as_q")

    # Create Material & Restock
    mat_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-Q-FLW",
            "name": "Queue Flower",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=admin_headers,
    )
    mat_id = mat_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": mat_id, "quantity": 100},
        headers=admin_headers,
    )

    # Create Order 1: Delivery in 3 days
    day_3 = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    ord1_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Order Later",
            "customerPhone": "081234567890",
            "deliveryDate": day_3,
            "items": [{"productId": mat_id, "quantity": 1}],
        },
        headers=admin_headers,
    )
    ord1_id = ord1_res.json()["data"]["id"]
    await client_with_db.patch(f"/api/v1/orders/{ord1_id}/payment", headers=admin_headers)

    # Create Order 2: Delivery tomorrow (should be #1 in queue)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    ord2_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Order Soonest",
            "customerPhone": "081987654321",
            "deliveryDate": tomorrow,
            "items": [{"productId": mat_id, "quantity": 1}],
        },
        headers=admin_headers,
    )
    ord2_id = ord2_res.json()["data"]["id"]
    await client_with_db.patch(f"/api/v1/orders/{ord2_id}/payment", headers=admin_headers)

    # Staff Packing inspects queue
    q_res = await client_with_db.get("/api/v1/assembly/queue", headers=staff_headers)
    assert q_res.status_code == 200
    queue_items = q_res.json()["data"]["items"]
    assert len(queue_items) >= 2
    assert queue_items[0]["orderId"] == ord2_id
    assert queue_items[1]["orderId"] == ord1_id


@pytest.mark.asyncio
async def test_claim_and_finish_assembly_deducts_physical_stock(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Staff claims task, finishes packing, physical on_hand and reserved are deducted."""
    await _seed_user(db_session, username="admin_as_f", email="as_f@asm.com", role=UserRole.ADMIN)
    await _seed_user(
        db_session, username="staff_as_f", email="st_f@asm.com", role=UserRole.STAFF_PACKING
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_as_f")
    staff_headers = await _get_auth_headers(client_with_db, "staff_as_f")

    # 1. Create materials
    r_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-FIN-ROSE",
            "name": "Rose Fin",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=admin_headers,
    )
    rose_id = r_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": rose_id, "quantity": 20},
        headers=admin_headers,
    )

    # 2. Create Bouquet: 4 roses
    b_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "BQT-FIN-BQT",
            "name": "Bouquet Fin",
            "productType": "BOUQUET_ARRANGEMENT",
            "price": 50000,
            "bomComponents": [{"materialId": rose_id, "quantityRequired": 4}],
        },
        headers=admin_headers,
    )
    b_id = b_res.json()["data"]["id"]

    # 3. Create Order for 2 bouquets (requires 8 roses)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    ord_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Michael Scott",
            "customerPhone": "081234567890",
            "deliveryDate": tomorrow,
            "items": [{"productId": b_id, "quantity": 2}],
        },
        headers=admin_headers,
    )
    ord_id = ord_res.json()["data"]["id"]
    await client_with_db.patch(f"/api/v1/orders/{ord_id}/payment", headers=admin_headers)

    # 4. Check initial reserved inventory
    inv1_res = await client_with_db.get(f"/api/v1/inventory/{rose_id}", headers=admin_headers)
    inv1 = inv1_res.json()["data"]
    assert inv1["quantityOnHand"] == 20
    assert inv1["quantityReserved"] == 8

    # 5. Get Assembly Task ID from queue
    q_res = await client_with_db.get("/api/v1/assembly/queue", headers=staff_headers)
    task_id = [t["id"] for t in q_res.json()["data"]["items"] if t["orderId"] == ord_id][0]

    # 6. Staff starts assembly
    start_res = await client_with_db.patch(
        f"/api/v1/assembly/{task_id}/start", headers=staff_headers
    )
    assert start_res.status_code == 200
    assert start_res.json()["data"]["status"] == "IN_PROGRESS"
    order_chk = (
        await client_with_db.get(f"/api/v1/orders/{ord_id}", headers=admin_headers)
    ).json()["data"]
    assert order_chk["status"] == "PROCESSING"

    # 7. Staff finishes assembly
    fin_res = await client_with_db.patch(
        f"/api/v1/assembly/{task_id}/finish", headers=staff_headers
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["data"]["status"] == "PACKED"

    order_chk2 = (
        await client_with_db.get(f"/api/v1/orders/{ord_id}", headers=admin_headers)
    ).json()["data"]
    assert order_chk2["status"] == "READY_FOR_DELIVERY"

    # 8. Verify physical stock deducted: on_hand was 20 -> 12, reserved was 8 -> 0
    inv2_res = await client_with_db.get(f"/api/v1/inventory/{rose_id}", headers=admin_headers)
    inv2 = inv2_res.json()["data"]
    assert inv2["quantityOnHand"] == 12
    assert inv2["quantityReserved"] == 0
    assert inv2["quantityAvailable"] == 12


@pytest.mark.asyncio
async def test_report_scrap_and_replacement_allocation(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Reporting damaged material deducts scrap from on_hand and reserves replacement."""
    await _seed_user(db_session, username="admin_scr", email="scr@asm.com", role=UserRole.ADMIN)
    await _seed_user(
        db_session, username="staff_scr", email="st_scr@asm.com", role=UserRole.STAFF_PACKING
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_scr")
    staff_headers = await _get_auth_headers(client_with_db, "staff_scr")

    # Create Material: 10 in stock
    m_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-SCRAP-FLW",
            "name": "Fragile Rose",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=admin_headers,
    )
    mat_id = m_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": mat_id, "quantity": 10},
        headers=admin_headers,
    )

    # Order requires 3 roses
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    ord_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Pam Beesly",
            "customerPhone": "081234567890",
            "deliveryDate": tomorrow,
            "items": [{"productId": mat_id, "quantity": 3}],
        },
        headers=admin_headers,
    )
    ord_id = ord_res.json()["data"]["id"]
    await client_with_db.patch(f"/api/v1/orders/{ord_id}/payment", headers=admin_headers)

    # Start assembly task
    q_res = await client_with_db.get("/api/v1/assembly/queue", headers=staff_headers)
    task_id = [t["id"] for t in q_res.json()["data"]["items"] if t["orderId"] == ord_id][0]
    await client_with_db.patch(f"/api/v1/assembly/{task_id}/start", headers=staff_headers)

    inv_b = (await client_with_db.get(f"/api/v1/inventory/{mat_id}", headers=admin_headers)).json()[
        "data"
    ]
    assert inv_b["quantityOnHand"] == 10
    assert inv_b["quantityReserved"] == 3

    # Report 1 stem broken
    scrap_res = await client_with_db.post(
        f"/api/v1/assembly/{task_id}/scrap",
        json={"materialId": mat_id, "quantity": 1, "reason": "Stem broke during wrapping"},
        headers=staff_headers,
    )
    assert scrap_res.status_code == 200

    inv_a = (await client_with_db.get(f"/api/v1/inventory/{mat_id}", headers=admin_headers)).json()[
        "data"
    ]
    assert inv_a["quantityOnHand"] == 9
    assert inv_a["quantityReserved"] == 4
    assert inv_a["quantityAvailable"] == 5


@pytest.mark.asyncio
async def test_full_disassembly_on_cancelled_packed_order(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Cancelling an order in READY_FOR_DELIVERY returns components to physical inventory."""
    await _seed_user(db_session, username="admin_dis", email="dis@asm.com", role=UserRole.ADMIN)
    await _seed_user(
        db_session, username="staff_dis", email="st_dis@asm.com", role=UserRole.STAFF_PACKING
    )

    admin_headers = await _get_auth_headers(client_with_db, "admin_dis")
    staff_headers = await _get_auth_headers(client_with_db, "staff_dis")

    p_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-DIS-ITEM",
            "name": "Disassembly Stem",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=admin_headers,
    )
    prod_id = p_res.json()["data"]["id"]
    await client_with_db.post(
        "/api/v1/inventory/restock",
        json={"productId": prod_id, "quantity": 10},
        headers=admin_headers,
    )

    # 2. Order 4 items
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    ord_res = await client_with_db.post(
        "/api/v1/orders",
        json={
            "customerName": "Jim Halpert",
            "customerPhone": "081122334455",
            "deliveryDate": tomorrow,
            "items": [{"productId": prod_id, "quantity": 4}],
        },
        headers=admin_headers,
    )
    ord_id = ord_res.json()["data"]["id"]
    await client_with_db.patch(f"/api/v1/orders/{ord_id}/payment", headers=admin_headers)

    # 3. Assemble and finish packing
    q_res = await client_with_db.get("/api/v1/assembly/queue", headers=staff_headers)
    task_id = [t["id"] for t in q_res.json()["data"]["items"] if t["orderId"] == ord_id][0]
    await client_with_db.patch(f"/api/v1/assembly/{task_id}/start", headers=staff_headers)
    await client_with_db.patch(f"/api/v1/assembly/{task_id}/finish", headers=staff_headers)

    # Order is READY_FOR_DELIVERY, on_hand was reduced from 10 to 6
    inv_packed = (
        await client_with_db.get(f"/api/v1/inventory/{prod_id}", headers=admin_headers)
    ).json()["data"]
    assert inv_packed["quantityOnHand"] == 6

    # 4. Customer cancels order suddenly -> Full Disassembly executed
    cancel_res = await client_with_db.patch(
        f"/api/v1/orders/{ord_id}/cancel", headers=admin_headers
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["status"] == "CANCELLED"

    # 5. Verify physical on_hand is fully restored back to 10
    inv_dis = (
        await client_with_db.get(f"/api/v1/inventory/{prod_id}", headers=admin_headers)
    ).json()["data"]
    assert inv_dis["quantityOnHand"] == 10
    assert inv_dis["quantityReserved"] == 0

    # 6. Verify ledger recorded DISASSEMBLY_RETURN
    mov_res = await client_with_db.get(
        f"/api/v1/inventory/{prod_id}/movements", headers=admin_headers
    )
    types = [m["movementType"] for m in mov_res.json()["data"]["items"]]
    assert "DISASSEMBLY_RETURN" in types
