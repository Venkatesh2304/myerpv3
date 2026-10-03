---
name: erp-data-ingestion
description: SOP and instructions for importing IT-related database tables (Sales, Collections, Adjustments, Purchases, Claims, HUL Ledger) and verifying database import completeness.
---

# ERP Data Ingestion Operational Guide (SOP)

This skill provides the conceptual framework, operational procedures, and command references for ingesting transaction records and statement data into the ERP database.

---

## 1. Context & Business Logic

The ERP database serves as the foundation for the entire synchronization and auditing process. Ingestion populates raw ledger entries, customer accounts, and stock tables. 

Data is ingested from two primary source domains:
1.  **Ikea Portal (Structured Reports)**: Contains operational records. Transactions are downloaded and parsed automatically by the pipeline. Some categories are imported monthly (due to size/memory limits) while others are imported yearly.
2.  **HUL Ledger Statement (Excel)**: An external statement uploaded directly by the cashier. It details actual bank receipts, portal credit notes, and adjustments that do not reside in raw Ikea invoice downloads.

---

## 2. Ingestion Categories & DB Models

The pipeline maps raw source records to the following Django database models:

*   **Sales** (`Sales` table): Ingested monthly. Contains invoice details, retail outlet keys, gross amounts, and tax breakdowns.
*   **Inventory** (`Inventory` table): Linked directly to `Sales`. Tracks item-level quantities, SKU identifiers, and values.
*   **Collections** (`Collection` table): Ingested monthly. Tracks payment receipts, cheque numbers, clearance dates, and collection amounts.
*   **Adjustments** (`Adjustment` table): Ingested yearly. Tracks credit note routing, scheme allowances, and discounts.
*   **Purchases** (`Purchase` table): Ingested yearly. Tracks stock receipts, warehouse purchases, and cost prices.
*   **Claims Report** (`claims_report` table): Ingested yearly. Tracks HUL claim approvals, service margins, and claims status.
*   **Market Returns** (`Sales` table with `type="damage"`): Ingested yearly. Tracks damaged stock returned from retailers.
*   **HUL Ledger** (`HulLedger` table): Ingested yearly from Excel. Represents cashier-logged credit notes and payments.

---

## 3. Command Line Operations

Run the commands below from the backend project folder under the active virtual environment:

### A. Run Full Year Ikea Import
To run the full import pipeline for a specific company (e.g., `devaki_hul`) and starting financial year (e.g., `2025` for FY 2025-2026):
```bash
source .venv/bin/activate
python manage.py erp_it_import --company devaki_hul --fy 2025
```

### B. Resume After a Portal Timeout
If the script halts due to an Ikea portal timeout or connection drop, simply run the same command again. It will automatically load the progress JSON, print completed statuses, and resume from the failed task:
```bash
source .venv/bin/activate
python manage.py erp_it_import --company devaki_hul --fy 2025
```

### C. Skip Downloading (Re-run Mapping Only)
If you have already downloaded the Excel reports and only need to re-run the database mapping and data import:
```bash
source .venv/bin/activate
python manage.py erp_it_import --company devaki_hul --fy 2025 --skip-download
```

### D. Run Database Validation Check (No Imports)
To simply check and verify that all months for the FY contain non-zero Sales and Collections data in the database:
```bash
source .venv/bin/activate
python manage.py erp_it_import --company devaki_hul --fy 2025 --validate-only
```

### E. Run HUL Ledger Excel Ingestion
To import the HUL ledger statement from an Excel file (e.g. `data/devaki_hul/ledger.xlsx`):
```bash
source .venv/bin/activate
python manage.py erp_ledger_import --file data/devaki_hul/ledger.xlsx --company devaki_hul
```

---

## 4. Progress Tracking Schema

The pipeline maintains state inside the hidden directory `.it_import_state/it_import_progress_{company_id}_{fy}.json` to allow clean resuming:
```json
{
  "company_id": "devaki_hul",
  "fy": 2025,
  "tasks": {
    "2025-04": {
      "sales": "completed",
      "collection": "completed"
    },
    "2025-05": {
      "sales": "completed",
      "collection": "pending"
    }
  },
  "yearly_tasks": {
    "adjustment": "pending",
    "purchase": "pending",
    "claims_report": "pending",
    "market_return": "pending"
  }
}
```
If you wish to force a complete re-run for a specific month, year, or task, change `"completed"` to `"pending"` in this state file before launching the command.
