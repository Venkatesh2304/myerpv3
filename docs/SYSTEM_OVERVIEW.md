# System Overview & Architecture

> Target Audience: Autonomous coding agents and engineers working on `/home/ubuntu/myerpv3`.  
> Style: Concise, high signal-to-noise ratio, zero filler code. Focuses on system constraints, domain concepts, and external dependencies.

---

## 1. Operating Environment & Hardware Constraints

- **Host**: AWS Ubuntu EC2 instance (`13.235.142.203`).
- **Resource Constraints**: **Strictly Limited RAM & CPU**.
  - Background processes use CPU throttling (e.g. `systemd-run -p CPUQuota=20%`).
  - Gunicorn runs with only 2 workers, 4 threads (`gthread`), `preload_app=False` on `0.0.0.0:5000` (see [gunicorn.py](file:///home/ubuntu/myerpv3/gunicorn.py)).
  - **Rule for Agents**: Avoid memory-heavy operations in single requests. Do NOT load massive unindexed datasets into memory without filtering by date/company or chunking. Never spin up headless browser instances (Selenium/Playwright) on request threads.
- **Port Mapping**:
  - **Backend API**: `http://13.235.142.203:5000` (Django 5.1 + Django REST Framework + SimpleJWT).
  - **Frontend UI**: Port `8000` (Node / Web UI).
  - **Database**: PostgreSQL on `localhost:5432` (`myerpv3_exp`).
  - **Cache & Queues**: Redis on `localhost:6379` (used for asynchronous token and auth worker requests).
- **Systemd Services**:
  - `backend.service`: Gunicorn WSGI server.
  - `scheduler.service`: Periodic/cron tasks.
  - `redis_worker.service`: Background authentication token helper ([redis_worker.py](file:///home/ubuntu/myerpv3/redis_worker.py)).

---

## 2. Business Domain: Enterprise HUL Distribution

The app operates as an ERP bridge, automation, and reconciliation engine for a **Hindustan Unilever Limited (HUL) Distributor** (e.g., Devaki Enterprises operating Urban & Rural branches).

The business workflow involves:
1. **Upstream (HUL / Supplier)**: Purchasing stock from HUL, verifying incoming truck loads, matching Unilever SAP ledger.
2. **Core Operations (IKEA / Leveredge)**: HUL's proprietary distributor portal where salesman beats, retail orders (Shikhar app), invoices, collections, claims, and damage notes live.
3. **Downstream (Retailers / Delivery)**: Billing market orders, packing physical goods, scanning boxes/bills into delivery vehicles, dispatching, and reconciling bank payments.
4. **Compliance (Government Portals)**: Monthly GSTR-1 return filing, GSTR-2B matching, E-Invoice (IRN) generation, and E-Way bill creation.

---

## 3. The Three External Portals & Their Roles

| Portal | Domain Name / URL | Key Purpose in this System | Client Class |
| :--- | :--- | :--- | :--- |
| **IKEA (Leveredge)** | `leveredge18.hulcd.com` | Primary HUL distributor ERP: reports, billing, orders, collections, stock. | [`Ikea`](file:///home/ubuntu/myerpv3/custom/classes.py#L439), [`Billing`](file:///home/ubuntu/myerpv3/custom/classes.py#L577), [`IkeaReports`](file:///home/ubuntu/myerpv3/custom/classes.py#L198) |
| **GST Portal** | `services.gst.gov.in` | Filing GSTR-1, downloading returns (JSON/ZIP), invoice reconciliation. | [`Gst`](file:///home/ubuntu/myerpv3/custom/classes.py#L930) |
| **E-Invoice / E-Way** | `einvoice1.gst.gov.in` | Generating IRNs for B2B invoices, downloading signed JSON/PDFs, E-Way bills. | [`Einvoice`](file:///home/ubuntu/myerpv3/custom/classes.py#L1245) |
| **Unilever SAP (Side)** | `web3.inpartner.unilever.com` | Distributor vendor ledger verification, batch OData SAP APIs. | [`Unilever`](file:///home/ubuntu/myerpv3/custom/classes.py#L1407) |

All external communications use direct HTTP requests via `requests.Session` wrapped in [`Session`](file:///home/ubuntu/myerpv3/custom/Session.py#L24). **No webdriver/browser automation is used in primary request flows.**

---

## 4. Multi-Tenancy & Auth Architecture

Defined in [`core/models.py`](file:///home/ubuntu/myerpv3/core/models.py):

- **`Organization`**: Top-level distributor entity.
- **`Company`**: Operating division under an organization (e.g., `devaki_urban`, `devaki_rural`). Holds division-specific flags: `gst_types`, `print_types`, `einvoice_enabled`, `emails`.
- **`User`**: Custom user tied to an `Organization` with M2M relationships to allowed `Company` records. Authenticated via JWT.
- **`UserSession`** (`pk = (user, key)`):
  - Stores credentials (`username`, `password`), active session `cookies` (JSON list), and dynamic `config` (JSON dict) for each external portal (`key` $\in$ `{"ikea", "gst", "einvoice", "unilever"}`).
  - Sessions are restored directly into the client's `requests.Session.cookies` on every instantiation.

---

## 5. Architectural Golden Rules for Agents

1. **Do not attempt direct login on IKEA**: The IKEA portal requires MFA / recaptcha pushed by an external Windows desktop client running at the distributor office. The backend only validates session liveness.
2. **Strict limit on GST / E-Invoice logins**: Captcha login attempts on GST/E-Invoice portals are strictly throttled by the government. Attempting bad logins $\ge 5$ times will lock the distributor account or ban the server IP.
3. **Respect the `@ikea_screen` decorator**: IKEA sessions fail if screens are left active in their state machine. Always use `@ikea_screen` for any IKEA UI action.
4. **Disambiguate report names by domain need**: Never grep blindly for "outstanding" or "stock". Check the semantic report resolver before fetching external data.
5. **Keep database modifications transactional**: Multi-table ERP insertions (Sales, Inventory, Stock) must use `transaction.atomic()` with composite keys.
