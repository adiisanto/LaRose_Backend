import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ProductType(StrEnum):
    """Supported product classifications in LaRose Floral Studio."""

    SINGLE_ITEM = "SINGLE_ITEM"
    BOUQUET_ARRANGEMENT = "BOUQUET_ARRANGEMENT"


class Product(Base):
    """Product entity representing single materials or assembled bouquets."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint("price >= 0", name="chk_products_price_non_negative"),
        Index("idx_products_type_active", "product_type", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    sku: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(
            ProductType,
            name="product_type",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    storage_bin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_premade: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationships
    bom_components: Mapped[list["BOMComponent"]] = relationship(
        "BOMComponent",
        foreign_keys="BOMComponent.bouquet_id",
        back_populates="bouquet",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BOMComponent(Base):
    """Bill of Materials recipe item mapping raw materials into a bouquet."""

    __tablename__ = "bom_components"
    __table_args__ = (
        UniqueConstraint("bouquet_id", "material_id", name="uq_bom_bouquet_material"),
        CheckConstraint("quantity_required > 0", name="chk_bom_qty_positive"),
        CheckConstraint("bouquet_id <> material_id", name="chk_bom_prevent_self_reference"),
        Index("idx_bom_bouquet_id", "bouquet_id"),
        Index("idx_bom_material_id", "material_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    bouquet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_required: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    # Relationships
    bouquet: Mapped["Product"] = relationship(
        "Product",
        foreign_keys=[bouquet_id],
        back_populates="bom_components",
    )
    material: Mapped["Product"] = relationship(
        "Product",
        foreign_keys=[material_id],
        lazy="selectin",
    )
