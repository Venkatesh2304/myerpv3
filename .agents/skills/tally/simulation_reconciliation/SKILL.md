---
name: simulation-reconciliation
description: SOP and scripts for executing Party Outstanding and Stock Quantity reconciliations using database simulation and Tally/Ikea data.
---

# ERP & Tally Simulation Reconciliation SOP

This skill provides the standard operating procedures, documentation, and logic for validating database transaction completeness using **in-memory Tally simulations** before syncing data to Tally Prime.

---

## 1. The Reconciliation Paradigm

Rather than verifying data after uploading it to Tally, the pipeline runs simulations using the backend `TallyExporter` class:
*   It generates mock Tally XML voucher structures in memory.
*   It computes expected ledger and inventory changes based on these simulated vouchers.
*   It compares these simulated results against physical closing statements.

If the simulation matches the physical statements, we guarantee that the transaction logs are complete and ready for import.

---

## 2. Party Outstanding Reconciliation

Checks customer ledger balances to verify that retail sales and collections match HUL's official outstanding balance reports.

*   **Django Management Command:** [verify_outstanding_simulation.py](file:///home/venkatesh/code/erp/backend/erp/management/commands/verify_outstanding_simulation.py)
*   **Logical Steps**:
    1. Loads the opening outstanding statement ($T-1$) and closing outstanding statement ($T$).
    2. Computes the actual physical balance change for each customer (Actual Change = OS Closing - OS Opening).
    3. Aggregates all simulated collections, invoices, and adjustments for the customer to find the expected change.
    4. Computes discrepancies and classifies mismatches.

### A. Command
```bash
source .venv/bin/activate
python manage.py verify_outstanding_simulation --company devaki_hul --from 2025-04-01 --to 2026-03-31
```
*(Automatically outputs the report in the conversation brain directory as `party_outstanding_verification.md`)*

### B. Mismatch Categorization Context
Discrepancies are categorized using the following rules:
1.  **Category 1 (Current Year CNs - Pending):** Credit notes raised near year-end that have not been adjusted against outstanding invoices. These represent valid customer credits that are outstanding in the books.
2.  **Category 2 (Previous Year CNs - Adjusted):** Previous year credit notes adjusted in the current year. Since Tally did not have them linked, they show as offsets in the current year.
3.  **Category 3 (Micro-Rounding):** Beat roundings and adjustments under ₹5.00.
4.  **Category 4 (Unacceptable Mismatches):** Any other discrepancy. Represents missing collection entries, wrong invoice values, or database omissions that must be audited and fixed.

---

## 3. Stock Quantity Reconciliation

Verifies that physical inventory changes match the database simulated stock transactions.

*   **Django Management Command:** [verify_stock_simulation.py](file:///home/venkatesh/code/erp/backend/erp/management/commands/verify_stock_simulation.py)
*   **Logical Steps**:
    1. Calculates starting physical quantities (from Ikea closing pickle on $T-1$) and ending physical quantities (on $T$).
    2. Computes physical difference (Ikea Delta = Qty End - Qty Start).
    3. Simulates inventory movement in Tally (Purchases/Returns are positive/inward; Sales/Returns are negative/outward).
    4. Integrates warehouse adjustments/transfers from the physical stock ledger pickle file (`stock_ledger_{start_date}_{end_date}.pkl`).
    5. Computes discrepancy (Ikea Delta - Simulated Delta).

### A. Command
```bash
source .venv/bin/activate
python manage.py verify_stock_simulation --company devaki_hul --start-date 2025-04-01 --end-date 2026-03-31
```
*(Generates markdown report `stock_tally_verification.md` and Excel report `stock_tally_verification.xlsx`)*

---

## 4. HUL Clearing (Dummy) Ledgers Verification

Clearing accounts (e.g. `HUL Purchase`, `HUL Claim Service`, `HUL Shortage`, `HUL Damage`, `HUL Dse`, `HUL Nmsm`) act as buffers between statements and local books. While they should net to zero, they carry balances at year-end due to cutoff dates.

*   **Verification Script:** `.agents/skills/simulation_reconciliation/scripts/reconcile_hul_clearing.py`
*   **Command**:
    ```bash
    python .agents/skills/simulation_reconciliation/scripts/reconcile_hul_clearing.py
    ```

### Matching Categories
*   **Deterministic Matching**: 1-to-1 matching using bill numbers/invoices (e.g., `HUL Purchase`, `HUL Damage`, `HUL Shortage`). Cutoffs represent Goods-in-Transit or claims pending approval.
*   **Non-Deterministic Matching**: Grouped matching using dates and amounts within a 45-day window for claims that portal statements group together (e.g., `HUL Dse`, `HUL Nmsm`).

---

## 5. Audit Threshold Rule

*   **Ignore < ₹5,000**: Do not spend manual or AI resources auditing unmatched entries, clearing balances, or discrepancies with an absolute value **under ₹5,000**. These represent minor round-offs or penny variances.
*   **Audit $\ge$ ₹5,000**: Direct all analysis to discrepancies **$\ge$ ₹5,000** to isolate genuine transaction cutoffs, portal delays, or claim rejections.
