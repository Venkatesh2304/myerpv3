---
name: monthly_gst
description: Workflow SOP for monthly GST filing user automation, handling sequential IKEA data ingestion, verification, eInvoice audit/generation, workings Excel email dispatch, and GSTR-1 portal filing.
---

# Monthly GST Filing Automation Skill (`monthly_gst`)

This skill defines the end-to-end operational SOP for the AI Agent acting as an automated user proxy for monthly GST and eInvoice filing. The backend system is treated as a black-box REST service layer, while the agent executes the structured filing and reconciliation workflow.

> [!IMPORTANT]
> **Production Operations & Remote Data Authority**:
> Monthly GST and eInvoice filing operations operate **exclusively on the production server** (`http://13.235.142.203:5000`). All ingestion data, portal session cookies, and database records reside **solely on the remote production server**.
> **Do NOT inspect or query the local development database** for filing data—the local database does NOT contain production ingestion data, and inspecting local DB tables for monthly GST state is a waste of time.

---

## 1. High-Level Workflow Overview

```
+---------------------------------------------------------------------------------+
| Step 1: Sequential IKEA Data Ingestion & CLI Output Verification (CLI Server)   |
+---------------------------------------+-----------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| Step 2: eInvoice Status Audit & Generation (Standard Pre-Filed vs. Damage Filing)|
+---------------------------------------+-----------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| Step 3: Workings Excel Generation & Email Dispatch (send_workings_email.py)     |
+---------------------------------------+-----------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| Step 4: GSTR-1 Portal Filing (Explicit User Request & JSON Payload Review)       |
+---------------------------------------------------------------------------------+
```

---

## 2. Strict Operational Rules & Mandates

- **Mandatory Session Resume via Workflow File**: Every monthly GST execution MUST maintain a persistent workflow state file:
  ```bash
  .workflows/monthly_gst/<username>/<MMYYYY>/workflow.md
  ```
  **BEFORE initiating any action in a new session**, the agent MUST read the workflow state file to check the current completion status and resume directly from the last completed step (preventing redundant execution of long-running steps like ingestion).
- **Clean Workflow State & Modular Log Files**: Keep `.workflows/monthly_gst/<username>/<MMYYYY>/workflow.md` **clean, concise, and structured**.
  - **Do NOT dump raw terminal stdout/stderr logs directly into `workflow.md`**.
  - Save full command outputs into separate log files under a `logs/` subfolder:
    ```bash
    .workflows/monthly_gst/<username>/<MMYYYY>/logs/<company_name>_ingestion.log
    ```
  - In `workflow.md`, record concise status summaries, key metrics, and markdown file links referencing the saved log files (e.g. `[ingestion.log](file:///.../logs/devaki_hul_ingestion.log)`).

---

## 3. Step 1: Long-Running IKEA Data Ingestion & CLI Output Verification

Raw IKEA sales/return data ingestion is a resource-intensive operation executed on the production server:

