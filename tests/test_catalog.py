from decimal import Decimal
from uuid import uuid4

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
async def test_create_single_item_product_success(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Admin can create a single item product with SKU, price, and storage bin."""
    await _seed_user(
        db_session,
        username="admin_cat",
        email="admin@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_cat")

    payload = {
        "sku": "FLW-ROSE-RED",
        "name": "Artificial Red Velvet Rose",
        "description": "Premium silk red rose stem 45cm",
        "productType": "SINGLE_ITEM",
        "price": 15000.00,
        "storageBin": "Rak B2",
        "isPremade": False,
    }

    res = await client_with_db.post("/api/v1/catalog/products", json=payload, headers=headers)
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["sku"] == "FLW-ROSE-RED"
    assert data["name"] == "Artificial Red Velvet Rose"
    assert data["productType"] == "SINGLE_ITEM"
    assert Decimal(str(data["price"])) == Decimal("15000")
    assert data["storageBin"] == "Rak B2"
    assert data["isActive"] is True


@pytest.mark.asyncio
async def test_duplicate_sku_rejection(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Attempting to create product with duplicate SKU returns 409 conflict."""
    await _seed_user(
        db_session,
        username="owner_cat",
        email="owner@cat.com",
        role=UserRole.OWNER,
    )
    headers = await _get_auth_headers(client_with_db, "owner_cat")

    payload = {
        "sku": "FLW-ROSE-WHT",
        "name": "White Silk Rose",
        "productType": "SINGLE_ITEM",
        "price": 14000.00,
    }

    res1 = await client_with_db.post("/api/v1/catalog/products", json=payload, headers=headers)
    assert res1.status_code == 201

    res2 = await client_with_db.post("/api/v1/catalog/products", json=payload, headers=headers)
    assert res2.status_code == 409
    body = res2.json()
    assert body["error"]["code"] == "SKU_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_single_item_cannot_have_bom_components(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """SINGLE_ITEM products cannot be created with BOM components."""
    await _seed_user(
        db_session,
        username="admin_cat2",
        email="admin2@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_cat2")

    payload = {
        "sku": "FLW-DAISY-01",
        "name": "Daisy Flower",
        "productType": "SINGLE_ITEM",
        "price": 8000.00,
        "bomComponents": [
            {"materialId": str(uuid4()), "quantityRequired": 1},
        ],
    }

    res = await client_with_db.post("/api/v1/catalog/products", json=payload, headers=headers)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_BOM_ASSIGNMENT"


@pytest.mark.asyncio
async def test_create_bouquet_with_bom_components_success(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Owner can create a bouquet arrangement composed of 3 raw materials."""
    await _seed_user(
        db_session,
        username="owner_cat2",
        email="owner2@cat.com",
        role=UserRole.OWNER,
    )
    headers = await _get_auth_headers(client_with_db, "owner_cat2")

    # 1. Create 3 single items
    m1_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-ROSE-RED",
            "name": "Red Rose Stem",
            "productType": "SINGLE_ITEM",
            "price": 12000,
            "storageBin": "Rak B1",
        },
        headers=headers,
    )
    m1_id = m1_res.json()["data"]["id"]

    m2_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-CELL-WHT",
            "name": "White Cellophane",
            "productType": "SINGLE_ITEM",
            "price": 5000,
            "storageBin": "Rak W1",
        },
        headers=headers,
    )
    m2_id = m2_res.json()["data"]["id"]

    m3_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "MAT-RIB-GLD",
            "name": "Gold Satin Ribbon",
            "productType": "SINGLE_ITEM",
            "price": 3000,
            "storageBin": "Rak R2",
        },
        headers=headers,
    )
    m3_id = m3_res.json()["data"]["id"]

    # 2. Create Bouquet using BOM
    bouquet_payload = {
        "sku": "BQT-VELVET-ROSE",
        "name": "Velvet Rose Special Bouquet",
        "description": "5 red roses wrapped in white cellophane and gold ribbon",
        "productType": "BOUQUET_ARRANGEMENT",
        "price": 125000.00,
        "isPremade": False,
        "bomComponents": [
            {"materialId": m1_id, "quantityRequired": 5},
            {"materialId": m2_id, "quantityRequired": 2},
            {"materialId": m3_id, "quantityRequired": 1},
        ],
    }

    res = await client_with_db.post(
        "/api/v1/catalog/products",
        json=bouquet_payload,
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["sku"] == "BQT-VELVET-ROSE"
    assert data["productType"] == "BOUQUET_ARRANGEMENT"
    assert len(data["bomComponents"]) == 3

    # Check component details mapped
    components_by_id = {c["materialId"]: c for c in data["bomComponents"]}
    assert components_by_id[m1_id]["materialName"] == "Red Rose Stem"
    assert components_by_id[m1_id]["quantityRequired"] == 5
    assert components_by_id[m1_id]["storageBin"] == "Rak B1"


@pytest.mark.asyncio
async def test_nested_bouquet_rejection(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """BOM recipe rejects using another bouquet as a component material."""
    await _seed_user(
        db_session,
        username="admin_nest",
        email="nest@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_nest")

    # Create Single Item
    s_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-LILY",
            "name": "Lily Flower",
            "productType": "SINGLE_ITEM",
            "price": 10000,
        },
        headers=headers,
    )
    single_id = s_res.json()["data"]["id"]

    # Create Bouquet 1
    b1_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "BQT-MINI-01",
            "name": "Mini Lily Bouquet",
            "productType": "BOUQUET_ARRANGEMENT",
            "price": 50000,
            "bomComponents": [{"materialId": single_id, "quantityRequired": 3}],
        },
        headers=headers,
    )
    b1_id = b1_res.json()["data"]["id"]

    # Create Bouquet 2 attempting to include Bouquet 1
    b2_payload = {
        "sku": "BQT-SUPER-01",
        "name": "Super Bouquet",
        "productType": "BOUQUET_ARRANGEMENT",
        "price": 150000,
        "bomComponents": [
            {"materialId": b1_id, "quantityRequired": 1},
        ],
    }
    res = await client_with_db.post("/api/v1/catalog/products", json=b2_payload, headers=headers)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_BOM_MATERIAL_TYPE"


