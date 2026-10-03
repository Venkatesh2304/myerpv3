---
name: hul-reconciliation-ops
description: Operational runbook and execution procedures for running periodic reconciliations, statutory filings, sync jobs, and system maintenance in HUL Distributor ERP (myerpv3). Use when executing monthly GST imports, filing GSTR-1, verifying Unilever SAP ledger, running bank statement matching, pushing collections to IKEA, or restarting system services.
---

# Skill: HUL ERP Periodic Operations & Reconciliation Runbook

> Usage Type: **Operational Execution, Reconciliation Cycles & Maintenance**  
> Shared Domain Brain: [docs/APPS_GUIDE.md](file:///home/ubuntu/myerpv3/docs/APPS_GUIDE.md) and [docs/CLASSES_GUIDE.md](file:///home/ubuntu/myerpv3/docs/CLASSES_GUIDE.md)

---

## 1. Playbook 1: Monthly GST Reconciliation & Statutory Filing

**Schedule**: Run at month-end after billing is closed for the month.

1. **Trigger Accounting Ingestion**:
   - Call `POST /monthly_gst_import/` with payload `{"month": M, "year": YYYY, "company": "devaki_urban"}`.
   - This executes [`GstFilingImport.run()`](file:///home/ubuntu/myerpv3/erp/erp_import.py), pulling fresh reports from IKEA and setting `Sales.gst_period = "MMYYYY"`.
2. **Download GST Portal Records**:
   - Verify GST session: `POST /custom/captcha` $\rightarrow$ solve $\rightarrow$ `POST /custom/login`.
   - Update portal records: [`GSTR1Portal.update_db(gst_client, organization, period)`](file:///home/ubuntu/myerpv3/report/models.py#L803).
3. **Execute Reconciliation**:
   - Call `POST /gst/generate` with payload `{"period": "MMYYYY"}`.
   - Runs [`gst.gst.generate`](file:///home/ubuntu/myerpv3/gst/gst.py), performing diff matching, zero-rate corrections, and generating:
     * Working Excel: `static/<org>/workings_<period>.xlsx`
     * Statutory JSON: `static/<org>/<period>.json`
4. **Audit Review & Submission**:
   - Download workings via `POST /gst/summary`.
   - Inspect `MISMATCH` and `MISSING` sheets.
   - Download statutory JSON via `POST /gst/json` for filing on GSTN.

---

## 2. Playbook 2: Daily Bank Statement Reconciliation

**Schedule**: Run daily after receiving bank statement files.

1. **Statement Ingestion**:
   - Call `POST /bank/bank_statement_upload/` with statement file (SBI/KVB).
   - Verifies date continuity against previous uploads.
2. **Automated Matching**:
   - Call `POST /bank/smart_match/` on unclassified statements.
   - Matches cheques against [`ChequeDeposit`](file:///home/ubuntu/myerpv3/bank/models.py#L11) records and runs ML character n-gram matching on NEFT narrations.
3. **Collection Push to IKEA**:
   - Review matched statements in dashboard.
   - Call `POST /bank/push_collection/` to assign 6-digit statement IDs, create receipts in IKEA, and settle cheques.
   - Download audit workbook `push_cheque_ikea.xlsx`.

---

## 3. Playbook 3: Inbound Truckload Intake Verification

**Schedule**: Run when an HUL supplier shipment arrives at the warehouse.

1. **Invoice Intake**:
   - Call `POST /load/upload_purchase_invoice/` with the HUL invoice PDF.
   - Coordinates are parsed into [`TruckLoad.purchase_products`](file:///home/ubuntu/myerpv3/load/models.py#L5).
2. **Carton Scanning**:
   - Warehouse staff scan physical boxes via mobile/web UI hitting `POST /load/box/`.
3. **Discrepancy Report**:
   - Call `GET /load/download_load_summary/?load=<id>`.
   - Review multi-tab Excel for `Mismatch (CBU)` (case shortages) and `Mismatch (Higher/Lower MRP)` before the truck departs.

---

## 4. Playbook 4: Unilever SAP Vendor Ledger Audit

**Schedule**: Run on or after the 21st of each month (MOC cycle cut-off).

1. **Import SAP Ledger**:
   - CLI: `python manage.py import_ledger <company> <file_path>`
   - Or API: `POST /ledger/import/`.
2. **Run Verification Subsystems**:
   - CLI: `python manage.py verify_ledger <company>`
   - Reconciles Claims, Shortages, Damages, and NMSM against RSUnify operational reports on an MOC basis.
   - Output comparison saved to `a.xlsx`.

---

## 5. System Maintenance & Service Restarts

When updating code, syncing environments, or recovering from crashes on the EC2 instance:

```bash
# 1. Restart Gunicorn WSGI Backend
sudo systemctl restart backend.service

# 2. Restart Background Token & Auth Worker
sudo systemctl restart redis_worker.service

# 3. Restart Scheduled Tasks
sudo systemctl restart scheduler.service

# 4. Inspect Service Logs
journalctl -u backend.service -n 50 --no-pager
journalctl -u redis_worker.service -n 50 --no-pager
```

**Sync Script**: To run full deployment pull and migration, execute `bash sync.sh`.