- **IKEA Session Pre-Check & Auto-Login**: Before running ingestion for any company, verify IKEA session status (`GET /ikea_login?company=<company_name>&key=ikea`). If IKEA is not logged in (`is_logged_in: false`), invoke the Playwright authentication pipeline described in [login/SKILL.md](file:///home/venkatesh/code/erp/backend/.agents/skills/login/SKILL.md) (`node main_automate.js <company_name>`) to complete browser login and post updated cookies to production before executing ingestion.
- **Sequential Execution Only**: Process target companies **strictly one company at a time sequentially**. **NEVER run ingestion commands in parallel** across companies to prevent server memory/CPU overload.
- **Server Overload & Stalling Protocol**: If server lag, memory pressure, SSH disconnection, or script stalling occurs during ingestion, **STOP IMMEDIATELY**. Do **NOT** force retries. Identify why the server is overloaded and propose findings to the user.
- **SSH Usage & Strict Access Rules**: Refer to Section 4 of [AGENTS.md](file:///home/venkatesh/code/erp/backend/.agents/AGENTS.md) for SSH access rules. SSH access is strictly Read-Only / Debug-Only and must be triggered only for mandated CLI ingestion or troubleshooting when explicitly requested.

```bash
# 1. SSH to production server (via configured alias or explicit command):
ssh-server
# (Equivalent to: ssh -4 -i /home/venkatesh/Downloads/billingv2.pem ubuntu@13.235.142.203)

# 2. Navigate to backend project directory on server:
cd /home/ubuntu/myerpv3

# 3. Activate virtual environment:
source .venv/bin/activate

# 4. Execute ingestion sequentially per company:
python3 manage.py monthly_gst <company_name>

# Optional: Skip downloading raw files if already present on server:
python3 manage.py monthly_gst <company_name> --skip-download
```

### Ingestion Output Verification & Non-Zero Sanity Check:
Upon running the CLI ingestion command for each company:
1. **CLI Stdout Log Verification**: Inspect the terminal `stdout`/`stderr` output printed during command execution to verify successful execution and record totals.
2. **Non-Zero Sanity Check**: Verify that ingested sales record counts, tax totals, and invoice numbers are non-zero.
   > [!NOTE]
   > **`lakme_rural` Zero Record Exception**: `lakme_rural` may legitimately have `0` records imported during certain periods. This is expected behavior and fine; do NOT flag `0` records for `lakme_rural` as an error.
3. **Update Clean Workflow State**: Save raw execution stdout output into `.workflows/monthly_gst/<username>/<MMYYYY>/logs/<company_name>_ingestion.log`. Record a clean summary entry with verified counts and a link to the log file in `workflow.md`.

---

## 4. Step 2: eInvoice Status Audit & Damage Generation Protocol

### Portal Session Validation
If any API call returns **HTTP 501** (`{"key": "gst"}` or `{"key": "einvoice"}`), refer to Section 3 of the [login skill](file:///home/venkatesh/code/erp/backend/.agents/skills/login/SKILL.md) for portal session re-authentication and vision Captcha resolution.

### IRN Synchronization & Refresh Requirement
> [!IMPORTANT]
> **IRN Refresh & Mapping (`POST /einvoice/reload` / `POST /gst/generate`)**:
> Before inspecting eInvoice stats or auditing filing readiness, the agent MUST trigger IRN synchronization on the backend:
> - **Endpoints**: `POST /einvoice/reload` or `POST /gst/generate` (`{"period": "<MMYYYY>"}`)
> - **Backend Mechanics**: Calling these endpoints executes `load_irns()`, which:
>   1. Fetches filed return data directly from the GST Government Portal to update `GSTR1Portal`.
>   2. Queries recent filed eInvoices from the eInvoice Portal (`get_filed_einvs`).
>   3. Maps all retrieved IRNs (`irn_mapping`) to internal sales records (`models.Sales`) and executes `bulk_update(invs, ["irn"])` across all sister companies in the organization.

### Audit & Generation Rules:
1. **Mandatory IRN Reload**: Call `POST /einvoice/reload` (or `POST /gst/generate`) to ensure all portal IRNs are synced and mapped into `Sales.irn`.
2. **Standard Invoices Pre-Filed Audit**: Standard invoice types (`sales`, `salesreturn`, `claimservice`) are expected to be **ALREADY eInvoiced** prior to this routine.
   - Execute `POST /einvoice/stats` for period `<MMYYYY>`.
   - If any standard invoice is un-eInvoiced (`not_filed > 0`), **FLAG THEM IMMEDIATELY** to the user.
3. **Damage Type eInvoicing Scope**:
   - Damage type eInvoicing is **ONLY applicable for `sathish_gst`** (other filing accounts like `murugan_gst` do not have damage type eInvoicing).
   - For `sathish_gst`, damage type eInvoices are expected to be filed during this routine.
4. **User Confirmation & Execution**:
   - Display pending counts (`filed`, `not_filed`, taxable amount `amt`) for damage eInvoices.
   - Request explicit user confirmation before calling `POST /einvoice/file` with `{"period": "<MMYYYY>", "type": "damage"}`.
5. **Portal Lag Notice**: Newly filed eInvoices take **1 day (24 hours)** to populate inside the government GST portal. This reflection delay is expected and normal.

---

## 5. Step 3: Workings Excel Generation & Email Dispatch

After eInvoice processing is complete:

1. **Generate & Download Workings Excel**:
   - **Endpoints**: `POST /gst/generate` (`{"period": "<MMYYYY>"}`) and `POST /gst/summary` (`{"period": "<MMYYYY>"}`)
   - **Core Authority Document**: The backend compiles `workings_<period>.xlsx` containing **4 well-established, highly trustworthy sheets**. Agents should download and inspect this spreadsheet directly for audits instead of executing ad-hoc database queries:
     - **`Summary`**: Aggregated tax totals (`txval`, `cgst`, `sgst`, `igst`) grouped by `gst_type` (`b2b`, `b2c`, `cdnr`) across all operational companies.
     - **`Einvoice`**: Full eInvoice reconciliation audit tables:
       - `MISSING`: Standard B2B invoices present in DB/IKEA but missing IRN on the government portal.
       - `MISMATCH`: Discrepancies between DB tax/amounts and government eInvoice portal data.
       - `YET TO BE PUSHED (GST)`: Pending eInvoices awaiting upload.
     - **`Zero Rate`**: Registered zero-percent rated items (`is_zero_rate`), zero-rate taxable values, and IRN mappings.
     - **`Detailed`**: Full transaction line-item records (`company_id`, `inum`, `date`, `name`, `ctin`, `amt`, `txval`, `cgst`) across all transactions for the period.

2. **Dispatch Workings Email Script**:
   - **Script Path**: `.agents/skills/monthly_gst/scripts/send_workings_email.py`
   - **Sender Address**: `venkateshks2304@gmail.com`
   - **Recipient Mappings**:
     - For **`sathish_gst`** $\rightarrow$ `sathish1974@gmail.com`, `devakilever@gmail.com`
     - For **`murugan_gst`** $\rightarrow$ `angalamman1234@gmail.com`
   - **Email Subject Standard**: `GSTR1 <MURUGAN|DEVAKI> <MMM YYYY> WORKINGS`
     *(Example: `GSTR1 DEVAKI APR 2026 WORKINGS` or `GSTR1 MURUGAN APR 2026 WORKINGS`)*

```bash
# Execute email dispatch script:
python3 .agents/skills/monthly_gst/scripts/send_workings_email.py \
  --user sathish_gst \
  --period 042026 \
  --excel path/to/workings_042026.xlsx
```

---

## 6. Step 4: GSTR-1 Portal Filing (Explicit User Request & Payload Review)

GSTR-1 return filing is the final step in the monthly routine and must be handled with strict confirmation controls:

1. **Explicit User Trigger**: GSTR-1 portal submission (`POST /gst/upload`) MUST ONLY be initiated when the user **explicitly asks** to file GST.
2. **JSON Payload Preview**:
   - Before executing upload, compile the GSTR-1 return JSON payload (`POST /gst/generate`).
   - Present the full compiled GSTR-1 JSON file to the user (via artifact link or view modal) so the user can inspect and verify the return details.
3. **Final Approval & Submission**:
   - Ask the user to review the compiled JSON payload and confirm filing.
   - Upon explicit confirmation, call `POST /gst/upload` (`{"period": "<MMYYYY>"}`).
   - Verify response `{"success": true, "error": ""}` and download government verification report via `POST /gst/download`.
