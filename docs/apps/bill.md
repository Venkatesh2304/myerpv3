# App: `bill` — Market Order Billing Pipeline & Credit Risk Management

> Purpose: Daily market order intake, retailer credit risk evaluation, packed quantity adjustment, invoice posting to IKEA, vehicle delivery assignment, and sales register reconciliation.

---

## 1. Business Purpose & Operational Context

In FMCG distribution:
- Orders originate from field sales reps (DSE handhelds) and retail ordering apps (HUL Shikhar).
- Before converting orders into tax invoices, distributors must manage credit risk: checking unpaid bills, overdue ageing, and uncleared cheques.
- Warehouse operators adjust packed quantities based on physical stock availability.
- Invoices are posted to Unilever's IKEA ERP, followed by automated vehicle allocation and local sales register synchronization.

The `bill` app provides the state machine, credit evaluation rules, optimistic locking, and billing orchestration.

---

## 2. Core Models & Schema (`bill/models.py`)

### 1. [`Billing`](file:///home/ubuntu/myerpv3/bill/models.py#L11) (CompanyModel)
Represents the state and audit record for a daily billing run.
- **Constraint**: `unique_together = ('company', 'date')` (one active billing ledger per company per calendar day).
- `process`: Enum (`getorder`, `postorder`, `editing`, `created`).
- `stop`: Emergency circuit breaker (`BooleanField`). When `True`, blocks all `get_order` and `post_order` attempts.
- `ongoing`: Concurrency mutex flag (`BooleanField`).
- `order_date`: Target order date being processed.
- `order_hash`: 32-char MD5 checksum of `market_order_data`. Enforces optimistic locking between order ingestion and posting.
- `market_order_data`: JSONField containing raw line-item order details from IKEA (`mol`).
- `order_values`: JSONField mapping `{order_no: bill_value}` to track order value changes across runs.
- `last_bills`: JSONField list of invoice numbers generated during the most recent post run.

### 2. [`Bill`](file:///home/ubuntu/myerpv3/bill/models.py#L53) (CompanyModel)
Represents an issued invoice and tracks physical print and delivery milestones.
- **Constraint**: `unique_together = ('company', 'bill_id')`.
- `bill_id`: Primary invoice number (`inum`).
- `bill_date`, `bill_amt`, `party_name`, `party_id`, `beat`, `ctin`.
- `irn`, `ewb_no`: Statutory GST identifiers.
- `print_time`: Timestamp of physical printing; null if unprinted.
- `print_type`: Enum (`first_copy`, `loading_sheet`, `loading_sheet_salesman`).
- `is_reloaded`: Boolean flag set when bill is reset for reprinting.
- `loading_sheet_id`: Associated `SalesmanLoadingSheet` reference.
- `vehicle`: ForeignKey to `Vehicle`.
- `loading_time`, `delivery_time`: Dispatch timestamps.
- `notes`: Append-only audit remarks list.

### 3. [`PartyCredit`](file:///home/ubuntu/myerpv3/bill/models.py#L107) (CompanyModel)
Per-retailer credit risk rules configured by distributor management.
- **Constraint**: `unique_together = ('company', 'party_id')`.
- `bills`: Maximum allowable unpaid invoices (default 1).
- `days`: Maximum allowable age of oldest unpaid bill in days (default 0).
- `value`: Maximum order value allowed (default 0).

---

## 3. The 3-Phase Billing Pipeline

```
[Phase 1: Ingest & Credit Check]
POST /bill/get_order/
  ├── Acquire DB lock on Billing (select_for_update)
  ├── billing.Sync() & billing.Collection(order_date)
  ├── Sync CollectionReport & OutstandingReport
  ├── billing.get_market_order(order_date, beat_type)
  ├── PartyCreditLogic: evaluate bills, overdue days, cheque float
  └── Save market_order_data, compute MD5 order_hash, release lock
             │
             ▼
[Phase 2: Order Line Adjustments (Optional)]
GET/POST /bill/order/
  └── Operator edits packed quantity (qp <= aq) in market_order_data
             │
             ▼
[Phase 3: Post Invoices & Dispatch]
POST /bill/post_order/
  ├── Acquire DB lock; verify client hash matches DB order_hash
  ├── billing.Prevbills() (caches existing delivery bills)
  ├── billing.post_market_order(orders, order_numbers, delete_orders)
  ├── billing.Delivery() (auto-assigns vehicle in IKEA)
  ├── Sync SalesRegisterReport
  ├── Bill.sync_with_salesregister() (bulk create Bills, prune cancelled)
  └── Update last_bills, release lock
```

