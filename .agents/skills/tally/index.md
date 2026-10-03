# Tally Integration & Reconciliation Skills Index

This directory contains the core workflows, ingestion protocols, reconciliation scripts, and synchronization skills for managing ERP data and integrating with Tally Prime.

---

## Skill Map & Reference Index

| Skill Folder | Purpose & Description |
| :--- | :--- |
| **`erp_tally_pipeline/`** | Master end-to-end coordination guide detailing ERP database intake, simulation verification, voucher loading, and aggregate opening imports. |
| **`erp_data_ingestion/`** | SOP for ingesting raw transactional data (Sales, Collections, Adjustments, Purchases, Claims, HUL Ledger) into Django models. |
| **`simulation_reconciliation/`** | In-memory stock movement & outstanding balance simulation audits to verify zero accounting discrepancies before Tally sync. |
| **`gstr1_reconciliation/`** | Multi-company aggregate reconciliation of outward sales liabilities against GSTR-1 filings. |
| **`gstr2_reconciliation/`** | Multi-company aggregate reconciliation of inward purchase and return credits against GSTR-2B filings. |
| **`tally_voucher_integration/`** | Tally Prime HTTP XML import protocol, voucher loading, bulk deletion routines, and opening balance import (`tally_opening_import`). |

---

## Navigation & Execution Flow

```
[erp_data_ingestion] ---> [simulation_reconciliation] ---> [tally_voucher_integration]
                              |                                    ^
                              v                                    |
                    [gstr1 / gstr2 reconciliation] ----------------+
```

For complete multi-company coordination rules and step-by-step commands, refer to [erp_tally_pipeline SKILL.md](file:///home/venkatesh/code/erp/backend/.agents/skills/tally/erp_tally_pipeline/SKILL.md).
