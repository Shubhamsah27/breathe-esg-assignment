# Breathe ESG - Carbon Accounting Ingestion & Review Engine

A production-grade, multi-tenant carbon data ingestion, normalization, and analyst review platform. Built with **Django REST Framework** (backend API) and **React** (Vite + modern Vanilla CSS dashboard).

---

## 🚀 Core Features

### 1. Data Ingestion & Engineering
* **Source A: SAP Fuel & Procurement (Scope 1)**
  * Parses CSV exports using technical SAP field mappings (`WERKS`, `BUDAT`, `MENGE`, `MEINS`, `TXT50`, `WRBTR`, `WAERS`).
  * Cleans European numerical formatting (e.g. `2.500,00` $\rightarrow$ `2500.0`).
  * Translates raw units (Tonnes `TO`, Kilograms `KG` $\rightarrow$ Liters `L`) based on fuel density.
  * Resolves cryptic plant codes (`WERKS`) to physical regions. Unknown plants default to global averages and trigger an analyst validation warning.
* **Source B: Utility Grid Electricity (Scope 2)**
  * Handles billing cycle calendar-month mismatches (e.g., bills spanning April 15 to May 15).
  * **Daily-Average Proration Algorithm**: Divides billed consumption proportionally by daily average weight and yields separate calendar-month records, applying regional grid factors.
  * Translates inconsistent units (`Wh`, `MWh` $\rightarrow$ `kWh`).
* **Source C: Corporate Travel Expense API (Scope 3)**
  * Simulates JSON expense integrations (Navan/Concur standard payloads).
  * **Haversine Distance Math Solver**: Looks up airport coordinates offline and calculates exact great-circle aviation distances in kilometers.
  * Implements precise seat-class multipliers (First, Business, Economy) for short-haul vs. long-haul flights.
  * Processes hotel room-nights (with country benchmarks) and ground transport modes (Taxi, Train, Rental Car).

### 2. Analyst Review Ledger & Audit Trails
* **Staging vs. Normalized Split**: Stages raw files in a backup staging table (`RawIngestedRecord`) before writing to the target carbon ledger. Malformed files never contaminate clean financial reports, allowing line-item error diagnostics.
* **Manual Correction Interface**: Analysts can manually adjust quantities on non-locked rows. The engine dynamically recalculates emissions, creates before/after diffs in the ledger, and resets the record to Draft.
* **Chronological Timeline Ledger**: An interactive chronological audit timeline captures all actions (ingestions, manual corrections, flags, and approvals) with usernames and comments.
* **Auditor Freeze (Audit Lock)**: Allows analysts to bulk-lock approved rows, freezing transactions and permanently blocking future API modifications to secure reporting integrity.

---

## 📂 Project Directory Structure

```text
d:\Assessment\BreatheESG/
├── breathe_esg/                # Django core project configs
│   ├── settings.py             # Settings (CORS, Whitenoise, persistent database paths)
│   └── urls.py                 # Core routing (root redirects to /api/v1/)
├── ingestion/                  # Core carbon accounting application
│   ├── models.py               # Relational schema (multi-tenant)
│   ├── parsers.py              # Math engines (Haversine, proration, factor calculations)
│   ├── serializers.py          # DRF serialization mappings
│   ├── views.py                # File uploads, travel API, analytics endpoints
│   ├── urls.py                 # App endpoint routers
│   └── tests.py                # 100% passing backend unit tests
├── frontend/                   # Vite React SPA client
│   ├── src/
│   │   ├── App.jsx             # React master component (analytics, uploads, audit drawer)
│   │   └── index.css           # Premium responsive HSL Vanilla CSS theme
│   ├── package.json
│   └── vite.config.js
├── requirements.txt            # Python production dependencies
├── render.yaml                 # Render infrastructure-as-code Blueprint
├── MODEL.md                    # Database design & schema justification
├── DECISIONS.md                # Resolved proration & Haversine ambiguities
├── TRADEOFFS.md               # 3 deliberate engineering trade-offs made
└── SOURCES.md                  # Ingestion formats research & production hardening
```

---

## 📈 Verification & Testing

We implemented 5 comprehensive unit tests covering proration day counts, Haversine aviation distance, European digit formatting, unrecognized plant warnings, and tenant isolation:

```powershell
python manage.py test
```

**Output Log**:
```text
Creating test database for alias 'default'...
.....
----------------------------------------------------------------------
Ran 5 tests in 0.029s

OK
Destroying test database for alias 'default'...
Found 5 test(s).
System check identified no issues (0 silenced).
```

---

## 💻 Local Launch Instructions

### 1. Backend Server Setup
In the project root folder:
```powershell
# Activate environment
.\venv\Scripts\activate

# Apply migrations
python manage.py makemigrations ingestion
python manage.py migrate

# Run local development server
python manage.py runserver
```
*API live at `http://127.0.0.1:8000/api/v1/`.*

### 2. Frontend Client Setup
In the `frontend` folder:
```powershell
# Install dependencies
npm install

# Start development server
npm run dev
```
*Vite dev server live at `http://localhost:5173/`.*
*Click the **🚀 Bootstrap & Seed DB** button on top to pre-populate lookups and sample sources!*

---

## ☁️ Render Production Deployment

The project is fully pre-configured for one-click deployment using **Render's Blueprint (`render.yaml`)** spec:
* Auto-configures the Django backend Web Service on Render's **Free Plan**.
* Binds the React frontend Static Site and automatically injects the backend environment variables.
* Integrates **Whitenoise** to serve static files in production.
