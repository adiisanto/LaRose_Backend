# Product Requirements Document (PRD)
## LaRose Floral Studio — Intelligent Artificial Florist & Inventory Management System

---

### 1. Ringkasan Eksekutif (Executive Summary)

**LaRose Floral Studio** adalah sistem terpadu pengelolaan operasional toko bunga artifisial (bunga palsu) berbasis arsitektur modular terpisah (*frontend-backend segregation*). Sistem ini dirancang untuk menyelesaikan tantangan unik bisnis bunga artifisial, di mana penjualan dilakukan dalam dua bentuk utama: **produk satuan** (misal: tangkai bunga tiruan, daun hias, pita, kertas wrapping) dan **rangkaian buket/komposisi** (misal: buket wisuda, buket meja, hampers) yang mengonsumsi komponen satuan melalui mekanisme **Bill of Materials (BOM)**.

Proyek ini dibangun sebagai proyek portofolio bertaraf profesional yang menonjolkan kompetensi ganda:
1. **Backend Software Engineer**: Arsitektur modular Python, transaksi database terisolasi (*atomic transactions*), pengelolaan konkurensi stok komponen, REST API bersih, dan pemisahan *concern* domain.
2. **System Analyst & Solution Architect**: Perancangan sistem berbasis analisis mendalam, pemodelan relasional yang fleksibel dan terukur (*scalable*), serta pendokumentasian rekayasa sistem berstandar industri.

---

### 2. Visi Produk & Problem Statement

#### 2.1 Problem Statement
1. **Kompleksitas Hubungan Stok Satuan vs Rangkaian**: Berbeda dengan produk ritel umum, sebuah buket bunga tiruan tersusun dari beberapa tangkai bunga satuan, aksesoris, dan bahan pembungkus. Tanpa sistem *Bill of Materials (BOM)* otomatis, toko berisiko mengalami *overselling* tangkai satuan yang sebetulnya telah dialokasikan untuk pesanan buket, atau sebaliknya.
2. **Ketiadaan Pelacakan Alur Kerja Internal**: Toko floris manual sering mengalami hambatan komunikasi antara bagian penerima pesanan (Admin) dan bagian perakitan fisik (Staff Packing/Assembly), menyebabkan pesanan terlewat atau waktu pemrosesan tidak terukur.
3. **Visibilitas Performa Bisnis Rendah**: Owner kesulitan memantau margin keuntungan per buket, sisa bahan baku berlebih (*slow-moving stems*), dan produktivitas harian tim perakitan.

#### 2.2 Solusi & Value Proposition
* **Dynamic Bill of Materials (BOM)**: Sistem secara otomatis memotong stok bahan satuan (tangkai bunga, kertas wrapping, pita) saat buket dipesan atau dirakit, sekaligus mendukung buket *pre-made* (stok siap kirim).
* **Role-Based Operational Flow**: Pemisahan hak akses dan alur kerja yang jelas antara **Owner**, **Admin**, dan **Staff Packing**.
* **Decoupled Architecture Ready**: Backend Python modular independen (di-host di Koyeb) siap melayani backoffice internal saat ini, dan dirancang terbuka untuk penambahan *storefront* publik (Next.js di Vercel) pada fase berikutnya tanpa perombakan arsitektur dasar.

---

### 3. Persona & Aktor Pengguna

Sistem mengadopsi pendekatan berfase. Pada **Fase 1 (MVP Portofolio)**, sistem berfokus pada 3 aktor internal toko. Pada **Fase 2 (Scale-up)**, sistem akan diperluas untuk mendukung pembeli publik.

