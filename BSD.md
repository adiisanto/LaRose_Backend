# Backend Schema Document (BSD)
## LaRose Floral Studio — Database DDL, Pydantic v2 Contracts & API Data Specifications

---

### 1. Prinsip Kontrak Data & Kebijakan Arsitektur (Data Contract Principles)

Seluruh lapisan data backend mematuhi lima aturan mutlak berikut:

1. **Strategi Primary Key (UUID v4)**:
   * Seluruh entitas tabel menggunakan `UUID` berbasis `gen_random_uuid()` di PostgreSQL.
   * Menghindari kerentanan *ID enumeration attack*, aman diekspos ke antarmuka web publik, dan mempermudah replikasi masa depan.
2. **Kebijakan Penghapusan Hybrid (Hybrid Deletion Policy)**:
   * **Master Data (Soft Delete)**: Tabel `users`, `products`, dan `bom_components` menggunakan kolom `is_active BOOLEAN` dan `deleted_at TIMESTAMP WITH TIME ZONE`. Data tidak dihapus secara fisik untuk menjaga integritas riwayat referensial.
   * **Transaksional & Ledger (Append-Only Immutable)**: Tabel `orders`, `order_items`, `assembly_tasks`, dan `stock_movements` bersifat **kekal (*immutable*)**. Baris data tidak boleh dihapus (`DELETE` dilarang). Koreksi transaksi dilakukan melalui mutasi penyesuaian (*compensating transaction*).
3. **Dual Naming Convention**:
   * Lapisan Database PostgreSQL & kode Python menggunakan **`snake_case`**.
   * Seluruh payload JSON REST API diserialisasi otomatis ke format **`camelCase`** menggunakan konfigurasi Pydantic v2 `alias_generator` untuk kenyamanan frontend React/Next.js.
4. **Strict UTC Timezone**:
   * Seluruh kolom waktu bertipe `TIMESTAMP WITH TIME ZONE` dan selalu disimpan dalam waktu UTC murni.
   * Serialisasi API menghasilkan string format ISO-8601 berakhiran **`Z`** (contoh: `2026-11-10T10:00:00Z`). Konversi ke waktu lokal (WIB / UTC+7) sepenuhnya menjadi tanggung jawab antarmuka pengguna (presentation layer).
5. **Tata Kelola Perubahan Skema & Proteksi Data Mutlak (Strict Schema Governance & Data Preservation)**:
   * **Persetujuan Wajib untuk Perubahan Struktur**: Dilarang keras memodifikasi struktur tabel (menambah, menghapus, atau mengubah nama/tipe kolom, relasi, constraint, maupun index) tanpa **persetujuan eksplisit dari USER** terlebih dahulu.
   * **Larangan Penghapusan Data Tabel**: Dilarang keras mengeksekusi operasi yang menghapus atau mengosongkan data tabel (`DROP TABLE`, `TRUNCATE`, bulk `DELETE`, atau script reset) tanpa **persetujuan eksplisit dari USER**.
   * **Prinsip Non-Destructive Migrations**: Seluruh migrasi atau perubahan struktur tabel **TIDAK BOLEH menghapus data yang sudah ada**. Jika dalam kondisi luar biasa/terpaksa data lama harus dimodifikasi atau terancam hilang akibat perubahan skema struktural, rencana mitigasi dan pencadangan (*backup plan*) wajib dipaparkan secara transparan dan **HANYA boleh dieksekusi setelah mendapat persetujuan tegas dari USER**.

---

### 2. DDL PostgreSQL Presisi (Production-Ready Database Schema)

