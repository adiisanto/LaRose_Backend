"""Realistic Studio Database Seeder.

Populates initial administrative and operational accounts, raw floral materials,
wrapping paper, satin ribbons, composite bouquet catalog with verified BOM recipes,
and realistic warehouse stock balances.
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.core.security import hash_password
from src.modules.catalog.models import BOMComponent, Product, ProductType
from src.modules.iam.models import User, UserRole
from src.modules.inventory.models import Inventory, MovementType, StockMovement

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seeder")

DEFAULT_PASSWORD = "Password123!"

# ============================================================================
# 1. STUDIO ACCOUNTS (3 Core Roles)
# ============================================================================
SEED_USERS = [
    {
        "username": "owner",
        "email": "owner@larose.id",
        "full_name": "Siti Nurhaliza (Owner)",
        "role": UserRole.OWNER,
    },
    {
        "username": "admin",
        "email": "admin@larose.id",
        "full_name": "Budi Santoso (Store Admin)",
        "role": UserRole.ADMIN,
    },
    {
        "username": "staff_packing",
        "email": "packing@larose.id",
        "full_name": "Dewi Lestari (Packing & Assembly)",
        "role": UserRole.STAFF_PACKING,
    },
]

# ============================================================================
# 2. RAW MATERIALS & ACCESSORIES (10 Single Items)
# ============================================================================
SEED_MATERIALS = [
    {
        "sku": "MAT-ROSE-RED",
        "name": "Rose Velvet Merah Artifisial (Premium Stem)",
        "description": "Tangkai bunga mawar beludru merah kualitas ekspor, kawat lentur",
        "price": Decimal("25000.00"),
        "storage_bin": "Rak B1-01",
        "stock_qty": 200,
        "reorder_point": 30,
    },
    {
        "sku": "MAT-ROSE-WHT",
        "name": "Rose Velvet Putih Bersih Artifisial",
        "description": "Tangkai mawar beludru putih gading untuk wedding & buket elegan",
        "price": Decimal("25000.00"),
        "storage_bin": "Rak B1-02",
        "stock_qty": 150,
        "reorder_point": 25,
    },
    {
        "sku": "MAT-ROSE-PNK",
        "name": "Rose Silk Soft Pink Artifisial",
        "description": "Mawar sutra kelopak gradasi baby pink lembut",
        "price": Decimal("22000.00"),
        "storage_bin": "Rak B1-03",
        "stock_qty": 180,
        "reorder_point": 25,
    },
    {
        "sku": "MAT-PEONY-WHT",
        "name": "Peony Bloom Putih Mewah",
        "description": "Bunga peony kelopak tumpuk mekar mekar penuh warna putih klasik",
        "price": Decimal("35000.00"),
        "storage_bin": "Rak B2-01",
        "stock_qty": 120,
        "reorder_point": 20,
    },
    {
        "sku": "MAT-LILY-WHT",
        "name": "Casablanca Lily Artifisial Putih",
        "description": "Tangkai lily putih 3 kuntum mekar dengan putik kuning alami",
        "price": Decimal("38000.00"),
        "storage_bin": "Rak B2-02",
        "stock_qty": 90,
        "reorder_point": 15,
    },
    {
        "sku": "MAT-EUCAL-GRN",
        "name": "Daun Eucalyptus Artifisial Daun Perak (Silver Dollar)",
        "description": "Filler daun perak alami bertekstur matte realistis",
        "price": Decimal("15000.00"),
        "storage_bin": "Rak D1-01",
        "stock_qty": 250,
        "reorder_point": 40,
    },
    {
        "sku": "MAT-BABYB-WHT",
        "name": "Baby's Breath Putih Kering Sintetis",
        "description": "Bunga pengisi putih kecil tahan rontok dan tahan lembap",
        "price": Decimal("18000.00"),
        "storage_bin": "Rak D1-02",
        "stock_qty": 300,
        "reorder_point": 50,
    },
    {
        "sku": "ACC-WRAP-KRAFT",
        "name": "Kertas Wrapping Cellophane Korean Kraft (Matte)",
        "description": "Kertas pembungkus anti-air motif matte gaya Korea",
        "price": Decimal("8000.00"),
        "storage_bin": "Rak W1-01",
        "stock_qty": 400,
        "reorder_point": 50,
    },
    {
        "sku": "ACC-WRAP-BLUSH",
        "name": "Kertas Wrapping Frosted Film Pastel Blush Pink",
        "description": "Lembar wrapping transparan buram warna dusty pink",
        "price": Decimal("9000.00"),
        "storage_bin": "Rak W1-02",
        "stock_qty": 350,
        "reorder_point": 50,
    },
    {
        "sku": "ACC-RIBBON-GOLD",
        "name": "Pita Satin Emas Mewah (Roll 2.5cm x 2m)",
        "description": "Pita satin berkilau tebal warna emas sampanye",
        "price": Decimal("6000.00"),
        "storage_bin": "Rak P1-01",
        "stock_qty": 500,
        "reorder_point": 60,
    },
]

# ============================================================================
# 3. POPULAR BOUQUET ARRANGEMENTS WITH BOM RECIPES (3 Composite Bouquets)
# ============================================================================
SEED_BOUQUETS = [
    {
        "sku": "BQT-VELVET-PASSION",
        "name": "Velvet Passion Grand Bouquet (10 Red Roses)",
        "description": "Rangkaian megah 10 mawar beludru merah dengan eucalyptus dan pita emas",
        "price": Decimal("385000.00"),
        "storage_bin": "Display Depan A",
        "is_premade": False,
        "recipe": [
            ("MAT-ROSE-RED", 10),
            ("MAT-EUCAL-GRN", 3),
            ("MAT-BABYB-WHT", 2),
            ("ACC-WRAP-KRAFT", 3),
            ("ACC-RIBBON-GOLD", 1),
        ],
    },
    {
        "sku": "BQT-PASTEL-DREAM",
        "name": "Pastel Romance Deluxe Bouquet",
        "description": "Kombinasi lembut mawar pink, peony mekar, dan baby breath gaya feminin",
        "price": Decimal("340000.00"),
        "storage_bin": "Display Depan B",
        "is_premade": False,
        "recipe": [
            ("MAT-ROSE-PNK", 6),
            ("MAT-PEONY-WHT", 3),
            ("MAT-BABYB-WHT", 3),
            ("ACC-WRAP-BLUSH", 3),
            ("ACC-RIBBON-GOLD", 1),
        ],
    },
    {
        "sku": "BQT-SERENITY-LILY",
        "name": "White Serenity Lily & Rose Symphony",
        "description": "Koleksi formal mewah lily putih dan mawar putih dengan wrapping frosted",
        "price": Decimal("420000.00"),
        "storage_bin": "Display Depan C",
        "is_premade": False,
        "recipe": [
            ("MAT-LILY-WHT", 4),
            ("MAT-ROSE-WHT", 6),
            ("MAT-EUCAL-GRN", 4),
            ("ACC-WRAP-KRAFT", 2),
            ("ACC-WRAP-BLUSH", 2),
            ("ACC-RIBBON-GOLD", 1),
        ],
    },
]


async def seed_users(session: AsyncSession) -> dict[str, User]:
    """Seed studio user accounts idempotently."""
    user_map = {}
    for data in SEED_USERS:
        result = await session.execute(select(User).where(User.username == data["username"]))
        existing = result.scalar_one_or_none()
        if not existing:
            user = User(
                username=data["username"],
                email=data["email"],
                password_hash=hash_password(DEFAULT_PASSWORD),
                full_name=data["full_name"],
                role=data["role"],
                is_active=True,
            )
            session.add(user)
            await session.flush()
            user_map[data["username"]] = user
            logger.info("Created user account: %s (%s)", user.username, user.role.value)
        else:
            user_map[data["username"]] = existing
            logger.info("User already exists: %s", existing.username)
    return user_map


async def seed_materials(session: AsyncSession, admin_user: User) -> dict[str, Product]:
    """Seed raw material single products and initialize inventory idempotently."""
    material_map = {}
    for mat in SEED_MATERIALS:
        result = await session.execute(select(Product).where(Product.sku == mat["sku"]))
        existing = result.scalar_one_or_none()
        if not existing:
            product = Product(
                sku=mat["sku"],
                name=mat["name"],
                description=mat["description"],
                product_type=ProductType.SINGLE_ITEM,
                price=mat["price"],
                storage_bin=mat["storage_bin"],
                is_premade=False,
                is_active=True,
            )
            session.add(product)
            await session.flush()

            # Initialize Inventory balance
            inv = Inventory(
                product_id=product.id,
                quantity_on_hand=mat["stock_qty"],
                quantity_reserved=0,
                reorder_point=mat["reorder_point"],
            )
            session.add(inv)
            await session.flush()

            # Record Inbound Restock ledger entry
            movement = StockMovement(
                inventory_id=inv.id,
                movement_type=MovementType.INBOUND_RESTOCK,
                delta_quantity=mat["stock_qty"],
                reference_id="SEED-INIT-STOCK",
                notes="Initial studio stock balance from realistic seeder",
                created_by_user_id=admin_user.id,
            )
            session.add(movement)
            material_map[mat["sku"]] = product
            logger.info(
                "Created material product: %s with initial stock %d",
                product.sku,
                mat["stock_qty"],
            )
        else:
            material_map[mat["sku"]] = existing
            logger.info("Material product already exists: %s", existing.sku)

    return material_map


async def seed_bouquets(session: AsyncSession, material_map: dict[str, Product]) -> None:
    """Seed composite bouquet arrangements and attach BOM recipes idempotently."""
    for bqt in SEED_BOUQUETS:
        result = await session.execute(select(Product).where(Product.sku == bqt["sku"]))
        existing = result.scalar_one_or_none()
        if not existing:
            product = Product(
                sku=bqt["sku"],
                name=bqt["name"],
                description=bqt["description"],
                product_type=ProductType.BOUQUET_ARRANGEMENT,
                price=bqt["price"],
                storage_bin=bqt["storage_bin"],
                is_premade=bqt["is_premade"],
                is_active=True,
            )
            session.add(product)
            await session.flush()

            # Attach BOM components
            for mat_sku, qty in bqt["recipe"]:
                mat = material_map.get(mat_sku)
                if mat:
                    comp = BOMComponent(
                        bouquet_id=product.id,
                        material_id=mat.id,
                        quantity_required=qty,
                    )
                    session.add(comp)

            logger.info(
                "Created bouquet arrangement: %s with %d BOM components",
                product.sku,
                len(bqt["recipe"]),
            )
        else:
            logger.info("Bouquet already exists: %s", existing.sku)


async def run_seed() -> None:
    """Run full idempotent database seeding process."""
    logger.info("=== Starting Realistic Studio Seeder ===")
    async with async_session_factory() as session:
        try:
            users = await seed_users(session)
            admin_user = users.get("admin") or users.get("owner")
            materials = await seed_materials(session, admin_user)
            await seed_bouquets(session, materials)
            await session.commit()
            logger.info("=== Seeding Completed Successfully! ===")
        except Exception:
            await session.rollback()
            logger.exception("Seeding encountered fatal error and was rolled back.")
            raise


if __name__ == "__main__":
    asyncio.run(run_seed())
