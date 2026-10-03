# App: `misc` — Scheduled Automation, Email Reporting & Batch Exports

> Purpose: Automated operational tasks, overdue credit summary reports, monthly bill archiving, and recurring IKEA integrations.

---

## 1. Business Purpose & Role

The `misc` app contains background utility endpoints and scheduled operational tasks that keep distributors and management informed. Rather than maintaining dedicated state models, it acts as an orchestration layer using models from `report`, `bill`, and `erp`, external clients from `custom.classes`, and system-level compression utilities.

---

## 2. Key Workflows & Endpoints

### 1. Daily 28-Day Overdue Outstanding Email (`/mail_reports/`)
- **Trigger**: Called via cron/scheduler daily.
- **Workflow**:
  1. Calls [`report.views.outstanding_report`](file:///home/ubuntu/myerpv3/report/views.py) for both `retail` and `wholesale` channels for today's date.
  2. Filters bills exceeding **28 overdue days**.
  3. Aggregates data by salesman: bill count, total overdue balance, and maximum overdue days.
  4. Generates an HTML table summary in the email body and attaches a formatted Excel workbook (`28_days.xlsx` with Retail and Wholesale sheets).
  5. Sends the email to all addresses configured in [`Company.emails`](file:///home/ubuntu/myerpv3/core/models.py#L25) via Amazon SES.

### 2. Monthly Bill Archiving & Download Link (`/mail_bills/`)
- **Trigger**: Called at month-end or on-demand with `{ month, year, company, force_download }`.
- **Workflow**:
  1. Loops through each date in the specified month.
  2. Queries [`SalesRegisterReport`](file:///home/ubuntu/myerpv3/report/models.py#L276) to find the first bill (`min_bill`) and last bill (`max_bill`) for each day.
  3. Downloads the combined multi-bill PDF directly from IKEA via `Billing.get_bill_durl(min_bill, max_bill, "pdf")`.
  4. Saves PDFs into `files/bills/<company>/month_wise/<year>/<month>/`.
  5. Compresses the entire monthly folder into a single `.7z` archive using LZMA2 compression (`7z a -t7z -m0=lzma2 -mx=9`).
  6. Sends an email containing the public media download link to management.

### 3. Monthly GST Import Orchestration (`/monthly_gst_import/`)
- **Trigger**: Called after month-end before filing returns.
- **Workflow**:
  1. Checks if GST has already been imported for the period (unless `force=True`).
  2. Executes [`GstFilingImport.run(company, args_dict)`](file:///home/ubuntu/myerpv3/erp/erp_import.py) to refresh external IKEA reports and sync internal `erp.models.Sales` and `Inventory`.
  3. Sets `gst_period = "MMYYYY"` on all eligible `Sales` records matching `Company.gst_types`.
  4. Handles division-specific filters (e.g. `devaki_urban` excludes damage bills with party `P150`).
  5. Sends status notification email to distributor accountants.

### 4. IKEA Quantum Beat Export (`/beat_export/`)
- **Trigger**: Called weekly or fortnightly.
- **Workflow**:
  1. Instantiates [`Ikea(company_id)`](file:///home/ubuntu/myerpv3/custom/classes.py#L439).
  2. Calls `ikea.beat_export(fromd, tod)`.
  3. Orchestrates SFM IKEA integration sync, requests salesman list, starts the Quantum export job, polls until completion (`status == ["0", "0", "1"]`), and repopulates commercial outlet mapping.

---

## 3. Edge Cases & Gotchas

1. **Long Request Times**: `mail_bills` and `beat_export` can take several minutes to run due to downloading hundreds of bill PDFs or waiting for IKEA export queues. Keep timeouts generous or trigger via background jobs.
2. **7z Subprocess Dependency**: `mail_bills` executes `7z` via `subprocess.run()`. Ensure `p7zip-full` is installed on the host.
3. **Empty Report Protection**: In `mail_bills`, if a date has no sales in `SalesRegisterReport`, it gracefully logs and skips that date instead of crashing.
