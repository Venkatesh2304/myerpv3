---
name: gstr2-reconciliation
description: High-level SOP for compiling simulated Tally inward (purchases & returns) taxable and tax aggregates month-wise, comparing against GSTR-2B portal values, and identifying mismatches.
---

# GSTR-2 Inward Supplies Reconciliation SOP

This skill provides standard operating procedures and documentation for performing high-level month-wise reconciliations of simulated Tally inward supplies (purchases, returns, claims) against GSTR-2B portal reports.

---

## 1. Overview & Business Logic

The GSTR-2 reconciliation matches inward purchases and debit return notes against the consolidated GSTR-2B reports filed by HUL (`GSTIN: 33AAACH1004N1Z1`). 

Similar to GSTR-1, GSTR-2 is a **multi-company aggregate** that sums purchase and return records across all three sister companies (`devaki_hul`, `lakme_urban`, `lakme_rural`) to verify that the inward tax credits mapped to Tally match the portal statements exactly.

---

## 2. Command Line Operations

Run the GSTR-2 reconciliation under the active virtual environment:
```bash
source .venv/bin/activate
python manage.py verify_gstr2_simulation --org devaki --companies all --fy 25-26
```
*   **Target Command File:** [verify_gstr2_simulation.py](file:///home/venkatesh/code/erp/backend/erp/management/commands/verify_gstr2_simulation.py)
*   **Org Parameter**: `--org` specifies the GST organization name (resolves caching directories dynamically).
*   **Aggregation Mode**: `--companies all` aggregates data across `devaki_hul`, `lakme_urban`, and `lakme_rural` (multi-company aggregate).

---

## 3. Data Retrieval Sources

1.  **Simulated Tally Data**: Compiled from simulated `purchase-all` vouchers (goods purchases and returns) and `hul-ledger` vouchers (services/software charges) generated across all companies.
2.  **GSTR-2B Portal Data**: Loaded from the local GSTR-2B JSON reports downloaded from the portal at `data/{org}/gstr2b/{period}.json`.

---

## 4. Aggregate Taxable and Tax (CGST) Logic

### Inward Supplies (Purchases & Journals)
Sum up all ledger entry amounts and inventory allocations in simulated vouchers whose oldest parent group resolves to **`Purchase Accounts`** (including `"Software Charges"` which is mapped to `"Purchase Accounts"` in `tally_exporter.py`).
```python
sim_taxable_sum = Decimal("0.00")
for name, amt in all_entries:
    ancestor = get_oldest_ancestor(name, ledger_groups)
    if "purchase" in ancestor.lower():
        sim_taxable_sum += abs(Decimal(str(amt)))
```

### CGST Match
Sum up ledger entries matching exact base inward CGST ledger names (after stripping company suffixes):
```python
clean_name = clean_ledger_name(name)
if clean_name in ("Purchase_CGST", "Purchase_Return_CGST", "Damage (Purchase)_CGST"):
    sim_cgst_sum += abs(Decimal(str(amt)))
```

---

## 5. Finding Root Causes (Discrepancy Investigation)

When a month-wise taxable or tax credit (ITC) mismatch exceeds ₹10.00, execute invoice-level audits to identify the root cause:
1.  **Match Invoice-by-Invoice**: Compare the list of invoices in `data/{org}/gstr2b/{period}.json` (where supplier GSTIN is `33AAACH1004N1Z1`) against the simulated vouchers list.
2.  **Verify Invoice Numbers**: Group both lists by invoice number (e.g. HUL invoice number `9533000329`) and look for entries present in the simulation but missing in GSTR-2B, or vice versa.
3.  **Date Cut-off/Timing Discrepancies**: Identify invoices that are recorded in Tally in one month but filed on the portal by HUL in a different month (very common for invoices generated in late March/April).
