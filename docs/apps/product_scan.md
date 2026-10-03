# App: `product_scan` — Sales Invoice Carton Packing Verification & Video Audit

> Purpose: Verification of packed retail carton goods against sales invoices retrieved from IKEA ERP, barcode and CBU resolution, anomaly/fake scan detection, and CCTV video audit clipping.

---

## 1. Business Purpose & Operational Context

In the distributor warehouse, outbound goods packed for retail delivery must be audited against customer invoices:
- Packers assembling cartons can miss items, pack wrong quantities, or substitute products.
- Packing discrepancies result in retailer disputes, rejected deliveries, and credit notes.
- In addition to counting errors, operators may engage in fraud (e.g., scan simulation without physical goods).

The `product_scan` app provides:
1. Box-by-box barcode and CBU scanning mapped against live line items fetched from IKEA ERP.
2. Real-time mismatch detection (shortages and excesses).
3. Packing log anomaly detection (rapid clicks < 700ms, manual barcode overrides).
4. Video audit subsystem linking Hikvision NVR security footage directly to scan timestamps, exporting trimmed snapshots and overlaying product names onto video.

---

## 2. Core Models & Schema (`product_scan/models.py`)

### [`SalesScan`](file:///home/ubuntu/myerpv3/product_scan/models.py#L5) (CompanyModel)
Tracks the packing verification session for a single sales invoice.
- **Constraint**: `unique_together = ('bill_no', 'company_id')`.
- `bill_no`: Invoice reference string.
- `bill_date`, `party_name`: Customer metadata.
- `is_posted`: `BooleanField`. True when locked/posted in IKEA ERP (`blhStatus != 0`).
- `bill_products`: JSONField containing expected items:
  ```json
  {
    "<sku_code>": {
      "<mrp>": {
        "qUnits": 12,
        "qCases": 1,
        "unitsCase": 12,
        "basepack": "29802",
        "name": "LUX SOAP 100G"
      }
    }
  }
  ```
- `scanned_products`: JSONField list of box dictionaries: `[ { "<sku_code>": { "<mrp>": <qty> } }, ... ]`.
- `logs`: JSONField list of per-box scan events with millisecond timestamps (`timestamp`, `type`, `sku`, `value`).
- `video_file`: FileField storing raw uploaded CCTV MP4 footage.
- `video_status`: Enum (`none`, `pending`, `completed`, `failed`).
- `video_start_time`, `video_end_time`: DateTimeField range for CCTV NVR extraction.

### [`Barcode`](file:///home/ubuntu/myerpv3/product_scan/models.py#L190)
Cross-references retail EAN-13 barcodes to HUL basepacks.
- `barcode`: CharField primary key (e.g. `"8901030999949"`).
- `basepack`: CharField HUL basepack code.
- `manual`: BooleanField. True if created or edited manually by a supervisor.

---

## 3. Barcode & CBU Resolution

When a barcode is scanned:
- **EAN Barcodes**: Looked up in [`Barcode`](file:///home/ubuntu/myerpv3/product_scan/models.py#L190) model to find the corresponding `basepack`, matching `itemVarCode` in `bill_products`.
- **CBU Outer Case Codes**: Resolved via `get_cbu_data()`:
  - Combines `cbu.json` static prefixes.
  - Queries Postgres `load_truckload.sku_map` (`jsonb_each`) from the inbound `load` app to resolve the freshest CBU-to-SKU mapping.

---

## 4. Live IKEA Bill Retrieval & Synchronization

- `Ikea.retrive_bill(bill_no)`:
  1. Clears existing session screen locks.
  2. Queries `/rsunify/app/billing/retrievebill?billRef=<bill_no>`.
  3. **Immediate Lock Release**: Calls `/rsunify/app/billing/deletemutable?salesmanId=<id>` so billing clerks aren't blocked in the native desktop ERP.
- **Cancelled Bill Purge**: If `blh_status == 4` (bill cancelled in IKEA) and nothing has been scanned, the `SalesScan` record is automatically pruned from the database.

---

## 5. Verification, Anomaly & Video Audit Subsystems

### 1. Mismatch Calculation (`SalesScan.mismatches`)
- Total billed units = `(qCases * unitsCase) + qUnits`.
- Discrepancies between billed and scanned totals are flagged immediately per SKU and MRP.

### 2. Anomaly Analysis (`views.anomaly_analysis`)
- **Fake Scans**: Consecutive scan events for the same SKU occurring $< 700\text{ ms}$ apart. If `fake_count / total_items >= 0.5`, flagged as automated scanner clicking without handling physical goods.
- **Manual Overrides**: Flagged when operator enters barcodes manually via UI.

### 3. Video Audit Workflow (`views.py`)
1. **NVR Polling (`/video_tasks/`)**: Background downloader polls for completed scans inactive for > 30 mins, requesting CCTV video for the time range (capped at 25 minutes).
2. **Video Upload (`/video_upload/`)**: NVR downloader posts raw MP4 video.
3. **Clip & Overlay Engine (`/video_process/`)**:
   - `req_type='photo'`: Uses `ffmpeg -ss <ts> -frames:v 1` to extract single snapshot of the scan moment.
   - `req_type='clip'`: Cuts a 30-second video clip around the scan.
   - Full video with overlay: Dynamically builds FFmpeg `drawtext` filters overlaying the scanned product name in red text during each scan's 4-second window.

---

## 6. Key Endpoints (`product_scan/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/product_scan/sales_scan_id/` | `views.sales_scan_id` | Initializes scan session, fetching live line items from IKEA. |
| `GET` / `POST` | `/product_scan/sales_box/` | `views.scan_sales_box` | Reads/writes box contents and logs. Auto-appends `{}` buffer. |
| `POST` | `/product_scan/sales_scan_summary/` | `views.sales_scan_summary` | Generates monochrome packing slip PDF. |
| `POST` | `/product_scan/sales_scan_mismatch/` | `views.sales_scan_mismatch` | Returns list of item shortages/excesses. |
| `GET` | `/product_scan/anomaly_analysis/` | `views.anomaly_analysis` | Scans for fake clicks (<700ms) and manual overrides. |
| `GET` / `POST` | `/product_scan/barcode/` | `views.barcode_view` | Resolves barcode to SKUs or creates manual mappings. |
| `GET` | `/product_scan/video_tasks/` | `views.get_video_tasks` | CCTV NVR polling endpoint. |
| `POST` | `/product_scan/video_upload/` | `views.upload_scan_video` | CCTV NVR video file upload. |
| `POST` | `/product_scan/video_process/` | `views.get_processed_video` | Extracts photo snapshot, 30s clip, or subtitle-overlaid video. |
| `GET` | `/product_scan/sales_scan/` | `modelviews.SalesScanViewSet` | Paginated scan list with background IKEA synchronization. |
