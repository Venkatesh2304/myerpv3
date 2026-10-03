# App: `bill_scan` — Outbound Delivery Loading, E-Way Generation & Route Sync

> Purpose: Verification of printed sales invoices loaded into delivery vehicles, driver gate-pass manifests, NIC E-Way Bill generation, and Unilever Impact / ShogunLite trip plan dispatch.

---

## 1. Business Purpose & Operational Context

After customer invoices are printed:
1. Physical bills must be loaded onto the correct delivery vehicle. Missing an invoice results in undelivered stock.
2. Vehicles carrying goods exceeding government threshold amounts require statutory E-Way Bills before exiting warehouse gates.
3. Delivery trips must sync to Unilever Impact / ShogunLite for driver mobile beat routing.
4. When delivery vehicles return in the evening, returned/undelivered bills must be reconciled.

The `bill_scan` app automates physical loading scans, generates vehicle E-Way bills, builds driver loading manifests, and coordinates with Unilever Impact.

---

## 2. Shared Models & State (`bill/models.py`)

`bill_scan` operates directly on models defined in the `bill` app:
- **[`Vehicle`](file:///home/ubuntu/myerpv3/bill/models.py#L45)**: `name`, `vehicle_no`, `name_on_impact` (Unilever ShogunLite vehicle alias).
- **[`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53)**:
  - `vehicle`: ForeignKey to `Vehicle`.
  - `loading_time`: Set when scanned during vehicle loading.
  - `delivery_time`: Set when verified upon vehicle return.
  - `delivery_applicable`: Boolean flag (false for counter pickups or holds).
  - `ewb_no`: Government E-Way Bill number.
  - `notes`: Append-only audit remarks list.

---

## 3. Core Workflows

### 1. Physical Bill Scanning (`/scan_bill/`)
- Supports individual bill IDs or batch scanning via Salesman Loading Sheet (IDs starting with `"SM"`).
- **Load Mode (`type="load"`)**: Links `bill.vehicle_id = vehicle_id` and sets `loading_time = now()`.
- **Delivery Mode (`type="delivery"`)**: Validates that bill was previously loaded; sets `delivery_time = now()`.

### 2. Driver Loading Manifest PDF (`/download_scan_pdf/`)
- Generates a compact 6-column tabular PDF manifest of all bill IDs loaded into a vehicle today to serve as a driver checklist and gate pass.

### 3. E-Way Bill Automation (`eway.py`)
- Downloads tax invoice export from IKEA via `Ikea.eway_excel()`.
- Transforms data into NIC E-Way JSON schema v1.0.0621 (`eway_df_to_json`):
  - Injects vehicle number, default distance (3 km local distribution radius), and pads HSN codes to 8 digits.
- Uploads to government portal via `Einvoice.upload_eway_bill()` and fetches generated EWB numbers via `Einvoice.get_eway_bills()`.
- Updates `Bill.ewb_no` in the database.
- **Vehicle E-Way (`/upload_vehicle_eway/`)**: Files E-Way bills for a specific vehicle's load today and outputs an A4 summary PDF for the driver.
- **Company Bulk E-Way (`/upload_company_eway/`)**: Files yesterday's bills (`bill_date < today`) and generates a multi-tab Excel report.

### 4. Unilever Impact / ShogunLite Trip Plan Sync (`/push_impact/`)
- Assigns bills to delivery vehicles using historical beat heuristics: if a dominant vehicle historically handled $\ge 40\%$ of a beat's volume or $\ge 4$ bills, unassigned bills auto-route to that vehicle.
- Authenticates via `/rsunify/app/impactDeliveryUrl` to retrieve SSO tokens.
- Accesses `shogunlite.com` session, extracts Apache Struts CSRF tokens, maps bill IDs to ShogunLite outlet codes (`selectedOutlets`), and posts to `ajxgetMovieBillnumber` to build the driver's trip plan.

### 5. Dispatch Dashboard (`/scan_summary/`)
- Provides trailing 4-day metrics:
  - By Bill Date: total bills, loaded bills, unallocated bills (`loading_time is null`).
  - By Loading Date: total loaded, delivered, and undelivered bills in transit.

---

## 4. Key Endpoints (`bill_scan/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/bill_scan/scan_bill/` | `views.scan_bill` | Scans individual bill or SM sheet to assign vehicle load or record delivery. |
| `POST` | `/bill_scan/download_scan_pdf/` | `views.download_scan_pdf` | Generates 6-column PDF loading manifest. |
| `POST` | `/bill_scan/delivery_applicable/` | `views.delivery_applicable` | Toggles delivery applicability and logs audit notes. |
| `GET` | `/bill_scan/scan_summary/` | `views.scan_summary` | Trailing 4-day dispatch & delivery reconciliation metrics. |
| `POST` | `/bill_scan/upload_vehicle_eway/` | `views.upload_vehicle_eway` | Generates NIC E-Way bills for vehicle load and returns driver PDF. |
| `POST` | `/bill_scan/upload_company_eway/` | `views.upload_company_eway` | Bulk generates E-Way bills for company bill date and returns Excel. |
| `POST` | `/bill_scan/push_impact/` | `views.push_impact` | Heuristically assigns bills and pushes trip dispatches to Unilever ShogunLite. |
| `GET` | `/bill_scan/vehicle/` | `modelviews.VehicleViewSet` | CRUD for delivery vehicles. |
| `GET` | `/bill_scan/bill_scan/` | `modelviews.BillScanViewSet` | Filterable list of bills (`company`, `vehicle`, `type`, `bill_date`, `loading_date`). |

---

## 5. Edge Cases & Operational Quirks

1. **Wholesale Beat Exclusion**: All dispatch workflows (`BillScanViewSet`, `scan_summary`, `push_impact`, `upload_company_eway`) explicitly exclude wholesale beats (`beat__contains="WHOLESALE"`), as wholesale buyers arrange their own transport.
2. **Hardcoded Defaults**: `eway.py` defaults to Tamil Nadu state code `33`, default pincode `620008`, and transit distance `3 km`.
3. **Date Restriction on Company E-Way**: `upload_company_eway` strictly rejects today's bills (`bill_date >= today` returns HTTP 400). Current-day bills must be filed per-vehicle via `upload_vehicle_eway`.
