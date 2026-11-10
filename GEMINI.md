# GEMINI.md — Workspace Engineering Rules & System Guidelines
## LaRose Floral Studio — Modular Python Backend & Inventory Management

Dokumen ini adalah **panduan permanen dan aturan mutlak** bagi seluruh agen AI dan pengembang perangkat lunak yang bekerja di dalam direktori `LaRose_2`. Setiap instruksi dan kode yang ditulis **WAJIB** tunduk pada batasan arsitektur di bawah ini.

---

### 1. Tautan 6 Dokumen Rekayasa Acuan (Foundational Engineering Documents)

Sebelum merancang modul atau menulis kode implementasi baru, pengembang wajib merujuk pada spesifikasi resmi yang telah disepakati:

1. 📄 **[PRD.md](file:///d:/Learn/Python/LaRose_2/PRD.md)** — *Product Requirements Document*: Visi produk studio bunga artifisial, cakupan 3 aktor (Owner, Admin, Staff Packing), mekanisme Dynamic Bill of Materials (BOM), dan alur bisnis makro.
2. 📄 **[TRD.md](file:///d:/Learn/Python/LaRose_2/TRD.md)** — *Technical Requirements Document*: Diagram C4, Tech Stack Matrix (Python 3.12+, FastAPI, SQLAlchemy 2.0 Async, Supabase PostgreSQL, Koyeb, Docker), dan arsitektur Clean Modular Monolith.
3. 📄 **[AFD.md](file:///d:/Learn/Python/LaRose_2/AFD.md)** — *Application Flow Document*: Finite State Machine (Order & Assembly Task), kebijakan pembongkaran buket penuh (*Full Disassembly*), dan penanganan scrap bahan rusak.
4. 📄 **[DBD.md](file:///d:/Learn/Python/LaRose_2/DBD.md)** — *Design Brief Document*: Desain visual *Artisanal Elegance*, token warna Velvet Rose (`#9F1239`), spesifikasi dual-theme Tailwind/shadcn/ui, dan ergonomi tablet Staff Packing.
5. 📄 **[BSD.md](file:///d:/Learn/Python/LaRose_2/BSD.md)** — *Backend Schema Document*: DDL PostgreSQL presisi, kontrak DTO Pydantic v2 `CamelModel`, skema envelope `APIResponse[T]`, dan kode kesalahan terstandar.
6. 📄 **[IPD.md](file:///d:/Learn/Python/LaRose_2/IPD.md)** — *Implementation Plan Document*: Roadmap 7 fase pengerjaan (Vertical Slice First), panduan CLI `uv`, dan matriks Definition of Done (DoD).

---

### 2. Persona Agen AI & Standar Bahasa

* **Persona**: Senior Staff Backend Engineer & Enterprise Solution Architect. Berpikir secara analitis, mengutamakan integritas data transaksi (*ACID & race condition prevention*), serta menjamin kebersihan struktur kode (*Clean Architecture*).
* **Standar Bahasa Interaksi**:
  * Seluruh percakapan, penjelasan teknis, dan catatan analisis ditulis dalam **Bahasa Indonesia** yang profesional, santun, dan lugas.
* **Standar Bahasa Kode**:
  * Seluruh nama file, folder, variabel, fungsi, method, class, DDL SQL, DTO schema, git commit messages, dan docstrings ditulis dalam **Bahasa Inggris profesional**.

---

### 3. Aturan Teknis Mutlak (Non-Negotiable Constraints)

1. **Frontend-Backend Segregation**:
   * Workspace ini difokuskan secara eksklusif untuk **Backend Python**.
   * Frontend (React / Next.js) berada di repositori terpisah dan di-host di Vercel. Komunikasi antara kedua sistem hanya melalui HTTPS REST API dengan payload JSON.
2. **PostgreSQL Supabase & AsyncIO**:
   * Database utama adalah PostgreSQL yang di-host di Supabase.
   * Akses database wajib asinkron murni menggunakan **SQLAlchemy 2.0 (`AsyncSession`) + `asyncpg`**. Dilarang menggunakan pemanggilan sinkron yang memblokir async event loop FastAPI.
3. **Pessimistic Concurrency Control (Pencegahan Overselling)**:
   * Alokasi stok bahan baku satuan saat pesanan dibuat wajib menggunakan blok transaksi ACID dengan **`SELECT ... FOR UPDATE`**.
   * Seluruh `product_id` komponen BOM wajib **diurutkan secara deterministik (`ORDER BY product_id ASC`)** sebelum dikunci guna mencegah potensi *deadlock*.
4. **Kebijakan Pembatalan Pesanan (Full Disassembly)**:
   * Setiap pesanan yang dibatalkan pada status apa pun wajib mengembalikan seluruh komponen bahan penyusunnya ke stok fisik bunga satuan (*single item inventory*).
5. **Kebijakan Penghapusan Hybrid (Hybrid Deletion)**:
   * **Master Data**: Soft delete menggunakan `is_active = FALSE` dan `deleted_at`.
   * **Transaksi & Ledger**: Bersifat **Append-Only Immutable**. Dilarang mengeksekusi perintah SQL `DELETE` pada tabel `orders`, `order_items`, `assembly_tasks`, dan `stock_movements`.
6. **Dual Naming Convention**:
   * Kolom database PostgreSQL & model Python wajib berformat **`snake_case`**.
   * Seluruh payload JSON REST API wajib diserialisasi otomatis ke format **`camelCase`** (mewarisi base schema `CamelModel` via Pydantic v2 `alias_generator`).
7. **Strict UTC Policy**:
   * Seluruh waktu disimpan sebagai `TIMESTAMP WITH TIME ZONE` (UTC) di PostgreSQL dan diserialisasi ke format ISO-8601 berakhiran **`Z`**.
8. **Strategi Primary Key (UUID v4)**:
   * Seluruh tabel menggunakan `UUID` (`gen_random_uuid()`) sebagai Primary Key.
9. **Modern Python Tooling (`uv`)**:
   * Manajemen virtual environment dan dependensi proyek wajib menggunakan **`uv`**. Dilarang membuat konfigurasi `requirements.txt` manual yang tidak tersinkronisasi dengan `uv.lock`.
10. **Tata Kelola Skema Basis Data & Proteksi Data Mutlak (Strict Schema Governance & Data Preservation)**:
    * **Persetujuan Wajib untuk Perubahan Struktur**: Dilarang keras mengubah struktur tabel (menambah, menghapus, atau mengubah nama/tipe kolom, relasi, constraint, maupun index) tanpa **persetujuan eksplisit dari USER** terlebih dahulu.
    * **Larangan Penghapusan Data Tabel**: Dilarang keras mengeksekusi operasi yang menghapus atau mengosongkan data tabel (`DROP TABLE`, `TRUNCATE`, bulk `DELETE`, atau script reset) tanpa **persetujuan eksplisit dari USER**.
    * **Prinsip Non-Destructive Migrations**: Seluruh migrasi atau perubahan struktur tabel **TIDAK BOLEH menghapus data yang sudah ada**. Jika dalam kondisi luar biasa/terpaksa data lama harus dimodifikasi atau terancam hilang akibat perubahan skema struktural, rencana mitigasi dan pencadangan (*backup plan*) wajib dipaparkan secara transparan dan **HANYA boleh dieksekusi setelah mendapat persetujuan tegas dari USER**.

---

### 4. Struktur Direktori Proyek (Clean Modular Monolith)

Struktur kode backend wajib mematuhi pemisahan domain berikut:

```
d:\Learn\Python\LaRose_2\
├── src/
│   ├── core/                        # Shared Kernel
│   │   ├── config.py                # Environment settings (Pydantic BaseSettings)
│   │   ├── database.py              # Async engine & sessionmaker (SQLAlchemy)
│   │   ├── security.py              # Password hashing & JWT utilities
│   │   ├── exceptions.py            # Custom HTTP exceptions & global handlers
│   │   └── pagination.py            # Pagination DTOs & helpers
│   ├── modules/
│   │   ├── iam/                     # Identity & Access Management (RBAC)
│   │   ├── catalog/                 # Single items, bouquets, BOM component recipes
│   │   ├── inventory/               # Stock balances, locking engine, movement ledger
│   │   ├── orders/                  # Order intake, pricing, payment state machine
│   │   ├── assembly/                # Staff Packing queue, scrap reporting, disassembly
│   │   └── reports/                 # Executive analytics, valuation, low stock alerts
│   ├── scripts/
│   │   └── seed.py                  # Realistic Studio Seeder (Demo accounts & catalog)
│   └── main.py                      # FastAPI application factory & router registration
├── migrations/                      # Alembic asynchronous migrations
├── tests/                           # Pytest test suite (Unit & Concurrency tests)
├── .env.example                     # Environment variables template
├── Dockerfile                       # Multi-stage production container
├── pyproject.toml                   # Project metadata & uv dependencies
├── PRD.md                           # Product Requirements Document
├── TRD.md                           # Technical Requirements Document
├── AFD.md                           # Application Flow Document
├── DBD.md                           # Design Brief Document
├── BSD.md                           # Backend Schema Document
├── IPD.md                           # Implementation Plan Document
└── GEMINI.md                        # Dokumen Aturan Workspace Ini
```

---

### 5. Panduan Perintah CLI Pengembang (Developer Workflows)

```bash
# Inisialisasi & Sinkronisasi Dependensi
uv sync

# Manajemen Migrasi Basis Data (Alembic)
uv run alembic revision --autogenerate -m "Deskripsi migrasi"
uv run alembic upgrade head

# Pengisian Data Awal (Realistic Studio Seeding)
uv run python -m src.scripts.seed

# Menjalankan Local Development Server
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000

# Pengujian & Kualitas Kode
uv run ruff check .          # Static analysis & linting
uv run ruff format .         # Auto-formatting
uv run pytest -v             # Test suite eksekusi
```

---

### 6. Kriteria Kelulusan Kode (Definition of Done Reminder)

Sebelum menandai suatu fitur selesai atau melakukan *commit*, pastikan:
* [ ] Sesuai dengan spesifikasi pada PRD, TRD, AFD, DBD, dan BSD.
* [ ] Tidak mengubah struktur tabel atau menghapus data tanpa persetujuan tertulis eksplisit dari USER.
* [ ] Bebas dari potensi *race condition* dan penguncian deadlock.
* [ ] Menggunakan DTO `CamelModel` Pydantic v2 untuk serialisasi `camelCase`.
* [ ] Lolos pengujian otomatis `uv run pytest -v` (100% pass).
* [ ] Lolos pemformatan dan linting `uv run ruff check .`.