| Aktor | Peran & Hak Akses | Kebutuhan Utama |
| :--- | :--- | :--- |
| **Owner** | Pemilik bisnis dengan hak akses penuh (*Superadmin*). | - Dashboard analitik penjualan dan margin keuntungan.<br>- Laporan stok kritis dan perputaran barang.<br>- Manajemen akun dan penugasan peran staf.<br>- Audit log aktivitas operasional. |
| **Admin** | Operator toko yang mengelola katalog, stok, dan pesanan masuk. | - Manajemen master data bunga satuan & bahan wrapping.<br>- Perumusan resep buket (BOM / *component recipes*).<br>- Input pesanan masuk dari multi-channel (WhatsApp, offline, marketplace).<br>- Validasi pembayaran dan penugasan pesanan ke antrean packing. |
| **Staff Packing** | Petugas gudang dan perakit buket fisik (*Floral Assembler*). | - Antrean kerja real-time (*Assembly Queue*).<br>- Lembar kerja perakitan (daftar komponen & bahan buket yang harus diambil).<br>- Konfirmasi status perakitan (Mulai Rakit $\rightarrow$ Selesai $\rightarrow$ Siap Kirim).<br>- Pelaporan bahan rusak/cacat fisik. |
| **Pembeli (Fase 2)** | Pelanggan eksternal toko bunga. | - Akses katalog publik bunga satuan dan buket.<br>- Pemesanan mandiri (*self-checkout*).<br>- Pelacakan status pesanan real-time via kode unik/nomor resi. |

---

### 4. Kebutuhan Fungsional (Functional Requirements)

#### 4.1 Modul 1: Identity & Access Management (IAM)
* **FR-IAM-01**: Sistem harus menyediakan mekanisme autentikasi aman berbasis JWT (JSON Web Token).
* **FR-IAM-02**: Sistem harus membatasi endpoint API berdasarkan Role-Based Access Control (RBAC): `OWNER`, `ADMIN`, `STAFF_PACKING`.
* **FR-IAM-03**: Owner dapat mengelola akun pengguna (membuat, mengubah peran, menonaktifkan pengguna internal).

#### 4.2 Modul 2: Catalog & Bill of Materials (BOM) Management
* **FR-CAT-01**: Sistem mendukung dua tipe produk utama:
  * `SINGLE_ITEM`: Bunga satuan (misal: Rose Tangkai Velvet Merah, Lily Artificial Putih), daun hias, bahan pembungkus (cellophane paper), dan aksesoris (pita satin, kartu ucapan).
  * `BOUQUET_ARRANGEMENT`: Rangkaian buket atau hampers yang memiliki formula komposisi (BOM).
* **FR-CAT-02**: Admin dapat menentukan resep BOM untuk setiap produk buket, mencakup daftar `SINGLE_ITEM` dan kuantitas yang dibutuhkan per 1 unit buket.
* **FR-CAT-03**: Sistem mendukung buket *pre-made* (buket yang sudah dirakit terlebih dahulu dan memiliki stok fisik langsung) maupun buket *made-to-order* (dirakit saat ada pesanan masuk, memotong stok bahan baku).

#### 4.3 Modul 3: Inventory & Material Ledger
* **FR-INV-01**: Sistem harus mencatat kuantitas fisik (`quantity_on_hand`) dan kuantitas teralokasi (`quantity_reserved`) untuk setiap item bahan satuan.
* **FR-INV-02**: Stok tersedia (*available stock*) dihitung secara konsisten: $\text{Available} = \text{On Hand} - \text{Reserved}$.
* **FR-INV-03**: Setiap mutasi stok (penambahan stok masuk/restock, pengurangan akibat penjualan, penyesuaian opname/rusak) harus dicatat secara *append-only* di tabel riwayat pergerakan stok (*Stock Ledger / Inventory Movement*) untuk audit trail.
* **FR-INV-04**: Sistem harus menyediakan peringatan stok minimum (*low stock alert*) untuk bahan satuan kritis.