@pytest.mark.asyncio
async def test_update_and_self_referencing_bom_rejection(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Updating a bouquet to include itself in BOM components is rejected."""
    await _seed_user(
        db_session,
        username="admin_self",
        email="self@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_self")

    mat_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={"sku": "MAT-STEM-01", "name": "Stem", "productType": "SINGLE_ITEM", "price": 5000},
        headers=headers,
    )
    mat_id = mat_res.json()["data"]["id"]

    b_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "BQT-SELF-01",
            "name": "Self Check Bouquet",
            "productType": "BOUQUET_ARRANGEMENT",
            "price": 60000,
            "bomComponents": [{"materialId": mat_id, "quantityRequired": 2}],
        },
        headers=headers,
    )
    bouquet_id = b_res.json()["data"]["id"]

    # Attempt to update BOM with bouquet's own ID
    update_payload = {
        "bomComponents": [
            {"materialId": bouquet_id, "quantityRequired": 1},
        ]
    }
    res = await client_with_db.put(
        f"/api/v1/catalog/products/{bouquet_id}",
        json=update_payload,
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SELF_REFERENCING_BOM"


@pytest.mark.asyncio
async def test_list_products_and_search_filter(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Listing products supports productType filter, search query, and pagination."""
    await _seed_user(
        db_session,
        username="admin_list",
        email="list@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_list")

    await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-ORCHID",
            "name": "White Orchid",
            "productType": "SINGLE_ITEM",
            "price": 20000,
        },
        headers=headers,
    )
    await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-TULIP",
            "name": "Pink Tulip",
            "productType": "SINGLE_ITEM",
            "price": 18000,
        },
        headers=headers,
    )

    # Search for "orchid"
    res = await client_with_db.get("/api/v1/catalog/products?search=orchid", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "FLW-ORCHID"


@pytest.mark.asyncio
async def test_soft_delete_product(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Soft delete sets is_active=False without physically deleting row."""
    await _seed_user(
        db_session,
        username="admin_del",
        email="del@cat.com",
        role=UserRole.ADMIN,
    )
    headers = await _get_auth_headers(client_with_db, "admin_del")

    create_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-PEONY",
            "name": "Peony Silk Flower",
            "productType": "SINGLE_ITEM",
            "price": 22000,
        },
        headers=headers,
    )
    prod_id = create_res.json()["data"]["id"]

    del_res = await client_with_db.delete(f"/api/v1/catalog/products/{prod_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["isActive"] is False

    # Verify get by ID still returns inactive product
    get_res = await client_with_db.get(f"/api/v1/catalog/products/{prod_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["isActive"] is False


@pytest.mark.asyncio
async def test_staff_packing_role_permissions(
    client_with_db: AsyncClient,
    db_session: AsyncSession,
):
    """Staff Packing can read products but is forbidden from creating/updating/deleting."""
    await _seed_user(
        db_session,
        username="owner_perm",
        email="owner_perm@cat.com",
        role=UserRole.OWNER,
    )
    await _seed_user(
        db_session,
        username="staff_perm",
        email="staff_perm@cat.com",
        role=UserRole.STAFF_PACKING,
    )

    owner_headers = await _get_auth_headers(client_with_db, "owner_perm")
    staff_headers = await _get_auth_headers(client_with_db, "staff_perm")

    # Owner creates product
    create_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-SUNFLOWER",
            "name": "Sunflower Stem",
            "productType": "SINGLE_ITEM",
            "price": 16000,
        },
        headers=owner_headers,
    )
    prod_id = create_res.json()["data"]["id"]

    # Staff Packing lists products -> 200 OK
    list_res = await client_with_db.get("/api/v1/catalog/products", headers=staff_headers)
    assert list_res.status_code == 200

    # Staff Packing gets product by ID -> 200 OK
    get_res = await client_with_db.get(f"/api/v1/catalog/products/{prod_id}", headers=staff_headers)
    assert get_res.status_code == 200

    # Staff Packing attempts to create product -> 403 Forbidden
    post_res = await client_with_db.post(
        "/api/v1/catalog/products",
        json={
            "sku": "FLW-FORBIDDEN",
            "name": "Forbidden Item",
            "productType": "SINGLE_ITEM",
            "price": 1000,
        },
        headers=staff_headers,
    )
    assert post_res.status_code == 403

    # Staff Packing attempts to delete -> 403 Forbidden
    del_res = await client_with_db.delete(
        f"/api/v1/catalog/products/{prod_id}",
        headers=staff_headers,
    )
    assert del_res.status_code == 403
