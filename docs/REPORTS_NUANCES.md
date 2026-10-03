# Report Nuances & Learned Distributor Behaviors — HUL Distributor ERP (`myerpv3`)

> This document captures operational nuances, client preferences, and hard-learned distributor behaviors gathered across production assistant interactions for `devaki_hul` and HUL distributor workflows.

---

## 1. Sales & Value Presentation Nuances

### 1. Bill Value ONLY (No Secondary Metrics by Default)
- **Distributor Preference**: When reporting sales numbers, report **ONLY the Bill Value** (Invoice Value in ₹) and **Total Bill Value**.
- ❌ **Do NOT include secondary metrics** unless explicitly requested:
  - Do NOT include **Taxable Value**
  - Do NOT include **Tax / GST**
  - Do NOT include **Scheme Discounts**
  - Do NOT include **Cash Discounts**
  - Do NOT include **Net Sales** (distributors look at actual invoice bill value)
- ❌ **No Bill Counts**: Never include invoice/bill counts ("No. of Bills: 62") in chat responses.
- ❌ **No Bill-Wise Summary Tables**: Never output long itemized lists of every individual bill in chat. Output aggregate totals grouped by line combination and beat.

---

## 2. Beat & Line Combination Nuances

### 1. Mandatory Wholesale Line Combinations
In this distribution territory, wholesale lines must always be combined and presented in this exact grouping:
- **D1 + D2**: Sum of `D1-WHOLESALE` and `D2-WHOLESALE`
- **F + H**: Sum of `F-WHOLESALE` and `H-WHOLESALE`
- **P**: `P-WHOLESALE`
- **Total**: Grand sum of all lines

### 2. Standard 2-Table Presentation Format
Always present party and beat sales using this clean structure:

```markdown
### <PARTY NAME> — <CYCLE/PERIOD> Sales

- **Party**: **<PARTY NAME>** (`<CODE>`)
- **Cycle**: **<MOC OR DATE RANGE>**
- **Total Bill Value**: **₹<TOTAL>**

---

### Wholesale Line Combinations

| Line Combination | Bill Value (₹) |
| :--- | :---: |
| **D1 + D2** | ₹<D1+D2 Amount> |
| **F + H** | ₹<F+H Amount> |
| **P** | ₹<P Amount> |
| **Total** | **₹<TOTAL>** |

---

### Beat-Wise Bill Value Breakdown

| Beat | Bill Value (₹) |
| :--- | :---: |
| **D1-WHOLESALE 5** | ₹<Amount> |
| **D2-WHOLESALE 5** | ₹<Amount> |
| **F-WHOLESALE 5** | ₹<Amount> |
| **H-WHOLESALE 5** | ₹<Amount> |
| **P-WHOLESALE 5** | ₹<Amount> |
| **Total** | **₹<TOTAL>** |
```

---

## 3. HUL Business Calendar (MOC 21st-Cutoff)

- **Cutoff Cycle**: HUL operates on a monthly cutoff from the **21st of the previous month** to the **20th of the current month**:
  - **MOC 09/2026** = **21st August 2026 to 20th September 2026**
  - **MOC 08/2026** = **21st July 2026 to 20th August 2026**
  - **MOC 10/2026** = **21st September 2026 to 20th October 2026**
- **Formula**: MOC (Month M) covers from `YYYY-(M-1)-21` to `YYYY-M-20`.
- **Current MOC Determination**:
  - If today's date <= 20, the active MOC is the current calendar month.
  - If today's date >= 21, the active MOC is the next calendar month.

---

## 4. Report-Specific Nuances

### 1. CCFOT Report (Customer Channel Fulfilment On Time)
- **What it is**: Tracks retail outlet orders against billed invoices (`OrderVsBill`).
- **Columns**: `Outlet Name`, `Outlet Code`, `Beat Name`, `Pricelist Group`, `Bill Value`, `Order Value`, `Bill Quantity`, `Actual Order Quantity`, `Suggested Order Quantity`, `TUR`.
- **Nuance**: LeverEDGE generates massive spreadsheets (often 80,000+ rows, 16+ MB).
  - Use `ik.ccfot_report(moc='09/2026')` directly.
  - Read with standard `pd.read_excel()` directly. Never use custom openpyxl loops or XML parsers.
- **Pricelist Group (PLG) Breakdown ONLY (No Beat-Wise Breakdown)**:
  - When presenting CCFOT sales / fulfillment data, ALWAYS report **Pricelist Group-wise (PLG-wise)** sales totals (`Pricelist Group` column: e.g. DETS, FNB, PP, NUTS).
  - ❌ **Do NOT provide beat-wise breakdown for CCFOT**. The distributor explicitly requested PLG-wise sales totals only for CCFOT.

