import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class MovementType(StrEnum):
    """Categorization of stock ledger mutations."""

    INBOUND_RESTOCK = "INBOUND_RESTOCK"
    ORDER_RESERVED = "ORDER_RESERVED"
    ORDER_RELEASED = "ORDER_RELEASED"
    ASSEMBLY_DEDUCTED = "ASSEMBLY_DEDUCTED"
    SCRAP_DAMAGED = "SCRAP_DAMAGED"
    DISASSEMBLY_RETURN = "DISASSEMBLY_RETURN"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"


class Inventory(Base):
    """Inventory balance tracking physical and reserved quantities per product."""

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_inventory_product"),
        CheckConstraint("quantity_on_hand >= 0", name="chk_inv_on_hand_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="chk_inv_reserved_non_negative"),
        CheckConstraint(
            "quantity_reserved <= quantity_on_hand",
            name="chk_inv_reserved_lte_on_hand",
        ),
        CheckConstraint("reorder_point >= 0", name="chk_inv_reorder_point_non_negative"),
        Index("idx_inventory_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    quantity_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    reorder_point: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default=text("10"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    # Relationships
    product = relationship("Product", foreign_keys=[product_id], lazy="selectin")
    movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement",
        back_populates="inventory",
        cascade="all, delete-orphan",
        order_by="desc(StockMovement.created_at)",
    )


class StockMovement(Base):
    """Immutable ledger recording all physical stock mutations."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("delta_quantity <> 0", name="chk_movement_delta_nonzero"),
        Index("idx_stock_movements_inv_date", "inventory_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory.id", ondelete="CASCADE"),
        nullable=False,
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(
            MovementType,
            name="movement_type",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    delta_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    # Relationships
    inventory: Mapped["Inventory"] = relationship("Inventory", back_populates="movements")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")
