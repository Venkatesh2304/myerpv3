# App: `erp` — Internal Accounting Ledger & Report Transformation Pipeline

> Purpose: Double-entry ERP accounting schema (Party, Stock, Inventory, Sales, Purchase) using composite primary keys and multi-column foreign objects, powered by the `erp_import.py` transformation pipeline.

---

## 1. Business Purpose & Operational Context

External reports from IKEA ERP are denormalized, flattened tabular dumps. To run statutory tax compliance, profit calculations, inventory tracking, and sales audit, the system requires a normalized, double-entry internal accounting ledger.

The `erp` app implements:
1. Normalized accounting models (`Sales`, `Purchase`, `Inventory`, `Stock`, `Party`, `Discount`).
2. Composite primary keys and multi-column foreign relationships (`ForeignObject`).
3. An atomic ETL import pipeline (`erp_import.py`) converting IKEA report rows into accounting entries.
4. An immutable audit replay engine ([`SalesChanges`](file:///home/ubuntu/myerpv3/erp/models.py#L156)) guaranteeing manual corrections survive automated re-imports.

---

## 2. Core Models & Schema (`erp/models.py`)

```
             ┌─────────────┐
             │   Company   │
             └──────┬──────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
      Party                   Stock
 (PK: company, code)     (PK: company, name)
        │                       │
        │ * ForeignObject       │ * ForeignObject
        ▼                       ▼
      Sales <───────────────── Inventory ──────────────────> Purchase
 (PK: company, inum)      (qty, txval, rt)             (PK: company, inum)
```

### 1. [`Party`](file:///home/ubuntu/myerpv3/erp/models.py#L29) (CompanyModel)
- **Composite PK**: `("company", "code")`.
- `name`, `master_code`, `addr`, `pincode`, `ctin`, `phone`, `type` (default `"shop"`).

### 2. [`Stock`](file:///home/ubuntu/myerpv3/erp/models.py#L46) (CompanyModel)
- **Composite PK**: `("company", "name")`.
- `hsn`, `desc`, `rt` (Central Tax rate, e.g. `9.0` for 18% GST), `standard_rate`.

### 3. [`Sales`](file:///home/ubuntu/myerpv3/erp/models.py#L98) (CompanyModel, PartyVoucher, GstVoucher)
- **Composite PK**: `("company", "inum")`.
- `amt`, `discount`, `roundoff`, `tds`, `tcs`, `ctin`, `irn`, `gst_period`.
- `type`: Enum (`sales`, `salesreturn`, `claimservice`, `damage`, `shortage`).
- **Party Relationship**: Linked via `ForeignObject` on `("company", "party_id")` $\rightarrow$ `Party("company", "code")`.
- **Audit Method (`update_and_log`)**: Saves field change in `transaction.atomic()` and appends an immutable audit log to `SalesChanges`.

### 4. [`Inventory`](file:///home/ubuntu/myerpv3/erp/models.py#L58) (CompanyModel)
- Line-item inventory transaction record: `stock_id`, `qty`, `txval` (3 decimals), `rt`.
- ForeignObject bindings:
  - `stock`: on `("company", "stock_id")` $\rightarrow$ `Stock("company", "name")`.
  - `sales`: on `("company", "bill_id")` $\rightarrow$ `Sales("company", "inum")` (`related_name="inventory"`).
  - `purchase`: on `("company", "pur_bill_id")` $\rightarrow$ `Purchase("company", "inum")`.

### 5. [`Discount`](file:///home/ubuntu/myerpv3/erp/models.py#L133) (CompanyModel)
- Line-item breakdown of voucher scheme deductions: `bill_id`, `sub_type` (`btpr`, `outpyt`, `ushop`, `pecom`, `other_discount`), `amt`, `moc`.

### 6. [`SalesChanges`](file:///home/ubuntu/myerpv3/erp/models.py#L156) (CompanyModel)
- Audit trail logging all automated and manual changes to sales vouchers: `bill_id`, `field`, `notes`, `old_value`, `new_value`, `time`.

---

## 3. The Transformation Pipeline (`erp/erp_import.py`)

### 1. `SalesImport` (Outward Sales, Returns & Claims)
- **Sources**: `SalesRegisterReport` (header totals, discounts) and `IkeaGSTR1Report` (item lines, rates).
- **Outward Invoices**: Matched 1-to-1 between reports.
- **Sales Returns Reconciliation**: In IKEA, returns reference original bill numbers, whereas GST mandates credit note numbers (`credit_note_no`). `SalesImport` matches original invoices to credit notes, inverts signs (`txval = -txval`), and handles 1-to-many credit note splits.
- **Claim Service Synthesis**: Aggregates claims by `inum`, calculates tax and TDS (2%), and generates synthetic vouchers with `party_id="HUL"`.
- **Double-Entry Convention**:
  - Outward receivables: `amt = -qs.amt`, `discount = -total_discounts`, `tds = -qs.tds`.
- Upserts distinct SKUs into `Stock` and bulk creates `Inventory` lines.

### 2. `MarketReturnImport` (Damages & Shortages)
- **Source**: `DmgShtReport` where `return_from="market"`.
- Uses Subqueries to fetch `rt` from `Stock` and recent `ctin` from `Sales`.
- Backcalculates taxable value: $\text{txval} = \text{round}(\frac{\text{amt} \times 100}{100 + 2 \times \text{rt}}, 3)$.

---

## 4. `GstFilingImport` Orchestration & Audit Replay

`GstFilingImport.run(company, args_dict)` coordinates the end-to-end import:

```
Step 1: Parallel Report Fetching
  ThreadPoolExecutor(max_workers=10) triggers report.update_db()
  for all required reports from IKEA.
            │
            ▼
Step 2: Sequential Atomic Import
  SalesImport.run_atomic()
  PartyImport.run_atomic()
  StockImport.run_atomic()
  MarketReturnImport.run_atomic()
            │
            ▼
Step 3: Audit Trail Replay (SalesChanges)
  Replays all historical manual changes recorded in SalesChanges
  (e.g., clearing invalid GSTINs, adjusting dates).
```

**Why Audit Replay Matters**: Re-running imports from external reports will not overwrite manual corrections (e.g. invalid GSTIN fixes). The replay loop re-applies all edits automatically after bulk insertion.
