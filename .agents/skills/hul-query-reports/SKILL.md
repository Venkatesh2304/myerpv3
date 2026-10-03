---
name: hul-query-reports
description: Autonomous business data retrieval, report extraction, and analytics engine for HUL Distributor ERP (myerpv3). Resolves ad-hoc user requests across 4 data domains (Live IKEA, Live GST/E-Invoice, Cached DB Models, and Internal ERP Exclusive records). Implements freshness guardrails, uses pre-tested helper classes directly, defines deterministic discovery for new IKEA report endpoints, and generates downloadable Excel exports.
---

# Skill: HUL ERP Business Data Retrieval, Reports & Analytics

> **Role**: Autonomous Data Extraction & Financial Analytics Engine  
> **Target Audience**: Distributor Owners, Billing Clerks, Accountants, Warehouse Managers  
> **Workspace Context**: Governed by [`AGENTS.md`](file:///home/ubuntu/myerpv3/AGENTS.md) for EC2 memory limits and 12-app architecture routing.  
> **Report Nuances & Preferences**: Governed by [`docs/REPORTS_NUANCES.md`](file:///home/ubuntu/myerpv3/docs/REPORTS_NUANCES.md) for wholesale line groupings, bill value only rules, and MOC cutoff dates.

---

## 1. High-Value Operational Nuances & Learning Protocol

> [!IMPORTANT]
> **READ BEFORE PROCESSING ANY REPORT**:
> Always read and follow [`docs/REPORTS_NUANCES.md`](file:///home/ubuntu/myerpv3/docs/REPORTS_NUANCES.md) before processing or presenting any business data.
> That file contains **confirmed, high-value distributor learnings** including:
> - Client presentation preferences (Bill Value ONLY, no bill counts, no taxable/schemes by default).
> - Wholesale line combinations (**D1 + D2**, **F + H**, **P**) and mandatory 2-table layout.
> - HUL MOC 21st-to-20th monthly cutoff dates.
> - Known report quirks (cleaning `Grand Total` / `NaN` dates in `sales_reg`, CCFOT order-vs-bill data, `outlet_payout` header rows).
>
> **WRITE NEW LEARNINGS PERMANENTLY**:
> Whenever a new confirmed distributor preference, report layout rule, or data parsing quirk is learned or corrected during user conversations, **immediately record / append it into [`docs/REPORTS_NUANCES.md`](file:///home/ubuntu/myerpv3/docs/REPORTS_NUANCES.md)** so it becomes permanent system knowledge for all future sessions.

---

## 2. Generic Business Data Retrieval Definition

Distributor users request business information in practical, high-level natural language:
- *"Sales for Asoka last month"*
- *"Closing stock of Lux and Dove"*
- *"List of unpaid bills for party X"*
- *"Truck load vs scanned carton difference for invoice 123"*
- *"Total cheques deposited yesterday"*
- *"MOC 9 RS QOC performance summary"*

Deriving the requested data requires identifying which of the **4 core data domains** hold the information, resolving ambiguities, and fusing data across domains when needed.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        USER BUSINESS DATA REQUEST                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   STAGE 1: HIGH-LEVEL INTENT DISAMBIGUATION            │
│   Deduce what business metrics, entities, and timeframes are needed.   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ DOMAIN 1: IKEA   │       │ DOMAIN 2: GST    │       │ DOMAIN 3: ERP    │
│ LEVEREDGE        │       │ & E-INVOICE      │       │ EXCLUSIVE DATA   │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ • Sales Register │       │ • GSTR-1 Invoices│       │ • Item Barcode   │
│ • Outstandings   │       │ • B2B / B2C data │       │   Carton Scans   │
│ • Inventory Stock│       │ • E-Invoice IRN  │       │ • CCTV Timestamps│
│ • Collections    │       │ • Portal status  │       │ • Inbound Load   │
│ • Purchases      │       │                  │       │   PDF Box Audits │
│                  │       │                  │       │ • Gate Passes    │
│ ⚡ Live Preferred│       │ ⚡ Live Preferred│       │ • Dot-Matrix     │
│ 💾 DB Cached Fall│       │ 💾 DB Cached Fall│       │   Print Queues   │
└────────┬─────────┘       └────────┬─────────┘       └────────┬─────────┘
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   DOMAIN 4: CROSS-DOMAIN FUSION                        │
│   Correlate records across domains (e.g. Invoiced vs Packed Scans,     │
│   Bank Statement Deposits vs IKEA Collections, PO vs Inbound Load).    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 4 Data Domains & Model Matrix

### Domain 1: IKEA LeverEDGE (Distributor Core Hub)
- **Live Access**: [`custom.classes.Ikea`](file:///home/ubuntu/myerpv3/custom/classes.py#L119) pre-tested methods.
- **Cached Database Models** in PostgreSQL:
  - In [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py): Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53) — Invoiced retailer bills (`bill_id`, `bill_date`, `party_name`, `party_id`, `bill_amt`, `beat`, `vehicle`, `company_id`).
  - In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py):
    - Model [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576) — Open customer balances (`inum`, `bill_date`, `bill_amt`, `balance`, `party_name`, `salesman`, `beat`).
    - Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276) — Line-item sales register with schemes, cash discount, tax, and TCS (`schdisc`, `cashdisc`, `ushop`, `tax`, `amt`).
    - Model [`CollectionReport`](file:///home/ubuntu/myerpv3/report/models.py#L508) — Collections grouped by payment mode (`amt`, `mode`: Cheque, Cash, RTGS/NEFT).
    - Model [`StockReport`](file:///home/ubuntu/myerpv3/report/models.py#L727) — Daily inventory stock balances (`item_name`, `closing_stock`).
    - Model [`BillAgeingReport`](file:///home/ubuntu/myerpv3/report/models.py#L634) — Aging buckets (`0-7`, `8-15`, `16-30`, `>30` days).
    - Model [`PartyReport`](file:///home/ubuntu/myerpv3/report/models.py#L692) — Customer master records (`code`, `name`, `address`, `gstin`).
    - Model [`BeatReport`](file:///home/ubuntu/myerpv3/report/models.py#L658) — Beat master and route mapping.

### Domain 2: Statutory GST & E-Invoice
- **Live Access**: [`custom.classes.Gst`](file:///home/ubuntu/myerpv3/custom/classes.py#L880) and [`custom.classes.Einvoice`](file:///home/ubuntu/myerpv3/custom/classes.py#L1250).
- **Cached Database Models**:
  - In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py):
    - Model [`GSTR1Portal`](file:///home/ubuntu/myerpv3/report/models.py#L803) — Live GSTN portal return filing records.
    - Model [`IkeaGSTR1Report`](file:///home/ubuntu/myerpv3/report/models.py#L336) — GSTR-1 outbound invoice records from IKEA.
    - Model [`IkeaGSTR2Report`](file:///home/ubuntu/myerpv3/report/models.py#L878) — GSTR-2 inbound purchase records from IKEA.
  - In [`erp/models.py`](file:///home/ubuntu/myerpv3/erp/models.py):
    - Model [`GstVoucher`](file:///home/ubuntu/myerpv3/erp/models.py#L20) — Internal double-entry GST liability and input tax credit vouchers.

### Domain 3: Internal ERP Exclusive Data (ONLY Available in Internal DB)
These data points do **not** exist in IKEA or Government portals; they are generated exclusively by warehouse workers and hardware inside the distributor ERP:
1. **Physical Carton Packing Scans**:
   - File: [`product_scan/models.py`](file:///home/ubuntu/myerpv3/product_scan/models.py)
   - Models: 
     - Model [`SalesScan`](file:///home/ubuntu/myerpv3/product_scan/models.py#L5) — Carton packing scan sessions per bill (`bill_no`, `bill_products` expected, `scanned_products` box list, `logs`, `is_posted`, CCTV timestamps `video_start_time`/`video_end_time`, `video_file`).
     - Model [`Barcode`](file:///home/ubuntu/myerpv3/product_scan/models.py#L190) — Internal SKU to physical product barcode mappings.
2. **Inbound HUL Truck Load Audits**:
   - File: [`load/models.py`](file:///home/ubuntu/myerpv3/load/models.py)
   - Model: Model [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5) — HUL purchase invoice PDF coordinate extraction (`purchase_products`, `purchase_inums`, `sku_map`) vs warehouse physical box scans (`scanned_products`, `completed`).
3. **Delivery Vehicle Loading & Dispatch**:
   - File: [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py)
   - Models:
     - Model [`Vehicle`](file:///home/ubuntu/myerpv3/bill/models.py#L45) — Delivery vehicle master.
     - Model [`SalesmanLoadingSheet`](file:///home/ubuntu/myerpv3/bill/models.py#L33) — Delivery loading sheets per salesman and route.
     - Model [`PartyCredit`](file:///home/ubuntu/myerpv3/bill/models.py#L107) — Real-time party credit risk and invoice blocking decisions.
4. **Bank Statement Parsing & Narration Mapping**:
   - File: [`bank/models.py`](file:///home/ubuntu/myerpv3/bank/models.py)
   - Models:
     - Model [`BankStatement`](file:///home/ubuntu/myerpv3/bank/models.py#L59) — Parsed SBI/KVB statement transactions (`date`, `idx`, `ref`, `desc`, `debit`, `credit`, `balance`).
     - Model [`ChequeDeposit`](file:///home/ubuntu/myerpv3/bank/models.py#L11) — Physical cheque collection entries (`cheque_no`, `amt`, `party`, `deposit_date`).
     - Model [`BankCollection`](file:///home/ubuntu/myerpv3/bank/models.py#L32) — Mapped bank statement collections tied to specific bills.
     - Model [`Bank`](file:///home/ubuntu/myerpv3/bank/models.py#L53) — Bank account configurations (SBI, KVB).
5. **Unilever SAP Vendor Ledger**:
   - File: [`ledger/models.py`](file:///home/ubuntu/myerpv3/ledger/models.py)
   - Model: Model [`Ledger`](file:///home/ubuntu/myerpv3/ledger/models.py#L4) — Unilever corporate SAP vendor statements (`doc_no`, `type`, `ref`, `moc`, `amt`, `notes`).
6. **Normalized Double-Entry Accounting**:
   - File: [`erp/models.py`](file:///home/ubuntu/myerpv3/erp/models.py)
   - Models:
     - Model [`Sales`](file:///home/ubuntu/myerpv3/erp/models.py#L98) — Normalized sales invoices.
     - Model [`Purchase`](file:///home/ubuntu/myerpv3/erp/models.py#L139) — Normalized purchase invoices.
     - Model [`Party`](file:///home/ubuntu/myerpv3/erp/models.py#L29) — Normalized master party ledger accounts.
     - Model [`Stock`](file:///home/ubuntu/myerpv3/erp/models.py#L46) — Item inventory balance snapshots.
     - Model [`PartyVoucher`](file:///home/ubuntu/myerpv3/erp/models.py#L8) — Accounting ledger vouchers.
     - Model [`SalesChanges`](file:///home/ubuntu/myerpv3/erp/models.py#L161) — Audit trail replay for manual sales modifications.

### Domain 4: Cross-Domain Fusion
When a business question requires correlating records across sources:
- **Bill vs Physical Packing Audit**: Correlate live IKEA invoice (`Ikea.retrievebill`) with physical warehouse scans in [`product_scan/models.py`](file:///home/ubuntu/myerpv3/product_scan/models.py) (Model [`SalesScan`](file:///home/ubuntu/myerpv3/product_scan/models.py#L5)).
- **Bank Reconciliation**: Match bank statement credits in [`bank/models.py`](file:///home/ubuntu/myerpv3/bank/models.py) (Model [`BankStatement`](file:///home/ubuntu/myerpv3/bank/models.py#L59)) against live IKEA collections (`Ikea.collection`).
- **Inbound Load vs Inventory**: Compare HUL invoice cases in [`load/models.py`](file:///home/ubuntu/myerpv3/load/models.py) (Model [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5)) against current stock in IKEA (`Ikea.current_stock`).

---

## 3. Data Freshness Strategy: Live vs. Cached Guardrails

### Rule 1: Live Data is Preferred by Default
For short date ranges (e.g. today, yesterday, last 7 days) or specific invoice/party checks, **always prefer live portal queries** via `custom.classes.Ikea` or `custom.classes.Gst`:
- Live data captures real-time invoice cancellations, updated party balances, and immediate syncs without database replication lag.

### Rule 2: Cached DB Fallback for Heavy / Rate-Limited Queries
> [!CAUTION]
> **CRITICAL GUARDRAIL: LIVE COLLECTION REPORTS > 10 DAYS ARE FORBIDDEN**  
> Live scraping collection reports from IKEA takes several minutes, triggers rate limits, and frequently drops session cookies.
> - For collection queries spanning **> 10 days**, ALWAYS query the **cached database models**:
>   - In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`CollectionReport`](file:///home/ubuntu/myerpv3/report/models.py#L508), Model [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576)
>   - In [`bank/models.py`](file:///home/ubuntu/myerpv3/bank/models.py): Model [`BankStatement`](file:///home/ubuntu/myerpv3/bank/models.py#L59), Model [`ChequeDeposit`](file:///home/ubuntu/myerpv3/bank/models.py#L11)
>   - In [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py): Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53)

### Rule 3: IKEA Session Expired / Offline Fallback Policy
> [!IMPORTANT]
> **IKEA Authentication is Strictly Client-Initiated**:
> - The backend **CANNOT** log into IKEA (LeverEDGE) directly or refresh expired cookies.
> - Authentication is strictly **client-initiated**: A local Windows desktop client logs into LeverEDGE and pushes session cookies to `/ikea_login`.
> - ❌ **NEVER** search the codebase for login scripts, try to reverse-engineer auth tokens, or search disk for temporary dumps when `ik.is_logged_in() == False` or `Exception: Ikea is Not Logged In` is raised!
> 
> **Immediate Database Fallback**:
> 1. **Switch to Cached DB Immediately (0 ms delay)**:
>    If `ik.is_logged_in()` fails for the requested company, immediately query the internal database models:
>    - **Stock / Inventory**: In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`StockReport`](file:///home/ubuntu/myerpv3/report/models.py#L727) or In [`erp/models.py`](file:///home/ubuntu/myerpv3/erp/models.py): Model [`Inventory`](file:///home/ubuntu/myerpv3/erp/models.py), Model [`Sales`](file:///home/ubuntu/myerpv3/erp/models.py#L98), Model [`Purchase`](file:///home/ubuntu/myerpv3/erp/models.py#L139).
>    - **Sales / Bills**: In [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py): Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53) or In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276).
>    - **Outstandings**: In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576).
> 2. **Notify the Client**:
>    Always prefix the response with a clear notice:
>    > ⚠️ *Live LeverEDGE session for **`<company>`** is currently offline. The figures below are derived from cached internal ERP database records.*
> 3. **If Database Has No Data / Insufficient Records**:
>    If the cached database contains no records (or insufficient records to provide a meaningful answer):
>    - Do NOT make up numbers or guess.
>    - Directly return a clear prompt asking the user:
>      > *"Live LeverEDGE session for **`<company>`** is offline, and no cached database records were found for this period. Please log into LeverEDGE via the local desktop client to sync fresh session cookies and retry."*

---

## 4. Use Tested Helper Classes Directly (NEVER Re-Invent cURL)

All standard IKEA and GST reports are already wrapped in battle-tested Python class methods in [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py).
- **Blind Trust Tested Helpers**: Directly invoke the helper for the requested date range or entity. Never make throwaway "test probe" calls (e.g. pulling 1 day just to inspect columns).
- **Download Once & Stage Locally**: Downloading from LeverEDGE is the main latency bottleneck (10–25s). Save the fetched DataFrame immediately (e.g. `df.to_pickle('/tmp/stage_report.pkl')`). All column checks, calculations, grouping, and Excel formatting can then iterate on local data in milliseconds without re-hitting the network.
- **STRICT RULE**: Do NOT parse raw cURL files or write custom HTTP request scripts when a method is already provided!

### Primary Tested Helper Methods:
```python
import os, django; os.environ['DJANGO_SETTINGS_MODULE'] = 'myerpv2.settings'; django.setup()
from custom.classes import Ikea, Gst, Einvoice
import datetime

ik = Ikea('devaki_hul')

# 1. Sales Register (Bill-wise invoices, schemes, taxes)
df_sales = ik.sales_reg(datetime.date(2026, 8, 21), datetime.date(2026, 9, 20))

# 2. Party Outstandings (Live customer balances)
df_outs = ik.outstanding(datetime.date.today())

# 3. Short Collections (<= 10 days only!)
df_coll = ik.collection(datetime.date(2026, 9, 10), datetime.date(2026, 9, 19))

# 4. Current Stock (Live inventory snapshot)
df_stock = ik.current_stock(datetime.date.today())

# 5. Stock Ledger (Opening, Inward, Outward, Closing)
df_ledger = ik.stock_ledger(datetime.date(2026, 9, 1), datetime.date(2026, 9, 19))

# 6. Product-wise Purchases & Sales
df_pur = ik.product_wise_purchase(datetime.date(2026, 9, 1), datetime.date(2026, 9, 19))
df_sal = ik.product_wise_sales(datetime.date(2026, 9, 1), datetime.date(2026, 9, 19))

# 7. Credit / Debit Notes
df_cr = ik.crnote(datetime.date(2026, 8, 21), datetime.date(2026, 9, 20))

# 8. Settled / Pending Cheques
df_chq = ik.download_settle_cheque(type="PENDING")

# 9. GSTR-1 Portal Data
df_gstr = ik.gstr_report(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), gstr_type=1)

# 10. Single Bill Lookup
bill_data = ik.retrievebill("INV-12345")

# 11. Outlet Payout Report (MOC Trade scheme and incentive claims)
df_payout = ik.outlet_payout('08/2026')

# 12. CCFOT Report (Order vs Bill fulfillment, party bill values, beat totals)
df_ccfot = ik.ccfot_report('09/2026')
```

---

## 5. Zero-Waste Execution: Do NOT Waste Time

To deliver responses in under 20 seconds, strictly avoid redundant steps:

1. **Blind Trust in Established Helpers & Packages (No Probes)**:
   - Helper methods in `custom/classes.py` (`ik.sales_reg`, `ik.outstanding`, `ik.current_stock`, etc.) and system libraries (`openpyxl`, `pandas`, `django`) are battle-tested and guaranteed to work.
   - ❌ **DO NOT** run throwaway package checks (`python -c "import openpyxl; print('available')"`).
   - ❌ **DO NOT** run test 1-day probes before fetching the requested date range. Directly call the method with the target parameters.

2. **No Post-Write File or URL Verifications (`ls`, `curl`)**:
   - If Python completed `pd.ExcelWriter(...)` or `df.to_excel(...)` without raising an exception, the file **is guaranteed to be on disk and correctly served** by Django/Nginx media routing.
   - ❌ **DO NOT** run `ls -lh /files/exports/...` to check file presence or size.
   - ❌ **DO NOT** run `curl -I http://...` to verify HTTP 200.
   - Simply output the download link immediately:
     `[📥 Download Excel Report (<filename>.xlsx)](http://13.235.142.203:5000/media/exports/<filename>.xlsx)`

3. **The 2-Step Execution Pattern (Separate Download from Analysis)**:
   - **Step 1 (Download & Stage)**: Downloading from LeverEDGE is the main external latency bottleneck (10–25s). First, run a quick script to fetch the report using the tested helper (e.g. `ik.sales_reg(fromd, tod)`) and immediately stage the raw DataFrame to disk:
     `df.to_pickle('/tmp/stage_report.pkl')`
   - **Step 2 (Consolidated Analysis & Export)**: In a single follow-up script, load `/tmp/stage_report.pkl`, clean the data (`.dropna()` on dates to exclude the Grand Total row), calculate all required summaries (daily, beats, schemes), write the styled Excel file to `/home/ubuntu/myerpv3/files/exports/`, and print the summary table.
    - **Why this separation is vital**: If any column handling or formatting needs an adjustment, you iterate on local disk in 0.2 seconds without re-triggering the slow LeverEDGE network download. Within Step 2, do NOT micro-chunk into separate shell commands.

4. **Never Output LaTeX Math Notation**:
   - The frontend assistant widget does NOT support LaTeX rendering. Never format formulas, calculations, or metrics using LaTeX notation (`$...$`, `$$...$$`, `\text{}`, `\mathbf{}`, `\div`, `\times`, etc.).
   - ❌ **DO NOT output**: `$\text{Stock in Days} = 103 \div 1.06 = \mathbf{97\text{ Days}}$`
   - ✅ **DO output**: `Stock in Days = 103 / 1.06 = 97 Days of Cover`
   - Use standard plain text, Markdown bold (`**...**`), and standard Unicode symbols (`/`, `*`, `=`, `₹`).

5. **Use Standard Pandas for Reading Data (No Custom Parsers or Overthinking)**:
   - Always use standard `pandas` (`pd.read_excel(...)`) directly to read downloaded Excel reports or staged data.
   - ❌ **DO NOT** write custom `openpyxl` row-by-row loops, `zipfile` XML extractors, or inspect XML tags.
   - ❌ **DO NOT** spend tool turns probing or checking for third-party parsing packages (`calamine`, `duckdb`, `polars`).
   - Simply load the DataFrame with `pd.read_excel(...)`, filter or aggregate using standard Pandas vectorized conditions (`df[df['Outlet Name'].str.contains(...)]`), and output the result in one single script.

6. **Parallelize Multi-Period / Multi-MOC Requests (Speed is Critical)**:
   - When queries request data across multiple time periods or MOCs (e.g. MOC 7, 8, and 9 CCFOT or multiple monthly reports), **never download them sequentially in a slow `for` loop**. Sequential LeverEDGE downloads multiply external latency (3 MOCs in series takes 3x the time).
   - ✅ **Fetch and stage concurrently using `ThreadPoolExecutor`**:
     ```python
     import concurrent.futures

     mocs = ['07/2026', '08/2026', '09/2026']

     def fetch_moc(moc):
         ik_local = Ikea(session=session)
         df = ik_local.ccfot_report(moc)
         df.to_pickle(f'/tmp/stage_ccfot_{moc.replace("/", "_")}.pkl')
         return moc

     with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(mocs), 4)) as executor:
         list(executor.map(fetch_moc, mocs))
     ```
   - Parallelizing network downloads drops external fetch time from 3+ minutes to under 45 seconds. Once staged on disk, perform all filtering, aggregations, and Excel generation in a single Step 2 Pandas script.

---

## 6. Semantic Intent Disambiguation

Before running queries, resolve ambiguous distributor terms to the correct report and domain:

| User Request | Potential Confusion | Resolution & Correct Target |
| :--- | :--- | :--- |
| **"Purchase details"** | Purchase Register vs Product-wise Purchase vs Load Check | • If asking for invoice totals/GR dates -> `Purchase Register`.<br>• If asking for SKU/case quantities -> `Ikea.product_wise_purchase`.<br>• If asking for physical truck box discrepancies -> In [`load/models.py`](file:///home/ubuntu/myerpv3/load/models.py): Model [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5). |
| **"Sales report"** | Sales Register vs Bill-wise Sales vs Product-wise Sales | • If asking for party bills, schemes, tax -> `Ikea.sales_reg` or In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276).<br>• If asking for SKU volume -> `Ikea.product_wise_sales`.<br>• If asking for delivery/dispatch status -> In [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py): Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53). |
| **"Outstanding / Dues"** | Outstanding vs Pending Bills vs Bill Ageing | • Overall party balance -> `Ikea.outstanding` or In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`OutstandingReport`](file:///home/ubuntu/myerpv3/report/models.py#L576).<br>• Specific unpaid invoice numbers -> `Ikea.pending_bills()`.<br>• Overdue aging buckets (0-7, 8-15, >30 days) -> `Ikea.bill_ageing()` or In [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py): Model [`BillAgeingReport`](file:///home/ubuntu/myerpv3/report/models.py#L634). |
| **"Load check differences"** | Inbound SAP Purchase vs Physical Scanning | In [`load/models.py`](file:///home/ubuntu/myerpv3/load/models.py): Model [`TruckLoad`](file:///home/ubuntu/myerpv3/load/models.py#L5) (internal ERP model comparing invoice PDF coordinates with warehouse box scans). |

---

## 7. Open-Ended Methodology to Derive NEW IKEA Reports & Screens

When a requested IKEA data point or report is **not** already wrapped in `custom/classes.py`:
**DO NOT probe random URLs or guess viewpage slugs.**
**DO NOT assume every report uses `jsonObj` or `generatereport`.**
Follow this 3-tier progressive discovery pipeline:

### Tier 1: Check the Cached Pre-Indexed Catalog (0 ms)
Check the pre-indexed catalog of 146+ verified LeverEDGE reports:
- File: [`.agents/skills/hul-query-reports/ikea_reports_catalog.json`](file:///home/ubuntu/myerpv3/.agents/skills/hul-query-reports/ikea_reports_catalog.json)
- Quick lookup in Python:
  ```python
  import json
  with open('/home/ubuntu/myerpv3/.agents/skills/hul-query-reports/ikea_reports_catalog.json') as f:
      catalog = json.load(f)
  matches = [r for r in catalog if '<keyword>' in r['title'].lower() or '<keyword>' in r['viewpage'].lower()]
  ```
- If found, it gives the exact `title`, `controller`, and `viewpage` immediately.

### Tier 2: Search the Live `authenSuccess` Menu Tree (1 ms)
If the report or transaction is not in the cached catalog, fetch the post-login application menu from `authenSuccess`:
```python
# Fetch live menu HTML (contains all 300+ application screens, transactions, and reports)
res = ik.post('/rsunify/app/user/authenSuccess', {'isDefaultPassword': False, 'g-recaptcha-response': ''})
# Grep for the user keyword directly in the menu HTML
# Matches displayScreen_reports, displayScreenUrl, or trigger_transaction
```
- Example: Searching for `"payout"` instantly reveals:
  - `displayScreen_reports('reportsController', 'reportScreen', 'Outlet Payout Report', 'report/outletPayoutReport')`
  - `displayScreen_reports('reportsController', 'reportScreen', 'Payout Report', 'report/payoutReport')`
  - `displayScreen_reports('reportsController', 'reportScreen', 'Current MOC Pending Payout Report', 'report/currentMocPendingPayoutReport')`
  - `displayScreen_reports('reportsController', 'reportScreen', 'Reversed Payouts', 'report/reversedPayout')`
  - `trigger_transaction(this)` with `data-context="pecomClosure"`, `"non_trade_payout"`, `"hul_qps_payout_closure"`

### Tier 3: Open-Ended Screen Determination & Execution
Once the target screen URL/viewpage is identified, fetch the screen HTML:
```python
screen_res = ik.get(f'/rsunify/app/{controller}/{action}?viewpage={viewpage}#!', timeout=10)
```
Inspect how the screen actually executes — adapt to its concrete pattern:

#### Pattern A: Central Report Engine (`reportsController/generatereport`)
Most standard reports call `generatereport`. Extract the parameters dynamically:
1. `jsonObjfileInfi`: Report metadata (`title`, `reportfilename`, `viewname`, `querycount`).
2. `jsonObjWhereClause`: Parameter keys (`:val1`, `:val2`, etc.) and any SQL escaping (e.g. `addedQuotes1` $\rightarrow$ `'''{moc}'''`).
3. `jsonObjforheaders`: Visual header structure.
4. Filter Dropdown Values: If the screen has `rParamArray`, inspect its viewnames (e.g. `OUTLET_PEYOUT_REPORT_MOC`) and query `/rsunify/app/reportsController/getReportScreenData?jasonParam=...` to resolve valid dropdown options (MOCs, Beats, Salesmen).
5. POST to `/rsunify/app/reportsController/generatereport` and fetch Excel buffer via `ik.fetch_durl_content(durl)`.

#### Pattern B: Dedicated Screen Controller (`displayScreenUrl`)
Screens like `creditDebitNoteAdjustmentRpt`, `userMaintenanceController`, or `eInvoiceGeneration` do not use `generatereport`. They submit directly to their own controller endpoints:
- Inspect the `<form action="...">` or `$.ajax({ url: ... })`.
- Replicate the controller's exact POST/GET parameters directly.

#### Pattern C: Transaction & Closure Operations (`trigger_transaction`)
Operational payout closures, approvals, and status syncs (e.g. `pecomClosure`, `non_trade_payout`, `hul_qps_payout_closure`):
- Map the `data-context` attribute to its corresponding AJAX handler in `common-ui.js` or `transactions.js`.

#### Pattern D: Analytical Synthesis Fallback (e.g. Corporate Scorecards / RS QOC)
If a requested report (such as **RS QOC** - Quality of Contribution / Performance Review) is an analytical corporate review that does **not** exist as a native downloadable screen in LeverEDGE:
1. Deduce the constituent metrics of the KPI review:
   - **Secondary Sales Turnover & Bills**: Aggregate Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276) in [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py) or Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53) in [`bill/models.py`](file:///home/ubuntu/myerpv3/bill/models.py) for the MOC date range (`21st` to `20th`).
   - **ECO (Effective Coverage Outlets)**: Count distinct billed `party_id`s across the cycle in Model [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53).
   - **Active Beats**: Group sales by `beat` and sort by turnover in Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276).
   - **Trade Schemes & Margin Deductions**: Sum `schdisc`, `cashdisc`, `ushop`, and `tax` from Model [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276).
   - **Collections Realization**: Aggregate Model [`CollectionReport`](file:///home/ubuntu/myerpv3/report/models.py#L508) in [`report/models.py`](file:///home/ubuntu/myerpv3/report/models.py) by payment `mode` (Cheque, Cash, RTGS).
2. Synthesize the multi-dimensional dataset into a clean multi-sheet Excel workbook.

### Step 4: Persisting Discovered Reports to `IkeaDynamicReports` (Code Design Standard)
When adding a newly derived report to the codebase for permanent reuse:
1. **Add to `IkeaDynamicReports` in [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py#L447)**:
   - Keeps dynamic payload reports separate from cURL-backed reports.
   - `Ikea` inherits from both: `class Ikea(IkeaReports, IkeaDynamicReports)`.
2. **Avoid Over-Generalization**:
   - Do NOT create bloated abstractions with hardcoded assumptions about row offsets, column names, or `Sr No`.
   - Only reuse truly generic primitives: `self.generate_report_buffer(payload)` and `self.fetch_durl_content(durl)`.
   - Each report method parses its own dataframe appropriately.
3. **Mandatory 3-Line Distributor Business Docstring**:
   - Describe what the report represents to the distributor, what metrics/columns it holds, and who uses it (not technical API noise).
   - Example:
     ```python
     @ikea_screen("Outlet Payout Report")
     def outlet_payout(self, moc: str) -> pd.DataFrame:
         """
         Outlet Payout Report:
         Tracks trade scheme discount payouts and performance incentives credited to retail counters.
         Details settled vs pending amounts, TDS u/s 194R deductions, and linked bill references.
         Used by distributor accountants to reconcile retailer claims and credit adjustments for the MOC.
         """
     ```

---

## 7. Execution Patterns & Downloadable Excel Protocol

### One-Off Command Execution
Execute all queries as one-off commands using `run_command`:
```bash
/home/ubuntu/myerpv3/.venv/bin/python -c "<python_code>"
```
- ❌ **NEVER edit ERP application code or models to answer a data query.**

### Downloadable Excel Link Protocol
For long-format datasets (more than 10 rows) or multi-dimensional summaries:
1. Ensure the export directory exists:
   ```python
   import os
   os.makedirs('/home/ubuntu/myerpv3/files/exports', exist_ok=True)
   ```
2. Save using `pandas.ExcelWriter`:
   ```python
   export_path = f"/home/ubuntu/myerpv3/files/exports/{query_slug}_{timestamp}.xlsx"
   df.to_excel(export_path, index=False)
   ```
3. Return a direct clickable markdown link in the response:
   ```markdown
   [📥 Download Excel Report (<filename>.xlsx)](http://13.235.142.203:5000/media/exports/<filename>.xlsx)
   ```

### Output Presentation
- **Simple, Everyday English**: Use plain, clear English. Never use complex or academic words (avoid "heuristics", "orthogonal", "telemetry", "discrepancies").
- **Bold Metrics Summary Card**: Total count, net amount in ₹, date range, key highlights.
- **Clean Markdown Table**: Grouped summary (top 10 parties, beats, or daily totals).
- **Download Link**: Clickable link to the full Excel report.
- **Zero Technical Jargon**: Present all information in simple distributor business language (bills, items, outstandings, payments).
