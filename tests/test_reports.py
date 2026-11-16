"""Integration tests for Reports, Executive Dashboard, and Critical Alerts."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
async def test_executive_dashboard_aggregation(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Test executive dashboard metrics: total revenue, order counts, and top selling products."""
    suffix = uuid.uuid4().hex[:6]
    await _seed_user(
        db_session,
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@larose.id",
        role=UserRole.OWNER,
    )
    headers = await _get_auth_headers(client_with_db, f"owner_{suffix}")

    # 1. Create a single item product
    sku_stem = f"STEM-{uuid.uuid4().hex[:6]}"
    create_prod = await client_with_db.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "sku": sku_stem,
            "name": "Luxury Stem Rose",
            "productType": "SINGLE_ITEM",
            "price": "35000.00",
            "storageBin": "BIN-R1",
        },
    )
    assert create_prod.status_code == 201
    prod_id = create_prod.json()["data"]["id"]

    # 2. Inbound restock
    restock = await client_with_db.post(
        "/api/v1/inventory/restock",
        headers=headers,
        json={
            "productId": prod_id,
            "quantity": 100,
            "notes": "Restock for dashboard tests",
        },
    )
    assert restock.status_code == 200

    # 3. Create an order and pay
    deliv_date = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    order_res = await client_with_db.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "customerName": "Executive Client",
            "customerPhone": "081234567899",
            "deliveryDate": deliv_date,
            "items": [{"productId": prod_id, "quantity": 4}],
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["data"]["id"]

    # Pay order -> status PAID (revenue 4 * 35,000 = 140,000)
    pay_res = await client_with_db.patch(
        f"/api/v1/orders/{order_id}/payment",
        headers=headers,
    )
    assert pay_res.status_code == 200

    # 4. Query executive dashboard
    dashboard_res = await client_with_db.get(
        "/api/v1/reports/executive-dashboard",
        headers=headers,
    )
    assert dashboard_res.status_code == 200
    data = dashboard_res.json()["data"]

    assert data["totalOrders"] >= 1
    assert Decimal(str(data["totalRevenue"])) >= Decimal("140000.00")
    assert any(item["status"] == "PAID" for item in data["ordersByStatus"])
    assert any(top["productId"] == prod_id for top in data["topSellingProducts"])


@pytest.mark.asyncio
async def test_inventory_valuation_metrics(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Test warehouse inventory valuation calculations."""
    suffix = uuid.uuid4().hex[:6]
    await _seed_user(
        db_session,
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@larose.id",
        role=UserRole.OWNER,
    )
    headers = await _get_auth_headers(client_with_db, f"owner_{suffix}")

    # Seed at least 1 product
    sku_val = f"VAL-{uuid.uuid4().hex[:6]}"
    create_prod = await client_with_db.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "sku": sku_val,
            "name": "Valuation Test Item",
            "productType": "SINGLE_ITEM",
            "price": "50000.00",
            "storageBin": "BIN-V1",
        },
    )
    assert create_prod.status_code == 201
    prod_id = create_prod.json()["data"]["id"]

    # Restock 10 units
    await client_with_db.post(
        "/api/v1/inventory/restock",
        headers=headers,
        json={
            "productId": prod_id,
            "quantity": 10,
            "notes": "Valuation restock",
        },
    )

    val_res = await client_with_db.get(
        "/api/v1/reports/inventory-valuation",
        headers=headers,
    )
    assert val_res.status_code == 200
    val_data = val_res.json()["data"]

    assert val_data["totalTrackedItems"] >= 1
    assert val_data["totalUnitsOnHand"] >= 0
    assert Decimal(str(val_data["totalWorkingCapitalValuation"])) >= Decimal("0.00")
    assert len(val_data["items"]) >= 1


@pytest.mark.asyncio
async def test_low_stock_critical_alerts(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Test low stock alert detection and reorder recommendations."""
    suffix = uuid.uuid4().hex[:6]
    await _seed_user(
        db_session,
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@larose.id",
        role=UserRole.OWNER,
    )
    headers = await _get_auth_headers(client_with_db, f"owner_{suffix}")

    # Create low stock item (on-hand 0, default reorder point 10 -> CRITICAL alert)
    sku_critical = f"CRIT-{uuid.uuid4().hex[:6]}"
    create_prod = await client_with_db.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "sku": sku_critical,
            "name": "Critical Low Stock Ribbon",
            "productType": "SINGLE_ITEM",
            "price": "12000.00",
            "storageBin": "BIN-CRIT",
        },
    )
    assert create_prod.status_code == 201
    crit_id = create_prod.json()["data"]["id"]

    alert_res = await client_with_db.get(
        "/api/v1/reports/low-stock-alerts",
        headers=headers,
    )
    assert alert_res.status_code == 200
    alert_data = alert_res.json()["data"]

    assert alert_data["totalAlertItems"] >= 1
    assert alert_data["criticalItemsCount"] >= 1

    matching = [a for a in alert_data["alerts"] if a["productId"] == crit_id]
    assert len(matching) == 1
    assert matching[0]["alertLevel"] == "CRITICAL"
    assert matching[0]["availableQuantity"] == 0
    assert matching[0]["recommendedReorderQty"] >= 10


@pytest.mark.asyncio
async def test_staff_packing_cannot_access_reports(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Staff Packing is strictly forbidden from accessing financial/executive reports."""
    suffix = uuid.uuid4().hex[:6]
    await _seed_user(
        db_session,
        username=f"staff_{suffix}",
        email=f"staff_{suffix}@larose.id",
        role=UserRole.STAFF_PACKING,
    )
    headers = await _get_auth_headers(client_with_db, f"staff_{suffix}")

    endpoints = [
        "/api/v1/reports/executive-dashboard",
        "/api/v1/reports/inventory-valuation",
        "/api/v1/reports/low-stock-alerts",
    ]

    for ep in endpoints:
        res = await client_with_db.get(ep, headers=headers)
        assert res.status_code == 403
        err = res.json()
        assert err["success"] is False
        assert err["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
