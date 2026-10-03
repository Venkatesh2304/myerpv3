# Django Apps Guide & Master Architecture Map

> Purpose: Central routing directory connecting system workflows to the 12 individual app deep-dive guides.  
> Rule: Use progressive disclosure. Read the dedicated app guide in `docs/apps/<app>.md` when working on a specific domain.

---

## 1. App-by-App Navigation Directory

| App & Deep-Dive Link | Domain Role | Core Models | Key Operational Endpoints |
| :--- | :--- | :--- | :--- |
| **[`core`](file:///home/ubuntu/myerpv3/docs/apps/core.md)** | Multi-tenancy, JWT auth, external portal credentials & session persistence. | [`User`](file:///home/ubuntu/myerpv3/core/models.py#L9), [`Organization`](file:///home/ubuntu/myerpv3/core/models.py#L16), [`Company`](file:///home/ubuntu/myerpv3/core/models.py#L19), [`UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27) | `/login`, `/usersession`, `/ikea_login`, `/trigger_ikea_login` |
| **[`erp`](file:///home/ubuntu/myerpv3/docs/apps/erp.md)** | Double-entry accounting ledger & report transformation pipeline. | [`Sales`](file:///home/ubuntu/myerpv3/erp/models.py#L98), [`Purchase`](file:///home/ubuntu/myerpv3/erp/models.py#L119), [`Inventory`](file:///home/ubuntu/myerpv3/erp/models.py#L58), [`Stock`](file:///home/ubuntu/myerpv3/erp/models.py#L46), [`Party`](file:///home/ubuntu/myerpv3/erp/models.py#L29) | Orchestrated via [`erp_import.GstFilingImport`](file:///home/ubuntu/myerpv3/erp/erp_import.py) |
| **[`report`](file:///home/ubuntu/myerpv3/docs/apps/report.md)** | Generic ETL, caching, and SQLAlchemy bulk storage for raw portal reports. | [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276), [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576), [`CollectionReport`](file:///home/ubuntu/myerpv3/report/models.py#L508), [`PartyReport`](file:///home/ubuntu/myerpv3/report/models.py#L692), [`GSTR1Portal`](file:///home/ubuntu/myerpv3/report/models.py#L803) | `/report/sync_reports/`, `/report/outstanding_report/`, `update_db()` methods |
| **[`bill`](file:///home/ubuntu/myerpv3/docs/apps/bill.md)** | Market order billing pipeline, party credit risk rules, invoice posting. | [`Billing`](file:///home/ubuntu/myerpv3/bill/models.py#L11), [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53), [`PartyCredit`](file:///home/ubuntu/myerpv3/bill/models.py#L107) | `/bill/get_order/`, `/bill/post_order/`, `/bill/order/` |
| **[`bill_scan`](file:///home/ubuntu/myerpv3/docs/apps/bill_scan.md)** | Delivery dispatch loading verification, vehicle assignment, E-Way bills. | Uses [`bill.Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53) & [`bill.Vehicle`](file:///home/ubuntu/myerpv3/bill/models.py#L45) | `/bill_scan/scan_bill/`, `/bill_scan/upload_vehicle_eway/`, `/bill_scan/push_impact/` |
| **[`load`](file:///home/ubuntu/myerpv3/docs/apps/load.md)** | Inbound purchase product load check: PDF coordinate extraction & box scanning. | [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5) | `/load/upload_purchase_invoice/`, `/load/box/`, `/load/download_load_summary/` |
| **[`product_scan`](file:///home/ubuntu/myerpv3/docs/apps/product_scan.md)** | Sales box packing verification, SKU barcode mapping, CCTV video audit. | [`SalesScan`](file:///home/ubuntu/myerpv3/product_scan/models.py#L5), [`Barcode`](file:///home/ubuntu/myerpv3/product_scan/models.py#L190) | `/product_scan/sales_scan_id/`, `/product_scan/sales_box/`, `/product_scan/video_process/` |
| **[`bank`](file:///home/ubuntu/myerpv3/docs/apps/bank.md)** | Bank statement reconciliation, ML party classification, collection push. | [`BankStatement`](file:///home/ubuntu/myerpv3/bank/models.py#L59), [`BankCollection`](file:///home/ubuntu/myerpv3/bank/models.py#L32), [`ChequeDeposit`](file:///home/ubuntu/myerpv3/bank/models.py#L11) | `/bank/bank_statement_upload/`, `/bank/smart_match/`, `/bank/push_collection/` |
| **[`gst`](file:///home/ubuntu/myerpv3/docs/apps/gst.md)** | GSTR-1 return reconciliation, statutory JSON filing, E-Invoice lifecycle. | Models in `erp` and `report` | `/gst/generate`, `/gst/json`, `/einvoice/file`, `/custom/captcha`, `/custom/login` |
| **[`printing`](file:///home/ubuntu/myerpv3/docs/apps/printing.md)** | Dot-matrix (TVS MSP 250 Star) & laser printing engine with 2-pass check. | [`SalesmanLoadingSheet`](file:///home/ubuntu/myerpv3/bill/models.py#L33), logic in `printing/printers.py` | `/printing/print_bills/` |
| **[`ledger`](file:///home/ubuntu/myerpv3/docs/apps/ledger.md)** | Unilever SAP vendor ledger ingestion and MOC-based discrepancy verification. | [`Ledger`](file:///home/ubuntu/myerpv3/ledger/models.py) | `/ledger/import/`, `verify_ledger` CLI |
| **[`misc`](file:///home/ubuntu/myerpv3/docs/apps/misc.md)** | Scheduled automation: 28-day overdue summary emails, monthly 7z bill archives. | Stateless utility views | `/misc/mail_reports/`, `/misc/mail_bills/`, `/misc/beat_export/` |

---

## 2. Core Business Workflows Quick-Index

1. **Purchase Product Inbound Verification**: See [docs/apps/load.md](file:///home/ubuntu/myerpv3/docs/apps/load.md).
2. **Bank Statement Reconciliation & Collection Push**: See [docs/apps/bank.md](file:///home/ubuntu/myerpv3/docs/apps/bank.md).
3. **Market Order Billing Pipeline**: See [docs/apps/bill.md](file:///home/ubuntu/myerpv3/docs/apps/bill.md).
4. **Physical Dispatch & E-Way Bill Generation**: See [docs/apps/bill_scan.md](file:///home/ubuntu/myerpv3/docs/apps/bill_scan.md).
5. **Sales Carton Packing Verification & Video Audit**: See [docs/apps/product_scan.md](file:///home/ubuntu/myerpv3/docs/apps/product_scan.md).
6. **Production Invoice Printing Engine**: See [docs/apps/printing.md](file:///home/ubuntu/myerpv3/docs/apps/printing.md).
7. **Statutory GSTR-1 Reconciliation & NIC E-Invoicing**: See [docs/apps/gst.md](file:///home/ubuntu/myerpv3/docs/apps/gst.md).
8. **Unilever SAP Vendor Ledger Audit**: See [docs/apps/ledger.md](file:///home/ubuntu/myerpv3/docs/apps/ledger.md).
9. **Generic Report Caching Framework**: See [docs/apps/report.md](file:///home/ubuntu/myerpv3/docs/apps/report.md).
10. **Normalized Double-Entry Accounting Ledger**: See [docs/apps/erp.md](file:///home/ubuntu/myerpv3/docs/apps/erp.md).
11. **Multi-Tenancy & External Credential Store**: See [docs/apps/core.md](file:///home/ubuntu/myerpv3/docs/apps/core.md).
12. **Scheduled Operations & Archiving**: See [docs/apps/misc.md](file:///home/ubuntu/myerpv3/docs/apps/misc.md).

---

## 3. "Where Do I Solve / Add X?" Reference

| Requirement | Primary App & File | Secondary / Related Files |
| :--- | :--- | :--- |
| Add new upstream report from IKEA | [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py) | [`custom/curl/ikea/`](file:///home/ubuntu/myerpv3/custom/curl/ikea/), [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py) |
| Modify party credit limits or risk formula | [`bill/credit_logic.py`](file:///home/ubuntu/myerpv3/bill/credit_logic.py) | [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py), [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py) |
| Tune ML narration party classifier | [`bank/views.py`](file:///home/ubuntu/myerpv3/bank/views.py) | `party_classifier_*.joblib`, `tfidf_vectorizer_*.joblib` |
| Adjust vehicle route assignments | [`bill_scan/views.py`](file:///home/ubuntu/myerpv3/bill_scan/views.py) | [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py) (`push_impact`) |
| Modify invoice print layout or Aztec 2D code | [`printing/printers.py`](file:///home/ubuntu/myerpv3/printing/printers.py) | [`printing/print.py`](file:///home/ubuntu/myerpv3/printing/print.py), [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py) |
| Fix HUL purchase invoice PDF parsing | [`load/views.py`](file:///home/ubuntu/myerpv3/load/views.py) | `extract_product_quantities` |
| Fix statutory GSTR-1 JSON construction | [`gst/gst.py`](file:///home/ubuntu/myerpv3/gst/gst.py) | [`gst/api.py`](file:///home/ubuntu/myerpv3/gst/api.py), [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py) |
| Handle NIC E-Invoice rejection error code | [`gst/einvoice.py`](file:///home/ubuntu/myerpv3/gst/einvoice.py) | [`gst/api.py`](file:///home/ubuntu/myerpv3/gst/api.py), [`erp/models.py`](file:///home/ubuntu/myerpv3/erp/models.py) |
| Modify packing discrepancy detection | [`product_scan/models.py`](file:///home/ubuntu/myerpv3/product_scan/models.py) | [`product_scan/views.py`](file:///home/ubuntu/myerpv3/product_scan/views.py) |
