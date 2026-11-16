"""create products and bom_components tables

Revision ID: 065ec64c5b0c
Revises: dffea7f27119
Create Date: 2026-11-16 11:00:14.136923

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "065ec64c5b0c"
down_revision: str | Sequence[str] | None = "dffea7f27119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "products",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "product_type",
            sa.Enum(
                "SINGLE_ITEM",
                "BOUQUET_ARRANGEMENT",
                name="product_type",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("storage_bin", sa.String(length=50), nullable=True),
        sa.Column("is_premade", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("price >= 0", name="chk_products_price_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index(
        "idx_products_type_active",
        "products",
        ["product_type", "is_active"],
        unique=False,
    )
    op.create_table(
        "bom_components",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("bouquet_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_required", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("bouquet_id <> material_id", name="chk_bom_prevent_self_reference"),
        sa.CheckConstraint("quantity_required > 0", name="chk_bom_qty_positive"),
        sa.ForeignKeyConstraint(["bouquet_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bouquet_id", "material_id", name="uq_bom_bouquet_material"),
    )
    op.create_index("idx_bom_bouquet_id", "bom_components", ["bouquet_id"], unique=False)
    op.create_index("idx_bom_material_id", "bom_components", ["material_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_bom_material_id", table_name="bom_components")
    op.drop_index("idx_bom_bouquet_id", table_name="bom_components")
    op.drop_table("bom_components")
    op.drop_index("idx_products_type_active", table_name="products")
    op.drop_table("products")
