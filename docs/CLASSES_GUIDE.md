# Custom Scraper Classes Guide (`custom/classes.py`)

> Purpose: Comprehensive reference for `custom/classes.py`, `custom/Session.py`, and the cURL scraping engine.  
> Note: No filler code; provides the operational mechanics, auth constraints, and semantic report disambiguation.

---

## 1. Scraper Architecture: Pure Requests + cURL Templates

All external portal communication (IKEA Leveredge, GST Portal, NIC E-Invoice, Unilever SAP) uses pure Python `requests` wrapped in custom session handlers. **No browser automation (Selenium/Playwright) runs on server request threads**, protecting limited EC2 RAM.

```
+---------------------------+       +-------------------------+
| custom/curl/<key>.txt     |  -->  | custom/curl.py          |
| (Raw browser cURL export) |       | (interpret_all_curls()) |
+---------------------------+       +-------------------------+
                                                 |
                                                 v
                                    +-------------------------+
                                    | all_curls.py            |
                                    | (Python CurlRequest obj)|
                                    +-------------------------+
                                                 |
                                    +------------v------------+
                                    | get_curl(key)           |
                                    | + curl_replace(pattern) |
                                    +------------+------------+
                                                 |
                                                 v
                                    +-------------------------+
                                    | r.send(session)         |
                                    | (Session loads cookies) |
                                    +-------------------------+
```