---

## 4. Credit Decision Engine (`bill/credit_logic.py`)

`PartyCreditLogic` evaluates three hard risk dimensions:

1. **Bills Count Limit**:
   - `len(unpaid_bills) < limit_bills` $\rightarrow$ **Allowed**.
   - `len(unpaid_bills) == limit_bills`:
     - **Hard Rejection 1**: If $\max(\text{oldest\_collection\_age}, \text{oldest\_bill\_age}) > 21\text{ days}$ $\rightarrow$ **Blocked**.
     - **Hard Rejection 2**: If $\text{total\_outstanding} > 500$ AND $\text{order\_value} > 500$ $\rightarrow$ **Blocked**.
     - Otherwise $\rightarrow$ **Allowed**.
   - `len(unpaid_bills) > limit_bills` $\rightarrow$ **Blocked**.
2. **Ageing Days Limit**: Oldest unpaid bill age must be $\le \text{limit\_days}$.
3. **Value Limit**: Order value must be $\le \text{limit\_value}$.
4. **Additional Business Filters**:
   - **Order Size Threshold**: Orders with value $< \text{Rs } 200$ are automatically blocked.
   - **Partial Drop Filter**: If order value dropped by $> \text{Rs } 200$ from a previous run, flagged for review.
   - **Pending Cheques**: Checked against `bank.ChequeDeposit` records with uncleared bank statements.

---

## 5. Sales Register Synchronization & Deletion Guard

`Bill.sync_with_salesregister(company, fromd, tod)`:
1. Queries `SalesRegisterReport` for sales invoices in the date range.
2. Performs `Bill.objects.bulk_create([...], ignore_conflicts=True)`:
   - New invoices are added; existing invoices preserve `print_time`, `vehicle`, and `notes`.
3. **Cancelled Bill Pruning with Deletion Guard**:
   - Identifies local `Bill` records absent in `SalesRegisterReport`.
   - **Safety Rule**:
     ```python
     if qs.count() < 10:
         qs.delete()
     ```
   - If 10 or more bills are missing, deletion is aborted to prevent mass-wiping records in case of an upstream sync timeout or partial report.

---

## 6. Key Endpoints (`bill/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/bill/get_order/` | `views.get_order` | Ingests market orders, evaluates credit risk, returns MD5 hash. |
| `POST` | `/bill/post_order/` | `views.post_order` | Validates hash, posts orders to IKEA, executes delivery run, syncs bills. |
| `GET` / `POST` | `/bill/order/` | `views.manage_order` | `GET`: View order lines. `POST`: Edit packed quantities (`qp`). |
| `GET` / `POST` | `/bill/party_credit/` | `views.party_credit` | Read or update customer credit limit overrides. |
| `GET` | `/bill/get_billing_stats/` | `views.get_billing_stats` | Dashboard metrics: today bill count, unprinted count, last bill range. |
| `GET` / `POST` | `/bill/stop_billing/` | `views.stop_billing` | Circuit breaker toggle to halt billing runs immediately. |
| `GET` | `/bill/bill/` | `modelviews.BillViewSet` | Filterable invoice list (`company`, `date`, `is_printed`, `salesman`). |

---

## 7. Concurrency & Error Recovery

1. **Lock Timeout Recovery (`BILLING_LOCK_TIMEOUT = 900`)**: If a process crashes leaving `ongoing=True`, subsequent runs clear the stale lock after 15 minutes.
2. **Optimistic Locking via MD5**: Prevents posting stale orders if another user or background job updated line items.
3. **Rapid Double-Fetch Suppression**: If `get_order` was run $< 30\text{ seconds}$ ago, duplicate calls are rejected.
