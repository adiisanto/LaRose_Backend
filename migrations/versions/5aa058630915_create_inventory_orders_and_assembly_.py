"""create inventory orders and assembly tables

Revision ID: 5aa058630915
Revises: 065ec64c5b0c
Create Date: 2026-11-16 14:33:14.796223

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5aa058630915"
down_revision: str | Sequence[str] | None = "065ec64c5b0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "inventory",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "quantity_reserved",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("reorder_point", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity_on_hand >= 0", name="chk_inv_on_hand_non_negative"),
        sa.CheckConstraint(
            "quantity_reserved <= quantity_on_hand",
            name="chk_inv_reserved_lte_on_hand",
        ),
        sa.CheckConstraint("quantity_reserved >= 0", name="chk_inv_reserved_non_negative"),
        sa.CheckConstraint("reorder_point >= 0", name="chk_inv_reorder_point_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_inventory_product"),
    )
    op.create_index("idx_inventory_product_id", "inventory", ["product_id"], unique=False)

    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_number", sa.String(length=50), nullable=False),
        sa.Column("customer_name", sa.String(length=100), nullable=False),
        sa.Column("customer_phone", sa.String(length=30), nullable=False),
        sa.Column("customer_address", sa.Text(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PENDING_PAYMENT",
                "PAID",
                "PROCESSING",
                "READY_FOR_DELIVERY",
                "COMPLETED",
                "CANCELLED",
                name="order_status",
                create_constraint=True,
            ),
            server_default=sa.text("'PENDING_PAYMENT'"),
            nullable=False,
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column("greeting_card_notes", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("total_amount >= 0", name="chk_orders_total_non_negative"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
    )
    op.create_index(
        "idx_orders_delivery_date",
        "orders",
        ["delivery_date", "created_at"],
        unique=False,
    )
    op.create_index("idx_orders_status", "orders", ["status"], unique=False)

    op.create_table(
        "assembly_tasks",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_staff_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "IN_PROGRESS",
                "PACKED",
                "CANCELLED",
                name="task_status",
                create_constraint=True,
            ),
            server_default=sa.text("'QUEUED'"),
            nullable=False,
        ),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["assigned_staff_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_assembly_status_priority",
        "assembly_tasks",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "order_items",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="chk_order_items_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="chk_order_items_price_non_negative"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_order_items_order_id", "order_items", ["order_id"], unique=False)

    op.create_table(
        "stock_movements",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column(
            "movement_type",
            sa.Enum(
                "INBOUND_RESTOCK",
                "ORDER_RESERVED",
                "ORDER_RELEASED",
                "ASSEMBLY_DEDUCTED",
                "SCRAP_DAMAGED",
                "DISASSEMBLY_RETURN",
                "INVENTORY_ADJUSTMENT",
                name="movement_type",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("delta_quantity", sa.Integer(), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("delta_quantity <> 0", name="chk_movement_delta_nonzero"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventory.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_stock_movements_inv_date",
        "stock_movements",
        ["inventory_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_stock_movements_inv_date", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("idx_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("idx_assembly_status_priority", table_name="assembly_tasks")
    op.drop_table("assembly_tasks")
    op.drop_index("idx_orders_status", table_name="orders")
    op.drop_index("idx_orders_delivery_date", table_name="orders")
    op.drop_table("orders")
    op.drop_index("idx_inventory_product_id", table_name="inventory")
    op.drop_table("inventory")