```sql
-- ============================================================================
-- EXTENSIONS & CUSTOM ENUM TYPES
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE user_role AS ENUM (
    'OWNER',
    'ADMIN',
    'STAFF_PACKING'
);

CREATE TYPE product_type AS ENUM (
    'SINGLE_ITEM',          -- Bunga satuan, daun artifisial, kertas cellophane, pita, aksesoris
    'BOUQUET_ARRANGEMENT'   -- Rangkaian buket/hampers yang memiliki resep BOM
);

CREATE TYPE order_status AS ENUM (
    'DRAFT',
    'PENDING_PAYMENT',
    'PAID',
    'PROCESSING',
    'READY_FOR_DELIVERY',
    'COMPLETED',
    'CANCELLED'
);

CREATE TYPE task_status AS ENUM (
    'QUEUED',
    'IN_PROGRESS',
    'PACKED',
    'CANCELLED'
);

CREATE TYPE movement_type AS ENUM (
    'INBOUND_RESTOCK',      -- Penambahan stok masuk dari supplier
    'ORDER_RESERVED',       -- Penguncian stok saat order dibuat
    'ORDER_RELEASED',       -- Pelepasan kuantitas teralokasi akibat pesanan dibatalkan
    'ASSEMBLY_DEDUCTED',    -- Pemotongan fisik quantity_on_hand saat packing selesai
    'SCRAP_DAMAGED',        -- Pencatatan bahan rusak/cacat saat perakitan
    'DISASSEMBLY_RETURN',   -- Pengembalian komponen ke stok satuan dari buket yang dibongkar
    'INVENTORY_ADJUSTMENT'  -- Penyesuaian opname berkala
);

-- ============================================================================
-- 1. IAM MODULE: USERS & SESSIONS
-- ============================================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role user_role NOT NULL DEFAULT 'STAFF_PACKING',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email)
);

-- ============================================================================
-- 2. CATALOG MODULE: PRODUCTS & BILL OF MATERIALS (BOM)
-- ============================================================================
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(50) NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT NULL,
    product_type product_type NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    storage_bin VARCHAR(50) NULL, -- Lokasi rak gudang fisik (misal: "Rak B2", "Rak W1")
    is_premade BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT chk_products_price_non_negative CHECK (price >= 0)
);

CREATE TABLE bom_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bouquet_id UUID NOT NULL,
    material_id UUID NOT NULL,
    quantity_required INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_bom_bouquet FOREIGN KEY (bouquet_id) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT fk_bom_material FOREIGN KEY (material_id) REFERENCES products(id) ON DELETE RESTRICT,
    CONSTRAINT uq_bom_bouquet_material UNIQUE (bouquet_id, material_id),
    CONSTRAINT chk_bom_qty_positive CHECK (quantity_required > 0),
    CONSTRAINT chk_bom_prevent_self_reference CHECK (bouquet_id <> material_id)
);

-- ============================================================================
-- 3. INVENTORY MODULE: STOCK BALANCES & LEDGER
-- ============================================================================
CREATE TABLE inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL,
    quantity_on_hand INT NOT NULL DEFAULT 0,
    quantity_reserved INT NOT NULL DEFAULT 0,
    reorder_point INT NOT NULL DEFAULT 10,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_inventory_product UNIQUE (product_id),
    CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT chk_inv_on_hand_non_negative CHECK (quantity_on_hand >= 0),
    CONSTRAINT chk_inv_reserved_non_negative CHECK (quantity_reserved >= 0),
    CONSTRAINT chk_inv_reserved_lte_on_hand CHECK (quantity_reserved <= quantity_on_hand),
    CONSTRAINT chk_inv_reorder_point_non_negative CHECK (reorder_point >= 0)
);

CREATE TABLE stock_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID NOT NULL,
    movement_type movement_type NOT NULL,
    delta_quantity INT NOT NULL, -- Positif untuk penambahan fisik, negatif untuk pengurangan
    reference_id VARCHAR(100) NULL, -- Contoh: "ORD-202611-0012" atau Task UUID
    notes TEXT NULL,
    created_by_user_id UUID NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_movement_inventory FOREIGN KEY (inventory_id) REFERENCES inventory(id) ON DELETE CASCADE,
    CONSTRAINT fk_movement_user FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_movement_delta_nonzero CHECK (delta_quantity <> 0)
);

-- ============================================================================
-- 4. ORDER MODULE: INTAKE & LINE ITEMS
-- ============================================================================
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(50) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(30) NOT NULL,
    customer_address TEXT NULL,
    delivery_date DATE NOT NULL,
    status order_status NOT NULL DEFAULT 'PENDING_PAYMENT',
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    greeting_card_notes TEXT NULL,
    internal_notes TEXT NULL,
    created_by_user_id UUID NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),
    CONSTRAINT fk_orders_created_by FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_orders_total_non_negative CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT,
    CONSTRAINT chk_order_items_qty_positive CHECK (quantity > 0),
    CONSTRAINT chk_order_items_price_non_negative CHECK (unit_price >= 0),
    CONSTRAINT chk_order_items_subtotal_valid CHECK (subtotal = (quantity * unit_price))
);

-- ============================================================================
-- 5. ASSEMBLY MODULE: QUEUE & FULFILLMENT TASKS
-- ============================================================================
CREATE TABLE assembly_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    assigned_staff_id UUID NULL,
    status task_status NOT NULL DEFAULT 'QUEUED',
    custom_instructions TEXT NULL,
    started_at TIMESTAMP WITH TIME ZONE NULL,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_assembly_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_assembly_staff FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================
CREATE INDEX idx_users_role_active ON users(role, is_active);
CREATE INDEX idx_products_type_active ON products(product_type, is_active);
CREATE INDEX idx_bom_bouquet ON bom_components(bouquet_id);
CREATE INDEX idx_bom_material ON bom_components(material_id);
CREATE INDEX idx_inventory_product_id ON inventory(product_id);
CREATE INDEX idx_stock_movements_inv_date ON stock_movements(inventory_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_delivery_date ON orders(delivery_date ASC, created_at ASC);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_assembly_status_priority ON assembly_tasks(status, created_at ASC);
```