### Key Components
1. **`custom/curl/`**: Directory containing raw cURL command exports saved directly from browser DevTools (e.g., [`custom/curl/ikea/outstanding.txt`](file:///home/ubuntu/myerpv3/custom/curl/ikea/outstanding.txt)).
2. **[`custom/curl.py`](file:///home/ubuntu/myerpv3/custom/curl.py)**:
   - `interpret_all_curls()`: Reads all `.txt` files in `custom/curl/`, parses them via `curlconverter`, and generates [`all_curls.py`](file:///home/ubuntu/myerpv3/all_curls.py).
   - `get_curl(key)`: Returns a deep copy of a `CurlRequest` from `all_curls.py` with sanitized headers.
   - `curl_replace(regex_pattern, replacement_tuple, target_string)`: Injects dynamic parameters (dates, IDs, bill numbers) into the encoded URL or JSON payload.
3. **[`custom/Session.py`](file:///home/ubuntu/myerpv3/custom/Session.py)**:
   - Extends `requests.Session`.
   - On instantiation for a user, loads credentials and cookies from [`core.models.UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27).
   - `StatusCodeError`: Formats failed requests with complete cURL commands, response code, and request body for debugging in logs.
   - Timed rotating logs saved per key and user in `logs/<key>/<user>/info.log` and `debug.log`.

---

## 2. Authentication & Login Nuances

### A. IKEA (Leveredge) — Desktop Client Push Only
- **How It Works**: The IKEA distributor portal uses enterprise Recaptcha and internal session handshakes that **cannot be initiated directly by the backend server**.
- **The Flow**:
  1. A dedicated Windows desktop client running at the distributor office logs into IKEA.
  2. The desktop client pushes valid session cookies and token to the backend API, updating [`UserSession.cookies`](file:///home/ubuntu/myerpv3/core/models.py#L27).
  3. The backend [`BaseIkea`](file:///home/ubuntu/myerpv3/custom/classes.py#L109) only verifies `is_logged_in()` via `/rsunify/app/billing/getUserId`.
- **Golden Rule**: **NEVER attempt to code automated direct logins for IKEA in backend views**. If `is_logged_in()` returns `False`, the system raises an exception or returns status `501` to prompt the user's desktop client to refresh the session.

### B. GST & E-Invoice Portals — Captcha-Based Login (Strict Ban Risk)
- **How It Works**: Both portals support headless session creation by solving an image captcha:
  1. Frontend / caller requests captcha image: `client.captcha()` (fetches image bytes and initializes session cookies).
  2. Caller submits solved captcha string: `client.login(captcha_text)`.
  3. Successful login persists new session cookies into [`UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27).
- **CRITICAL BAN WARNING**:
  - The government GST and E-Invoice portals have automated bot detection and brute-force defenses.
  - **Entering wrong credentials or failing captcha $\ge 5$ times (`SWEB_9014`) results in the user account being temporarily LOCKED or the server IP being BANNED.**
  - **Rule**: Never loop retries on failed captcha or login attempts. Surface errors immediately.

### C. Unilever SAP (InPartner) — Redis Worker Sync
- Uses [`Unilever`](file:///home/ubuntu/myerpv3/custom/classes.py#L1407).
- Cookies are obtained via background Selenium worker running in [`redis_worker.py`](file:///home/ubuntu/myerpv3/redis_worker.py) listening on Redis queue `unilever_requests`.
- Handles OData multipart batch requests with automated CSRF token negotiation via `_sap_odata_batch`.

---

## 3. IKEA Session State & The `@ikea_screen` Decorator

IKEA Leveredge enforces a strict server-side state machine on active user screens:

- Before performing actions on a screen (e.g., "Market Order Billing", "Sales Register", "Outstanding Report"), IKEA requires a notification call: `/rsunify/app/ikeaCommonUtilController/updateScreenNameIntoSession`.
- **The Trap**: If a screen was not properly closed (e.g., previous request crashed or timed out), IKEA rejects subsequent calls with `"Screen Already Exists"`.
- **The Solution**: The [`@ikea_screen(screen_name)`](file:///home/ubuntu/myerpv3/custom/classes.py#L47) decorator:
  1. Tries to register `screen_name` in session.
  2. If it encounters `"Screen Already Exists"`, it removes the conflicting screen via `/removeScreenNameFromSession` and retries.
  3. Executes the underlying report or operation.
  4. In a `finally` block, cleanly removes `screen_name` from session.
- **Rule**: Whenever adding a new report or operation on IKEA, always check whether IKEA requires the screen in session and apply `@ikea_screen("Screen Name")`.

---

## 4. Semantic Report Resolver (Do Not Blindly Grep)

IKEA has dozens of reports with overlapping or ambiguous business terms. **Agents must map user intent to the specific report function rather than grepping for keywords**:

### Outstanding & Pending Due Reports
| User Need / Requirement | Correct Method | Notes / Distinctions |
| :--- | :--- | :--- |
| "Show all customer dues / balance / overdue" | [`IkeaReports.outstanding(date)`](file:///home/ubuntu/myerpv3/custom/classes.py#L302) | Beat-wise / party-level complete outstanding ledger (unpaid bills, balances, overdue days). |
| "Which bills are currently unpaid?" | [`IkeaReports.pending_bills(date)`](file:///home/ubuntu/myerpv3/custom/classes.py#L388) | Bill-level list of unpaid documents. |
| "Show overdue ageing buckets (0-7, 8-15, >30 days)" | [`IkeaReports.bill_ageing(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L391) | Categorized ageing bucket report. |
| "Generate pending statement for delivery salesmen" | [`IkeaReports.pending_statement_excel`](file:///home/ubuntu/myerpv3/custom/classes.py#L423) or [`pending_statement_pdf`](file:///home/ubuntu/myerpv3/custom/classes.py#L501) | Filtered strictly by specific delivery beats for collection on the route. |

### Stock & Inventory Reports
| User Need / Requirement | Correct Method | Notes / Distinctions |
| :--- | :--- | :--- |
| "What is our current warehouse stock right now?" | [`IkeaReports.current_stock(date)`](file:///home/ubuntu/myerpv3/custom/classes.py#L324) | Point-in-time warehouse stock snapshot per batch/SKU. |
| "How did stock change over a period (opening/closing)?" | [`IkeaReports.stock_ledger(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L321) | Transaction ledger of inward and outward stock movements. |
| "Full batch-level stock & sales movement" | [`IkeaReports.stock_movement_report(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L433) | In-depth opening, purchase, sales, and closing quantities. |
| "Aggregated SKU purchase totals" | [`IkeaReports.product_wise_purchase(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L315) | Product-level total quantities purchased from HUL. |
| "Aggregated SKU sales totals" | [`IkeaReports.product_wise_sales(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L318) | Product-level total quantities sold to retailers. |

### Sales & Dispatch Reports
| User Need / Requirement | Correct Method | Notes / Distinctions |
| :--- | :--- | :--- |
| "Official sales invoices, tax values, discounts" | [`IkeaReports.sales_reg(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L328) | Sales Register; source of truth for internal `erp.models.Sales`. |
| "GSTR-1 formatted report from IKEA" | [`IkeaReports.gstr_report(fromd, tod)`](file:///home/ubuntu/myerpv3/custom/classes.py#L254) | Direct GSTR tax breakdown from IKEA. |
| "Dispatch packing sheet for warehouse loading" | [`IkeaReports.loading_sheet(bills)`](file:///home/ubuntu/myerpv3/custom/classes.py#L407) | Returns tuple: `(Loading Sheet DataFrame, Party Wise Sales Report DataFrame)`. |
| "Retrieve detailed line-items of a single bill" | [`Ikea.retrive_bill(bill_no)`](file:///home/ubuntu/myerpv3/custom/classes.py#L489) | Returns raw bill JSON with products, units, case counts, MRP, and status. |

---

## 5. How to Fix or Update Scrapers When Upstream Changes

When an external site changes its API format, cookies, or headers:

1. **Capture the Working Request**:
   - In browser DevTools Network tab, locate the working request.
   - Right-click $\rightarrow$ **Copy as cURL (bash)**.
2. **Update the cURL Template**:
   - Paste the cURL command into the relevant file under `custom/curl/<portal>/<report_name>.txt`.
   - Remove hardcoded session cookies (cookies are handled dynamically by `Session`).
3. **Recompile `all_curls.py`**:
   - Run in python:
     ```python
     from custom.curl import interpret_all_curls
     interpret_all_curls()
     ```
   - This re-generates [`all_curls.py`](file:///home/ubuntu/myerpv3/all_curls.py).
4. **Update Regex Substitutions**:
   - Inspect the method in [`custom/classes.py`](file:///home/ubuntu/myerpv3/custom/classes.py).
   - Ensure the regex pattern passed to `curl_replace` matches the new parameter placement in the cURL request.
5. **Verify with a Minimal Test**:
   - Test by running a targeted one-liner:
     ```bash
     python3 -c "from custom.classes import Ikea; ikea = Ikea('devaki_urban'); print(ikea.is_logged_in())"
     ```
