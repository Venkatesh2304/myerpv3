---
name: tally-voucher-integration
description: Skill for exporting database simulated vouchers and importing them to Tally Prime (running at localhost:9000). Also includes bulk-deletion, query protocols, and verification rules.
---

# Tally Prime XML Integration SOP (Voucher Imports & Queries)

This skill provides operational SOPs, serialization mechanics, XML envelopes, and execution commands for posting transactions directly to Tally Prime.

---

## 1. Context & Business Logic

Tally Prime acts as the final accounting ledger. The integration converts Django database transactions into structured XML payloads and uploads them via Tally's local XML HTTP API (defaulting to `http://localhost:9000/`).

To ensure system reliability, the sync pipeline implements:
1.  **Strict Voucher Ordering**: Vouchers are sorted by remote ID to guarantee that invoices are imported before payments or credit returns.
2.  **Referenced Master Auto-Creation**: Every batch upload contains the ledger definitions (accounting accounts) and stock item definitions referenced by those transactions, preventing "Ledger not found" errors in Tally.
3.  **State Registry & Resume**: Batch states are logged in `tally_import_batch_status.csv` and category dates are tracked in `tally_import_registry.json`. If a sync halts due to connection failures, it resumes from the last completed batch.

---

## 2. Command Line Operations

### A. Run Active Voucher Import Command
Run the bulk transaction importer command under the active virtual environment:
```bash
source .venv/bin/activate
python manage.py tally_voucher_import --category sales-all --company devaki_hul --batch-size 1000 --tally-company "DEVAKI IT (25-26)"
```
*   **Allowed Categories**: `sales`, `sales-all`, `purchase`, `purchase-all`, `collection`, `adjustment`, `hul-ledger`.

### B. Run Opening Balance & Standard Cost Import Command
Run the aggregated opening stock, standard cost, and party outstanding importer command under the active virtual environment:
```bash
source .venv/bin/activate
# Import Stock opening quantities & values (from previous FY closing stock)
python manage.py tally_opening_import --org devaki --fy 25-26 --tally-company "Devaki (25-26)" --type stock

# Import Standard Cost Rates (from current FY closing stock)
python manage.py tally_opening_import --org devaki --fy 25-26 --tally-company "Devaki (25-26)" --type standard_cost

# Import Party outstanding opening balances (with bill allocations from previous FY closing outstandings)
python manage.py tally_opening_import --org devaki --fy 25-26 --tally-company "Devaki (25-26)" --type parties
```
*   **Org Parameter**: `--org` specifies the GST organization name (resolves caching/company list dynamically from the DB).
*   **Aggregation Rule**: Automatically groups closing stock levels, closing rates, or outstanding bills across all sister companies of the organization in a single run.
*   **Type Options**: `--type` supports `stock` (opening stock values), `standard_cost` (standard cost rates from end of FY), `parties` (customer outstandings), or `all` (combines stock and parties). Party ledger names are created as `"Party Name (Party Code)"` with individual bill allocations.


---

## 3. Request & Envelope XML Schema

All data sent to Tally is wrapped in a standard `ENVELOPE` request:
```xml
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Import</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Vouchers</ID>
    </HEADER>
    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVCURRENTCOMPANY>DEVAKI IT (25-26)</SVCURRENTCOMPANY>
            </STATICVARIABLES>
        </DESC>
        <DATA>
            <TALLYMESSAGE>
                <!-- Serialized Voucher Masters & Accounting Ledgers -->
            </TALLYMESSAGE>
        </DATA>
    </BODY>
</ENVELOPE>
```

---

## 4. Bulk Deleting Incorrect Vouchers

If an import sync error occurs or incorrect data is synchronized, you can bulk-delete vouchers by sending an XML import envelope with `ACTION="Delete"` referencing their `REMOTEID`:
```xml
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Import</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Vouchers</ID>
    </HEADER>
    <BODY>
        <DESC></DESC>
        <DATA>
            <TALLYMESSAGE>
                <VOUCHER REMOTEID="Sales-SAT09000" ACTION="Delete"></VOUCHER>
                <VOUCHER REMOTEID="Sales-SAT09001" ACTION="Delete"></VOUCHER>
            </TALLYMESSAGE>
        </DATA>
    </BODY>
</ENVELOPE>
```

---

## 5. Optimized Tally Queries

> [!IMPORTANT]
> **CRITICAL PERFORMANCE WARNING:**
> DO NOT fetch general or unfiltered ledger lists. Unfiltered queries force Tally to calculate running balances for all historical accounts, which will freeze Tally. Use the optimized collection-filtered query structure below.

### Optimized Tally Collection Query
```xml
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>TargetLedgersCol</ID>
    </HEADER>
    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
            </STATICVARIABLES>
            <TDL>
                <TDLMESSAGE>
                    <COLLECTION NAME="TargetLedgersCol">
                        <TYPE>Ledger</TYPE>
                        <FILTER>TargetFilter</FILTER>
                        <FETCH>NAME, PARENT, CLOSINGBALANCE</FETCH>
                    </COLLECTION>
                    <SYSTEM TYPE="Formulae" NAME="TargetFilter">
                        $Parent = "Sundry Debtors" or $Name = "HUL Ledger"
                    </SYSTEM>
                </TDLMESSAGE>
            </TDL>
        </DESC>
    </BODY>
</ENVELOPE>
```