---

### 3. Kontrak DTO Pydantic v2 (Pydantic Models)

#### 3.1 Base CamelModel Configuration
Semua skema mewarisi `CamelModel` untuk mendukung konversi otomatis antara `snake_case` Python dan `camelCase` JSON.

```python
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


T = TypeVar("T")


class APIResponse(CamelModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    error: Optional[dict] = None
```

---

#### 3.2 Modul IAM (Schemas)

```python
class UserRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    STAFF_PACKING = "STAFF_PACKING"


class UserCreate(CamelModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole = UserRole.STAFF_PACKING


class UserResponse(CamelModel):
    id: UUID
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 3600
    user: UserResponse
```

---

#### 3.3 Modul Catalog & BOM (Schemas)

```python
class ProductType(str, Enum):
    SINGLE_ITEM = "SINGLE_ITEM"
    BOUQUET_ARRANGEMENT = "BOUQUET_ARRANGEMENT"


class BOMComponentItem(CamelModel):
    material_id: UUID
    material_name: Optional[str] = None
    material_sku: Optional[str] = None
    storage_bin: Optional[str] = None
    quantity_required: int = Field(..., gt=0)


class ProductCreate(CamelModel):
    sku: str = Field(..., max_length=50)
    name: str = Field(..., max_length=150)
    description: Optional[str] = None
    product_type: ProductType
    price: Decimal = Field(..., ge=0)
    storage_bin: Optional[str] = None
    is_premade: bool = False
    bom_recipes: Optional[List[BOMComponentItem]] = (
        None  # Hanya jika product_type == BOUQUET_ARRANGEMENT
    )


class ProductResponse(CamelModel):
    id: UUID
    sku: str
    name: str
    description: Optional[str] = None
    product_type: ProductType
    price: Decimal
    storage_bin: Optional[str] = None
    is_premade: bool
    is_active: bool
    available_stock: Optional[int] = None
    bom_components: Optional[List[BOMComponentItem]] = None
    created_at: datetime
```

---

#### 3.4 Modul Inventory (Schemas)

