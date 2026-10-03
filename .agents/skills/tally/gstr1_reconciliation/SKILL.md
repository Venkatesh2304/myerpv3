---
name: gstr1-reconciliation
description: High-level SOP for compiling simulated Tally outward taxable and tax aggregates month-wise, comparing against GSTR-1 portal values, and identifying major discrepancies.
---

# GSTR-1 Outward Supplies Reconciliation SOP

This skill provides standard operating procedures and documentation for performing high-level month-wise reconciliations of simulated Tally outward supplies against GSTR-1 portal returns.

---

## 1. Overview & Business Logic

The GSTR-1 reconciliation verifies outward tax liabilities. When syncing multiple sister companies under a single consolidated GSTIN (e.g. `lakme_urban`, `devaki_hul`, and `lakme_rural`), we aggregate their simulated sales ledger balances and compare the combined totals against GSTR-1 portal filings. This lets us immediately detect missing invoices, mismatched tax values, or billing discrepancies.

---

## 2. Command Line Operations

Run the GSTR-1 reconciliation under the active virtual environment:
```bash
source .venv/bin/activate
python manage.py verify_gstr1_simulation --org devaki --companies all --fy 25-26
```
*   **Target Command File:** [verify_gstr1_simulation.py](file:///home/venkatesh/code/erp/backend/erp/management/commands/verify_gstr1_simulation.py)
*   **Org Parameter**: `--org` specifies the GST organization name (resolves caching directories dynamically).
*   **Aggregation Mode**: `--companies all` aggregates data across `devaki_hul`, `lakme_urban`, and `lakme_rural` (multi-company aggregate).

---

## 3. Data Retrieval Sources

1.  **Simulated Tally Data**: Computed in-memory using `TallyExporter.get_vouchers` under category `sales-all`.
2.  **GSTR-1 Portal Data**:
    *   **Live Portal API**: If a GST portal session is active, the script fetches monthly summaries using the `get_period_summary` method of the `Gst` helper.
    *   **JSON Cached Fallback**: If no active session exists, it loads the cached period JSON files from `data/{org}/gstr1/{period}.json`.

---

## 4. Aggregate Taxable and Tax (CGST) Logic

### Taxable Value Match
Sum up all ledger entry amounts and inventory allocations in simulated vouchers whose oldest parent group resolves to **`Sales Accounts`**.
```python
sim_taxable_sum = Decimal("0.00")
for name, amt in all_entries:
    ancestor = get_oldest_ancestor(name, ledger_groups)
    if "sales" in ancestor.lower():
        sim_taxable_sum += abs(Decimal(str(amt)))
```

### CGST Match
Sum up ledger entries matching exact base outward CGST ledger names (after stripping company suffixes):
```python
clean_name = clean_ledger_name(name)
if clean_name in ("Sales_CGST", "SalesReturn_CGST", "Damage (Sales)_CGST", "ClaimService_CGST"):
    sim_cgst_sum += abs(Decimal(str(amt)))
```

---

## 5. Finding Root Causes (Discrepancy Investigation)

When a month-wise taxable or tax mismatch exceeds ₹10.00, execute invoice-level audits to identify the root cause:
1.  **Date Cut-off Check**: Check if invoices dated on the 30th or 31st of the month were uploaded or filed in the subsequent month's return on the portal (a very common cause of timing mismatches).
