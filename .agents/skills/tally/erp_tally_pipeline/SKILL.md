---
name: erp-tally-pipeline
description: Master coordination guide for the end-to-end ERP data flow and Tally Prime synchronization. Explains the intake process, simulation reconciliation, voucher loading, and aggregate opening imports.
---

# Master ERP-to-Tally Integration Pipeline

This guide outlines the conceptual steps, logical progression, and coordination sequence for importing business data into the ERP database and synchronizing it with Tally Prime.

---

## Step 1: ERP Data Ingestion (Portal to DB)

### Context & Logic
Before any reconciliation or export can occur, the local Django database must be populated with transaction records. We ingest data from two distinct external sources:
1.  **Ikea Portal Reports**: The primary transactional repository containing retail sales invoices, customer collection entries, adjustments, purchase bills, and claims data.
2.  **HUL Ledger Statement (Excel)**: An off-portal cashier bank/credit statement detailing credit notes and actual payment receipts.

These source files are processed, structured, and saved into Django DB tables (such as `Sales`, `Collection`, `Adjustment`, `Purchase`, and `HulLedger`). The database models serve as the absolute source of truth for all downstream simulations and integrations.

*To retrieve the exact ingestion commands, progress configurations, and validation parameters, refer directly to:*
*   [erp-data-ingestion Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/erp_data_ingestion/SKILL.md)

---

## Step 2: Simulation Verification & Reconciliation

### Context & Logic
Pushing unverified transaction logs directly to Tally Prime frequently leads to accounting discrepancies due to missing entries, timing cutoffs, or off-the-record adjustments. To prevent this, we run **virtual simulations** in-memory before Tally import:
1.  **Stock Movement Simulation**: Translates Django model transactions into virtual Tally stock journal deltas and compares them with physical stock movements derived from Ikea closing stock levels. This verifies that zero inventory records have been omitted.
2.  **Outstanding Balance Simulation**: Translates collections, adjustments, and invoices into virtual customer accounts. It compares the simulated balances against physical outstanding statements to ensure customer ledgers align.
3.  **HUL Clearing (Dummy) Ledger Verification**: Compares transactions in dummy buffer accounts (e.g. `HUL Purchase`, `HUL Claim Service`, `HUL Shortage`, `HUL Damage`, `HUL Dse`, `HUL Nmsm`) against the HUL portal statements to matching clearing adjustments at 1-to-1 or grouped time-window levels.
4.  **GSTR (GST Returns) Reconciliation**: Reconciles outward sales liabilities (GSTR-1) and inward purchases/debit returns (GSTR-2B) against GST portal filings. Unlike stock or outstanding audits (which are single-company sequential operations), GSTR audits operate as **multi-company aggregates** since the sister companies share a consolidated GSTIN.

Specialized cashier corrections (such as duplicate receipt adjustments and collection discount cancellations) are resolved in these simulations to guarantee that Tally matches the cashier's verified reality.

*To retrieve the simulation execution commands, mismatch categorizations, and discrepancy audit thresholds, refer directly to:*
*   [simulation-reconciliation Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/simulation_reconciliation/SKILL.md)
*   [gstr1-reconciliation Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/gstr1_reconciliation/SKILL.md)
*   [gstr2-reconciliation Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/gstr2_reconciliation/SKILL.md)

---

## Step 3: Tally Prime Transaction Synchronization

### Context & Logic
Once the simulation validation passes, transactions are ready to be integrated into Tally Prime. The exporter reads the validated database records, translates them into Tally's proprietary XML schema, and transmits them in batches to the Tally Prime HTTP interface. A local import registry tracks successfully uploaded batches to support resuming in case of network drops.

*To retrieve the synchronization commands, XML shapes, and registry management parameters, refer directly to:*
*   [tally-voucher-integration Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/tally_voucher_integration/SKILL.md)

---

## Step 4: Tally Prime Opening Balances (Stock & Parties)

### Context & Logic
Importing opening balances is fundamentally different from importing vouchers:
*   **No DB Transaction Dependency**: It loads opening positions directly from raw physical closing files as of March 31st (closing stock pickles and Leveredge outstanding reports), bypassing database transaction history entirely.
*   **Multi-Company Aggregate**: The opening balance importer (`tally_opening_import`) aggregates balances across all sister companies under the organization (e.g. `devaki_hul`, `lakme_urban`, `lakme_rural`) to establish unified opening balances inside the target Tally company.
*   **Supported Elements**: Supports importing both stock items (quantities and rates) and customer ledger outstandings (Sundry Debtors with bill allocations) formatted as `"Party Name (Party Code)"`.

*To retrieve the opening import commands and financial year parameters, refer directly to:*
*   [tally-voucher-integration Skill](file:///home/venkatesh/code/erp/backend/.agents/skills/tally_voucher_integration/SKILL.md)

---

## Step 5: Multi-Company vs. Single-Company Coordination Rules

> [!IMPORTANT]
> **Operational Execution Rules:**
> 1. **Single-Company Pipeline Scope**: The database import commands, stock/outstanding simulation checks, and voucher imports operate strictly on a single company at a time. To run the pipeline for multiple companies, loop through and execute the commands for each company individually by following the corresponding sub-skills.
> 2. **Multi-Company Group Aggregate Scope**: The opening stock import (`tally_opening_import`) and GSTR matching checks (`verify_gstr1_simulation`, `verify_gstr2_simulation`) are multi-company aggregates. They combine/reconcile data across the three sister companies (`devaki_hul`, `lakme_urban`, `lakme_rural`) in a single run.