```python
class MovementType(str, Enum):
    INBOUND_RESTOCK = "INBOUND_RESTOCK"
    ORDER_RESERVED = "ORDER_RESERVED"
    ORDER_RELEASED = "ORDER_RELEASED"
    ASSEMBLY_DEDUCTED = "ASSEMBLY_DEDUCTED"
    SCRAP_DAMAGED = "SCRAP_DAMAGED"
    DISASSEMBLY_RETURN = "DISASSEMBLY_RETURN"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"


class InventoryResponse(CamelModel):
    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    storage_bin: Optional[str]
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int  # Computed: on_hand - reserved
    reorder_point: int
    is_low_stock: bool
    updated_at: datetime


class StockMovementResponse(CamelModel):
    id: UUID
    inventory_id: UUID
    movement_type: MovementType
    delta_quantity: int
    reference_id: Optional[str]
    notes: Optional[str]
    created_by_username: Optional[str]
    created_at: datetime
```

---

#### 3.5 Modul Orders & Assembly (Schemas)

```python
class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    PACKED = "PACKED"
    CANCELLED = "CANCELLED"


class OrderItemInput(CamelModel):
    product_id: UUID
    quantity: int = Field(..., gt=0)


class OrderCreate(CamelModel):
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_phone: str = Field(..., min_length=8, max_length=30)
    customer_address: Optional[str] = None
    delivery_date: date
    greeting_card_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    items: List[OrderItemInput] = Field(..., min_length=1)


class OrderItemResponse(CamelModel):
    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderResponse(CamelModel):
    id: UUID
    order_number: str
    customer_name: str
    customer_phone: str
    customer_address: Optional[str]
    delivery_date: date
    status: OrderStatus
    total_amount: Decimal
    greeting_card_notes: Optional[str]
    internal_notes: Optional[str]
    items: List[OrderItemResponse]
    created_at: datetime
    updated_at: datetime


class AssemblyTaskResponse(CamelModel):
    id: UUID
    order_id: UUID
    order_number: str
    delivery_date: date
    status: TaskStatus
    assigned_staff_name: Optional[str]
    custom_instructions: Optional[str]
    required_materials: List[BOMComponentItem]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class ScrapReportRequest(CamelModel):
    damaged_material_id: UUID
    quantity_damaged: int = Field(1, gt=0)
    reason: str = Field(..., min_length=3, max_length=255)
```

---

### 4. Standar Kode Kesalahan & Error Envelope Contract

Setiap respons gagal (`success: false`) menghasilkan format JSON terstruktur dengan HTTP status code yang semantik:

| HTTP Status | Kode Error Internal | Kondisi Pemicu |
| :--- | :--- | :--- |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Token JWT tidak disertakan atau kedaluwarsa. |
| `403 Forbidden` | `INSUFFICIENT_PERMISSIONS` | Aktor tidak memiliki hak akses role (misal: Staff Packing mengakses laporan keuangan). |
| `404 Not Found` | `RESOURCE_NOT_FOUND` | ID produk, pesanan, atau tugas perakitan tidak ditemukan di database. |
| `409 Conflict` | `INSUFFICIENT_STOCK` | Stok bahan baku satuan (BOM) tidak mencukupi untuk memenuhi pesanan. |
| `409 Conflict` | `INVALID_STATUS_TRANSITION` | Mencoba memicu aksi yang melanggar FSM (misal: order `CANCELLED` hendak diubah jadi `PAID`). |
| `422 Unprocessable` | `VALIDATION_ERROR` | Format data request tidak memenuhi syarat Pydantic. |

#### Contoh Payload Error Standar:
```json
{
  "success": false,
  "data": null,
  "message": "Stok bahan tidak mencukupi untuk memenuhi pesanan buket.",
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "details": [
      {
        "materialId": "d3b07384-d113-4a6c-940e-53c8c7d67f1b",
        "materialSku": "ART-ROSE-RED",
        "materialName": "Rose Velvet Merah Artifisial",
        "requested": 20,
        "available": 8
      }
    ]
  }
}
```