#### 4.4 Modul 4: Order Intake & Processing
* **FR-ORD-01**: Admin dapat membuat pesanan baru (*Manual Order Intake*) yang mencantumkan nama pelanggan, detail kontak, alamat pengiriman, tanggal permintaan kirim, dan rincian item pesanan.
* **FR-ORD-02**: Ketika pesanan buket dibuat, sistem secara otomatis mengecek ketersediaan bahan komponen berdasarkan resep BOM.
* **FR-ORD-03**: Sistem menerapkan transaksi *atomic*: jika stok bahan mencukupi, bahan langsung dipindahkan ke status `reserved` untuk mencegah *overselling*.
* **FR-ORD-04**: Admin dapat mencatat status pembayaran (`UNPAID`, `PAID`, `CANCELLED`).

#### 4.5 Modul 5: Assembly & Packing Operations
* **FR-PCK-01**: Pesanan berstatus `PAID` secara otomatis memunculkan tugas perakitan (*Assembly Task*) pada antrean kerja Staff Packing.
* **FR-PCK-02**: Staff Packing dapat melihat instruksi perakitan (BOM spesifik per buket dan instruksi kustomisasi seperti warna wrapping/pita).
* **FR-PCK-03**: Alur status perakitan: `QUEUED` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `PACKED` $\rightarrow$ `READY_FOR_DELIVERY`.
* **FR-PCK-04**: Saat status berubah menjadi `PACKED`, stok bahan baku yang sebelumnya berstatus `reserved` resmi dipotong dari `quantity_on_hand` fisik.

#### 4.6 Modul 6: Business Intelligence & Reporting (Owner Dashboard)
* **FR-REP-01**: Menampilkan ringkasan pendapatan harian/bulanan, jumlah pesanan selesai, dan tingkat pembatalan.
* **FR-REP-02**: Menampilkan daftar produk terlaris (*best-selling bouquets & single stems*).
* **FR-REP-03**: Menampilkan estimasi nilai valuasi inventaris bahan baku saat ini.

---

### 5. Kebutuhan Non-Fungsional (Non-Functional Requirements)

1. **Integritas & Keandalan Transaksi (Data Integrity)**:
   * Alokasi stok dan perakitan BOM wajib dijalankan di dalam blok transaksi terisolasi (*PostgreSQL ACID Transactions*) dengan penguncian baris (*pessimistic row locking*) untuk mencegah kondisi balapan (*race condition*).
2. **Modular Monolith Architecture**:
   * Struktur kode backend Python harus terbagi dalam domain modul yang kohesif (`iam`, `catalog`, `inventory`, `orders`, `assembly`, `reports`) dengan dependensi antarmuka yang bersih (*Clean/Hexagonal Architecture principles*).
3. **API Performance & Latency**:
   * P95 response time untuk endpoint katalog dan mutasi inventaris $< 200\text{ ms}$.
4. **Security & Data Protection**:
   * Hashing kata sandi menggunakan Argon2id atau bcrypt.
   * Komunikasi HTTPS terenkripsi penuh melalui Koyeb SSL termination.
   * Supabase PostgreSQL diakses via connection string aman berparameter SSL.
5. **Portability & Cloud Compatibility**:
   * Konfigurasi berbasis environment variables (*12-Factor App*).
   * Siap dijalankan melalui container Docker pada platform PaaS (Koyeb).

---

### 6. Alur Bisnis Makro (Macro Business Flow)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer / Channel
    actor A as Admin
    participant O as Order Module
    participant I as Inventory (BOM Engine)
    actor P as Staff Packing
    actor W as Owner

    C->>A: Melakukan pemesanan buket & bunga satuan
    A->>O: Input Order (Items & Customer Details)
    O->>I: Validasi Stok Komponen (BOM Check)
    alt Stok Komponen Cukup
        I-->>O: Stok Valid & Lock Bahan (Reserve Stock)
        O-->>A: Order Created (Status: PENDING_PAYMENT)
        A->>O: Konfirmasi Pembayaran (Status: PAID)
        O->>P: Generate Assembly & Packing Task
        P->>P: Ambil Bahan Fisik & Rangkai Buket (IN_PROGRESS)
        P->>I: Selesai Packing (Deduct Reserved Stock to Zero)
        P->>O: Update Status: READY_FOR_DELIVERY
        A->>O: Update Status: COMPLETED / DISPATCHED
    else Stok Komponen Kurang
        I-->>O: Insufficient Material Error
        O-->>A: Tampilkan detail bahan yang kurang
    end
    W->>O: Pantau Laporan Penjualan & Performa via Dashboard
