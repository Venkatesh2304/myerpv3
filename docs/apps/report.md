# App: `report` — Generic External Report ETL & Caching Engine

> Purpose: Ingestion, normalization, disk caching, and high-performance SQLAlchemy bulk storage of tabular reports from IKEA Leveredge and the GST Portal.

---

## 1. Business Purpose & Operational Context

The distributor relies on dozens of disparate upstream tabular reports for billing, credit control, inventory, and statutory compliance. Upstream portals (IKEA and GSTN) are slow, subject to transient timeouts, and output non-standard schemas.

The `report` app functions as an external ETL and caching layer:
- Normalizes raw portal exports into structured pandas DataFrames.
- Implements disk pickling for date-ranged queries to prevent redundant network fetches.
- Performs high-performance bulk insertions into PostgreSQL via SQLAlchemy.
- Tracks cache staleness and sync audit timestamps in [`ReportSyncLog`](file:///home/ubuntu/myerpv3/report/models.py#L30).

---

## 2. Generic Report Architecture (`report/models.py`)

```
BaseReport[ArgsT] (Generic fetcher & pandas preprocessor)
   ├── DateReportModel.Report (Generic[DateRangeArgs], disk caching in .cache/)
   ├── EmptyReportModel.Report (Generic[EmptyArgs], live snapshot fetcher)
   └── GSTR1Portal.Report (Generic[MonthArgs], fetches b2b/cdnr from GST portal)

BaseReportModel[ArgsT] (Abstract Model + SQLAlchemy bulk saver)
   ├── CompanyReportModel[ArgsT] (Scoped to Company)
   │     ├── DateReportModel (Keyed on company + date range)
   │     │     ├── SalesRegisterReport
   │     │     ├── IkeaGSTR1Report
   │     │     ├── DmgShtReport
   │     │     ├── DseReport
   │     │     ├── DamageDebitNoteReport
   │     │     ├── CollectionReport (15-day sliding batching)
   │     │     ├── PurchaseDmgShtReport
   │     │     ├── IkeaGSTR2Report
   │     │     ├── Adjustment
   │     │     └── ClaimsReport
   │     └── EmptyReportModel (Full table refresh per company)
   │           ├── OutstandingReport
   │           ├── BillAgeingReport
   │           ├── BeatReport
   │           ├── StockHsnRateReport
   │           ├── PartyReport
   │           └── StockReport
   └── OrganizationReportModel[ArgsT] (Scoped to Organization)
         └── GSTR1Portal (MonthArgs period MMYYYY)
```

---

## 3. The Ingestion Pipeline (`update_db`)

When `ReportModel.update_db(client, scope_instance, args)` is invoked:

1. **Fetching (`get_dataframe`)**: Calls `cls.fetch_raw_dataframe()` with automated retries.
   - For `DateReportModel`, checks `.cache/<ReportClass>/<fromd>_<tod>.pkl`. If cached and valid, loads directly from disk.
2. **Preprocessing Pipeline**:
   - `basic_preprocessing`: Drops footer metadata rows (`ignore_last_nrows`), renames columns via `column_map`, parses dates, and filters nulls.
   - `custom_preprocessing`: Subclass-specific calculations (e.g. net tax adjustments, negative sign normalization).
3. **Partition Deletion (`delete_before_insert`)**:
   - `DateReportModel`: Clears existing records within `[fromd, tod]`.
   - `EmptyReportModel`: Clears all existing records for that company.
4. **SQLAlchemy High-Performance Bulk Insert (`save_to_db`)**:
   - Validates that DataFrame contains all model concrete fields.
   - Bypasses Django ORM overhead by writing directly using SQLAlchemy:
     ```python
     df[cols].to_sql(cls._meta.db_table, engine, if_exists="append", index=False)
     ```
5. **Sync Audit**: Records execution timestamp in [`ReportSyncLog`](file:///home/ubuntu/myerpv3/report/models.py#L30).

---

## 4. Key Concrete Reports & Business Meaning

| Model | Upstream Source | Primary Key / Scope | Business Purpose |
| :--- | :--- | :--- | :--- |
| [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276) | `Ikea.sales_reg()` | `(company, date)` | Official invoice register: net bill amounts, tax, schemes, and line-level discounts. |
| [`IkeaGSTR1Report`](file:///home/ubuntu/myerpv3/report/models.py#L336) | `Ikea.gstr_report()` | `(company, date)` | Tax-rate breakdown of sales lines, returns, and credit note linkage (`original_invoice_no`). |
| [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576) | `Ikea.outstanding()` | `company` | Current customer dues, balances, and overdue days. |
| [`CollectionReport`](file:///home/ubuntu/myerpv3/report/models.py#L508) | `Ikea.collection()` | `(company, date)` | Receipt ledger. *Note: Overrides `update_db` to chunk requests into 15-day sliding windows.* |
| [`PartyReport`](file:///home/ubuntu/myerpv3/report/models.py#L692) | `Ikea.party_master()` | Composite PK `("company", "code")` | Retailer master list: address, phone, GSTIN, beat mapping. |
| [`StockReport`](file:///home/ubuntu/myerpv3/report/models.py#L727) | `Ikea.current_stock()` | `company` | Snapshot of warehouse inventory across godowns, batches, and MRPs. |
| [`GSTR1Portal`](file:///home/ubuntu/myerpv3/report/models.py#L803) | `Gst.getinvs()` | `(organization, period)` | Live filed B2B and CDNR invoice downloads from the government GST portal. |

---

## 5. Key Endpoints & APIs (`report/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/report/salesman/` | `views.salesman` | Distinct active salesmen from `BeatReport`. |
| `GET` | `/report/party/` | `views.party` | Active retailers within last 16 weeks from `SalesRegisterReport`. |
| `GET` | `/report/party_credibility/` | `views.party_credibility` | Retailer payment credibility stats: weighted average collection days and order value. |
| `GET` | `/report/sync_reports/` | `views.sync_reports` | Ad-hoc manual trigger to run `update_db()` for specified report models. |
| `POST` | `/report/outstanding_report/` | `views.outstanding_report_view` | Generates 3-sheet Excel (`21 Days`, `28 Days`, `ALL BILLS`). |
| `POST` | `/report/stock_report/` | `views.stock_report_view` | Multi-company stock comparison workbook for Main Godown. |
| `POST` | `/report/pending_sheet/` | `views.pending_sheet_pdf` | Generates duplex-ready PDF collection sheets with cash denomination grids. |

---

## 6. Edge Cases & Gotchas

1. **System Check Enforcement**: The registered check `reportmodel_date_field_check` validates that every model inheriting from `DateReportModel` contains a concrete `date` field; otherwise, Django startup halts with `reportmodel.E001`.
2. **Collection 15-Day Sliding Window**: IKEA's collection endpoint times out if querying ranges $> 15\text{ days}$. `CollectionReport.update_db` automatically breaks date ranges into 15-day sub-intervals.
3. **EmptyReport Wipes Whole Company**: Updating an `EmptyReportModel` (like `OutstandingReport` or `PartyReport`) deletes all existing rows for that company before insertion.
