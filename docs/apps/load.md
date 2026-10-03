# App: `load` — Inbound Purchase Product Load Check

> Purpose: Inbound truckload intake verification, parsing HUL purchase invoice PDFs with bounding box extraction, carton scanning, and multi-tier mismatch reconciliation.

---

## 1. Business Purpose & Operational Context

When an HUL factory or depot supply truck arrives at the distributor warehouse:
- The truck carries outer cartons (cases) containing consumer goods.
- Delivery invoices list billed CBU codes, SKU codes, MRPs, and case quantities.
- Common delivery errors include:
  1. Missing or extra cartons.
  2. MRP mismatch: Receiving cartons with higher or lower printed MRPs than billed on the invoice (critical for tax credits and distributor gross margin).

The `load` app parses incoming invoice PDFs, tracks physical carton scans box-by-box as goods are unloaded, and exports a reconciliation report categorizing physical and valuation variances before the truck departs.

---

## 2. Core Model (`load/models.py`)

### [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5)
Represents a single unloading session for an inbound truck.
- `organization`: `ForeignKey(Organization)`
- `created_at`: `DateTimeField(auto_now_add=True)`
- `completed`: `BooleanField(default=False)`
- `purchase_inums`: JSONField list of invoice numbers (e.g. `["INV1001", "INV1002"]`).
- `sku_map`: JSONField mapping `{"<CBU_CODE>": "<SKU_CODE>"}`.
- `purchase_products`: JSONField nested map of `{inum: {cbu: {mrp: qty}}}`.
- `scanned_products`: JSONField list of boxes. Index `i` represents Box `i+1`. Each element is `{cbu: {mrp: scanned_qty}}`.
  - *Dynamic Buffer Rule*: The system keeps an empty `{}` at the end of the list as a buffer for the next box.

---

## 3. PDF Parsing with Exact Bounding Boxes (`load/views.py`)

HUL purchase invoice PDFs are parsed using `pdfplumber` with coordinate cropping (1 cm ≈ 28.35 pt):
- `width_limit_pts = 3.5 * 28.35` (~99.23 pt)
- `qty_offset = 13.2 * 28.35` (~374.22 pt)

1. **Invoice Number**: Extracted from Page 0 text line 0.
2. **Codes Column (BBox `0` to `width_limit_pts`)**: Sliced between `"SKU code"` and `"Net Payabl"`. Alternates: Even lines = CBU code; Odd lines = SKU code.
3. **Quantities & MRP Column (BBox `qty_offset` to `qty_offset + width_limit_pts`)**: Sliced after `"Old MRP\n"`, filters `"TAX"`. Triplets per item:
   - Line 0: Case Quantity (`int(qty.split("/")[0])`)
   - Line 1: MRP (`int(mrp.split(".")[0])`)

---

## 4. Unloading & Reconciliation Workflow

```
[Inbound HUL Truck]
         │
         ▼
1. POST /load/upload_purchase_invoice/
   - Uploads PDF invoice, extracts items, populates purchase_products & sku_map
         │
         ▼
2. GET /load/get_last_load/
   - Returns active TruckLoad ID or creates a new session
         │
         ▼
3. Unloading & Scanning Box N:
   ├── GET /load/box/?load=X&box_no=N  (Fetches current box items & previous box totals)
   └── POST /load/box/                 (Saves scanned counts; appends empty buffer {})
         │
         ▼
4. GET /load/download_load_summary/?load=X
   - Joins purchase_products vs scanned_products on (cbu, mrp)
   - Fetches SKU descriptions from IKEA product_wise_purchase
   - Classifies variances into 4 categories:
       * Mismatch (CBU): Case quantity shortage or excess
       * Mismatch (Higher MRP): Total cases match, but received higher MRP stock
       * Mismatch (Lower MRP): Total cases match, but received lower MRP stock
       * Correct: Exact match on quantity and MRP
   - Generates 8-sheet Excel reconciliation workbook
```

---

## 5. Key Endpoints (`load/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/load/upload_purchase_invoice/` | `views.upload_purchase_invoice` | Ingests HUL PDF invoice and updates `purchase_products`. |
| `GET` | `/load/get_last_load/` | `views.get_last_load` | Retrieves latest uncompleted `TruckLoad` ID. |
| `GET` / `POST` | `/load/box/` | `views.box` | `GET`: Read box contents. `POST`: Commit carton scan and increment box. |
| `GET` | `/load/download_load_summary/` | `views.download_load_summary` | Generates multi-sheet reconciliation Excel. |
| `GET` | `/load/load_summary/` | `modelviews.LoadSummaryViewSet` | Lists loads with invoice lines, cases, and scan stats. |

---

## 6. Edge Cases & Gotchas

1. **Artificial Delay**: `upload_purchase_invoice` includes an intentional `time.sleep(19)` delay.
2. **Layout Shifts in Invoices**: If HUL modifies invoice header padding or table column order, `codes[::2]` and `qtys[1::3]` coordinate slicing will misalign.
3. **IKEA Report Dependency**: Summary export fetches SKU names from `Ikea.product_wise_purchase` for the previous 15 days. If the IKEA session is down, name resolution fails.