```

---

### 7. Entity Relationship Diagram Konseptual (Conceptual ERD)

```mermaid
erDiagram
    USER ||--o{ REFRESH_TOKEN : has
    USER ||--o{ ORDER : creates_or_handles
    USER ||--o{ ASSEMBLY_TASK : assigned_to

    PRODUCT ||--o{ BOM_COMPONENT : "used_as_parent_bouquet"
    PRODUCT ||--o{ BOM_COMPONENT : "used_as_raw_material"
    PRODUCT ||--|| INVENTORY : has_stock
    INVENTORY ||--o{ STOCK_MOVEMENT : records

    ORDER ||--o{ ORDER_ITEM : contains
    ORDER ||--o{ ASSEMBLY_TASK : generates
    PRODUCT ||--o{ ORDER_ITEM : ordered_as

    USER {
        uuid id PK
        string username
        string email
        string password_hash
        string role "OWNER | ADMIN | STAFF_PACKING"
        boolean is_active
    }

    PRODUCT {
        uuid id PK
        string sku UK
        string name
        string product_type "SINGLE_ITEM | BOUQUET_ARRANGEMENT"
        decimal price
        boolean is_active
    }

    BOM_COMPONENT {
        uuid id PK
        uuid bouquet_id FK
        uuid material_id FK
        integer quantity_required
    }

    INVENTORY {
        uuid id PK
        uuid product_id FK
        integer quantity_on_hand
        integer quantity_reserved
        integer reorder_point
    }

    STOCK_MOVEMENT {
        uuid id PK
        uuid inventory_id FK
        string movement_type "INBOUND | OUTBOUND_ORDER | ASSEMBLY_RESERVE | ADJUSTMENT"
        integer delta_quantity
        string reference_id
        timestamp created_at
    }

    ORDER {
        uuid id PK
        string order_number UK
        string customer_name
        string customer_phone
        string status "DRAFT | PENDING_PAYMENT | PAID | PROCESSING | READY | COMPLETED | CANCELLED"
        decimal total_amount
        timestamp scheduled_delivery_date
    }

    ORDER_ITEM {
        uuid id PK
        uuid order_id FK
        uuid product_id FK
        integer quantity
        decimal unit_price
        decimal subtotal
    }

    ASSEMBLY_TASK {
        uuid id PK
        uuid order_id FK
        uuid assigned_staff_id FK
        string status "QUEUED | IN_PROGRESS | PACKED"
        text custom_notes
        timestamp started_at
        timestamp completed_at
    }
```

---

### 8. Rencana Fase Pengembangan (Roadmap)

```mermaid
timeline
    title Roadmap Pengembangan LaRose Floral Studio
    Fase 1 : Fondasi Dokumentasi Arsitektur (PRD, TRD, AFD, DBD, BSD, IPD, GEMINI.md)
           : Backend Core & IAM (FastAPI Modular, PostgreSQL Supabase, JWT RBAC)
           : Master Catalog & Dynamic Bill of Materials (BOM)
           : Transaksi Inventaris Atomik & Pencegahan Overselling
           : Antrean Perakitan & Staff Packing Operations
           : Deployment Backend ke Koyeb
    Fase 2 : Pengembangan Web Frontend (Next.js di Vercel)
           : Dashboard Internal untuk Owner, Admin, dan Packing Staff
    Fase 3 : Ekstensi Storefront Publik (Katalog Pembeli Online & Self-checkout)
           : Integrasi Payment Gateway (Midtrans/Xendit)
           : Integrasi Notifikasi Pengiriman (WhatsApp/Email Webhook)
```