### 2. Standard PLG-Wise Sales & Contribution Format
When asked for PLG-wise sales, contributions, or percentages for shops/outlets, always follow this confirmed standard structure:
1. **Header Card**:
   - Party Name (`Code`), Cycle/MOC range, Total Shop Bill Value (₹), and Overall Shop Share of Territory (%)
2. **PLG Contribution & Territory Share Table**:
   | Pricelist Group | Shop Bill Value (₹) | % Share of Shop | Total Territory PLG Sales (₹) | Shop Share of Territory (%) |
   | :--- | :---: | :---: | :---: | :---: |
   | **DETS** | ₹... | % | ₹... | % |
   | **FNB** | ₹... | % | ₹... | % |
   | **NUTS** | ₹... | % | ₹... | % |
   | **PP** | ₹... | % | ₹... | % |
   | **Total** | **₹...** | **100.00%** | **₹...** | **%** |
3. **MOC-Wise % Trend Table (when multiple MOCs requested)**:
   | Pricelist Group | MOC X (%) | MOC Y (%) | MOC Z (%) | Overall Average (%) |
   | :--- | :---: | :---: | :---: | :---: |
   | **DETS** | ...% | ...% | ...% | ...% |
   | **FNB** | ...% | ...% | ...% | ...% |
   | **NUTS** | ...% | ...% | ...% | ...% |
   | **PP** | ...% | ...% | ...% | ...% |
   | **Total** | **100.00%** | **100.00%** | **100.00%** | **100.00%** |
4. **Excel Download Link**: Include downloadable workbook with summaries and line item details.

### 3. Sales Register (`ik.sales_reg`)
- **Grand Total Row**: The final row of the Excel export contains text like "Grand Total" or "Total" with a `NaN` date.
  - Always clean with: `df = df.dropna(subset=['Invoice Date'])` or `df[df['Invoice Date'].notna()]` to prevent double-counting totals or crashing date parsers.
- **Date Formats**: LeverEDGE exports dates in mixed formats (`DD/MM/YYYY` or `YYYY-MM-DD`). Always parse with `pd.to_datetime(..., errors='coerce')`.

### 4. Outlet Payout Report (`ik.outlet_payout`)
- **What it is**: Trade scheme discount payouts, performance incentive credits, and TDS u/s 194R deductions.
- **Format**: LeverEDGE adds 6 metadata header rows at the top. The actual column headers start on row 7 (index 6).
- Use `ik.outlet_payout(moc='08/2026')` which automatically strips metadata rows and formats numeric columns.

### 5. Stock & Inventory Reports
- **Stock in Days (Days of Cover)**: `Days of Cover = Current Stock / Average Daily Sales`.
- Formulas must always be written in plain text (e.g. `Stock in Days = 103 / 1.06 = 97 Days`), never in LaTeX.

---

## 5. System & Execution Nuances

### 1. IKEA Authentication Reality
- The backend server **cannot** log into IKEA on its own.
- Authentication cookies are pushed to `/ikea_login` from a local Windows desktop client.
- If `ik.is_logged_in()` is False:
  1. Notify user that figures are from cached database records.
  2. Fall back to cached DB models (`StockReport`, `Inventory`, `Bill`, `OutstandingReport`).
  3. If DB has no cached records, ask the user to log in via the desktop client.

### 2. Standard Pandas Only
- Never write throwaway `openpyxl` loops, custom XML DOM extractors, or check for non-existent third-party libraries (`calamine`, `duckdb`).
- Standard pandas handles 80,000+ rows in ~55 seconds on this server. Run in 1 step and compute results directly.

### 3. No LaTeX Math in Output
- The frontend chat widget does not support LaTeX rendering. Never use `$...$`, `\text{}`, `\div`, or `\mathbf{}`. Always use standard plain text and Unicode symbols (`₹`, `/`, `*`, `=`).

### 4. Simple Distributor English
- Non-technical users run busy distribution operations. Keep language everyday, straightforward, and direct. Avoid high-flown or academic words.

### 5. Parallelizing Multi-Period Downloads (Speed is Critical)
- When a query requests data across multiple periods or MOCs (e.g. MOC 7, MOC 8, and MOC 9 CCFOT):
  - ❌ **DO NOT fetch sequentially in a slow loop** (waiting for 3 downloads in series takes 3x the time).
  - ✅ **Parallelize network requests** using Python's `ThreadPoolExecutor` so LeverEDGE generates and downloads all MOCs concurrently.
  - Stage each DataFrame to disk, then merge and filter with Pandas locally. This slashes response time from 3 minutes to under 45 seconds.
