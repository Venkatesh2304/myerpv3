# App: `gst` — Statutory GSTR-1 Reconciliation, JSON Filing & E-Invoice Lifecycle

> Purpose: Monthly GSTR-1 return reconciliation against live portal data, statutory JSON generation, NIC E-Invoicing (IRN generation), and government captcha authentication.

---

## 1. Business Purpose & Operational Context

FMCG distributors operate under strict GST compliance:
1. **NIC E-Invoicing**: B2B sales invoices require real-time registration on the National Informatics Centre (NIC) IRP portal to generate 64-character Invoice Reference Numbers (IRNs).
2. **Monthly GSTR-1 Return Filing**: Monthly sales must reconcile with the GSTN portal. Differences arise from promotional zero-rate goods, credit notes, and manual portal edits.
3. **Statutory GSTR-1 JSON**: The system must output the official government JSON payload (`b2b`, `b2cs`, `cdnr`, `hsn`, `doc_issue`, `nil`) for direct upload.

---

## 2. Monthly GSTR-1 Return Generator (`gst/gst.py`)

`gst.generate(organization, period, gst_client)` executes the reconciliation:

```
Internal Accounting (Sales, Inventory)          GSTR-1 Portal Data (GSTR1Portal)
                    │                                          │
                    └───────────────────┬──────────────────────┘
                                        │
                                        ▼
                             diff_dataframes(inum)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
                 Missing              Extra              Mismatch
           (in ERP, not portal)   (in portal, not ERP) (txval / cgst diff)
                    │                   │
         ┌──────────┴──────────┐        ▼
         ▼                     ▼  Fetch NIC ItemList
    irn is null           irn not null  via get_einv_data()
   (To File B2B)       (Yet to be Pushed)
```

### 1. Classification & Difference Detection (`diff_dataframes`)
- Internal sales vouchers are classified as `b2b`, `b2c`, or `cdnr`.
- Compares against [`GSTR1Portal`](file:///home/ubuntu/myerpv3/report/models.py#L803) live downloads:
  - **`missing`**: Present in ERP but absent on the portal. Partitioned into:
    * `yet_to_be_pushed`: Already has an IRN (registered on NIC, pending auto-sync to GSTN).
    * `missing`: Lacks IRN; needs immediate filing.
  - **`extra`**: Invoices found on portal but absent from local ERP. Fetches item lines directly from NIC via `gst.get_einv_data()`.
  - **`mismatch`**: Present in both, but $|txval_{erp} - txval_{portal}| > 1$ or $|cgst_{erp} - cgst_{portal}| > 0.5$.

### 2. Zero-Rate Tax Correction (`registered_zero_rate`)
- **Business Problem**: Schemes and promotional items (e.g. food grains, free goods) have zero tax rate (`rt=0`). In ERP, they are included in invoice totals, but upstream e-invoicing systems omit them from taxable value, creating apparent tax mismatches.
- **Resolution**: Evaluates:
  $$\text{abs}(txval_{erp} - zero\_rate\_txval - txval_{portal}) < 1$$
  Zero-rate taxable amounts are deducted from B2B/CDNR taxable sums and routed to the GSTR-1 `"nil"` (Nil Rated / Exempt) section.

### 3. Statutory GSTR-1 JSON Output (`static/<org>/<period>.json`)
- **B2B & CDNR**: Contains only `mismatch` and true `missing` documents. Matching portal documents are omitted to prevent duplicate overwrites.
- **B2CS**: Consolidated intra-state supplies grouped by rate (`sply_ty="INTRA"`).
- **HSN Table with Negative Rate Absorption**: When return credits exceed sales for an HSN/rate, producing negative net tax, the negative amount is rolled into the highest positive HSN for that rate (`max_hsn_per_rt`).
- **Doc Issue**: Calculates `from`, `to`, `totnum`, `cancel`, and `net_issue` for invoices and credit notes.
- **Nil Rated**: Populated with `nil_amt` from zero-rate corrections under supply type `"INTRAB2B"`.

---

## 3. E-Invoice Lifecycle (`gst/einvoice.py` & `gst/api.py`)

### 1. Payload Creation & 28-Day Capping (`change_einv_dates`)
- Builds NIC schema v1.1 JSON from [`erp.models.Sales`](file:///home/ubuntu/myerpv3/erp/models.py#L98) and `Inventory`.
- **Government Restriction**: The NIC portal strictly rejects invoices dated $> 28\text{ days}$ in the past.
- `change_einv_dates()` caps overdue document dates to `fallback_date` (the last day of the filing month).

### 2. Batch Upload & Automated Error Recovery (`file_einvoice`)
- Uploads to `/Invoice/BulkUpload` on the NIC portal.
- **Error Code 2150 (Duplicate IRN)**: The invoice was already registered. Extracts the 64-character hex IRN directly from the error string via regex `([a-f0-9]{64})` and updates `Sales.irn`.
- **Error Codes 3074 to 3079 (Invalid / Cancelled Buyer GSTIN)**: Automatically demotes the voucher to B2C by setting `ctin=None` via `inv.update_and_log("ctin", None, error)` and recording the change in [`SalesChanges`](file:///home/ubuntu/myerpv3/erp/models.py#L156).

---

## 4. Captcha Authentication & Security Precautions

Direct portal access ([`Gst`](file:///home/ubuntu/myerpv3/custom/classes.py#L930) and [`Einvoice`](file:///home/ubuntu/myerpv3/custom/classes.py#L1245)) requires solving image captchas:

1. **`@check_login(Client)` Decorator**:
   - Probes `client.is_logged_in()`. If False $\rightarrow$ returns HTTP 501 `{"key": client.key}`.
2. **`POST /custom/captcha`**:
   - Takes `{"key": "gst" | "einvoice"}`.
   - Clears stale cookies, fetches captcha image bytes from the portal, caches session tokens, and returns `image/png`.
3. **`POST /custom/login`**:
   - Takes `{"key": "gst" | "einvoice", "captcha": "<text>"}`.
   - Hashes passwords with portal salts and machine fingerprints.
   - On success, saves session cookies into [`UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27).

> [!CAUTION]
> **Strict Lockout Risk**: Entering wrong credentials or failed captchas $\ge 5$ times triggers `GstMultipleWrongAttempts` (portal error `SWEB_9014`), locking the distributor's tax account or banning the server IP. Never loop retries on failed captcha attempts.

---

## 5. Key Endpoints (`gst/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/custom/captcha` | `api.get_captcha` | Fetches captcha PNG image for GST or E-Invoice portal. |
| `POST` | `/custom/login` | `api.captcha_login` | Solves captcha and establishes authenticated session. |
| `POST` | `/einvoice/file` | `api.file_einvoice` | Batch uploads B2B invoices to NIC; auto-recovers IRNs and invalid GSTINs. |
| `POST` | `/einvoice/stats` | `api.einvoice_stats` | Filing statistics per company/type by IRN presence. |
| `POST` | `/einvoice/reload` | `api.einvoice_reload` | Refreshes IRNs from GST and E-Invoice portals. |
| `POST` | `/einvoice/pdf` | `api.einvoice_pdf` | Headless Chrome PDF generation and ZIP archiving per party. |
| `POST` | `/gst/generate` | `api.generate_gst_return` | Executes reconciliation; generates `workings_<period>.xlsx` and JSON. |
| `POST` | `/gst/summary` | `api.gst_summary` | Downloads generated workings Excel workbook. |
| `POST` | `/gst/json` | `api.gst_json` | Downloads official statutory GSTR-1 JSON file. |
