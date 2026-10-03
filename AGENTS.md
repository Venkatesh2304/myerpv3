# Antigravity Agent Workspace Guide — HUL Distributor ERP (`myerpv3`)

> This file is automatically discovered by Antigravity agent sessions in `/home/ubuntu/myerpv3`.  
> It establishes system architecture, hardware limits, progressive disclosure rules, and deep-dive routing for all 12 Django apps.

---

## 1. System Operating Environment & Critical Constraints

- **Host Environment**: Production AWS Ubuntu EC2 instance (`13.235.142.203`) with **strictly limited RAM and CPU quotas**.
- **Service Endpoints**:
  - **Django Backend**: `http://13.235.142.203:5000` (Gunicorn 2 workers, 4 threads in [gunicorn.py](file:///home/ubuntu/myerpv3/gunicorn.py)).
  - **Frontend UI**: Port `8000`.
  - **PostgreSQL**: `localhost:5432` (`myerpv3_exp`).
  - **Redis**: `localhost:6379` (async worker queues).
- **Core Guardrails**:
  1. **Memory Discipline**: Avoid loading massive DataFrames or unfiltered querysets into memory without date or company scoping.
  2. **No Webdrivers on Request Threads**: External scraping uses pure `requests.Session` wrapped in [`custom.Session`](file:///home/ubuntu/myerpv3/custom/Session.py#L24). Never spin up Selenium or Chrome directly inside request handlers.
  3. **IKEA Authentication**: The backend **cannot** log into IKEA (Leveredge) directly. A local Windows desktop client pushes cookies to `/ikea_login`. Backend sessions only verify `is_logged_in()`.
  4. **GST / E-Invoice Lockout Risk**: Government portals enforce strict rate limits. Attempting bad logins or failed captchas >= 5 times will lock the account or ban the server IP.
  5. **SOURCE CODE SEARCH: ALWAYS USE `git grep` (NEVER WORKSPACE-WIDE `grep -r`)**: DO NOT RUN RECURSIVE DISK GREP (`grep -r` OR `grep -ri`) ACROSS THE REPOSITORY ROOT. THE WORKSPACE CONTAINS OVER 2.0 GB OF UNRELATED DATA (911 MB `.venv/`, 283 MB `files/` EXPORTS/PDFS, 193 MB `.git/`), WHILE SOURCE CODE IS UNDER 20 MB. BLANKET GREP HANGS SESSIONS OR TAKES 20+ SECONDS.
     - **FOR APPLICATION SOURCE CODE**: ALWAYS USE `git grep -i "<pattern>"`, WHICH COMPLETES IN UNDER 50 MILLISECONDS (400X FASTER) AND ONLY SEARCHES TRACKED APPLICATION CODE.
     - **FOR LOG FORENSICS**: USE TARGETED `grep` STRICTLY SCOPED TO THE LOG DIRECTORY (e.g. `grep -rn "<pattern>" logs/`) OR `journalctl -u backend.service`. NEVER RUN GREP AT THE REPOSITORY ROOT LEVEL (`.`).
  6. **STANDARD PYTHON EXECUTION BOILERPLATE**: When running any one-off Python script, querying Django models, or calling helpers (`custom.classes`), ALWAYS run via `/home/ubuntu/myerpv3/.venv/bin/python` using this exact preamble. NEVER run ad-hoc imports without it:
     ```python
     import os, sys
     sys.path.insert(0, '/home/ubuntu/myerpv3')
     os.environ['DJANGO_SETTINGS_MODULE'] = 'myerpv2.settings'
     import django; django.setup()

     # Safe to import classes and models now:
     from custom.classes import Ikea, Gst, Einvoice
     ```
     This prevents `ModuleNotFoundError: No module named 'custom'` and Django's `AppRegistryNotReady: Apps aren't loaded yet` errors.
  7. **NO LATEX IN CHAT RESPONSES**: The frontend assistant UI only renders standard Markdown (tables, bold, lists). It does NOT support LaTeX. Never output math or formulas with LaTeX formatting (`$...$`, `$$...$$`, `\text{}`, `\div`, `\mathbf{}`). Always write formulas and calculations in plain text / Unicode (e.g. `Stock in Days = 103 / 1.06 = 97 Days of Cover`).
  8. **SIMPLE & PLAIN ENGLISH IN CHAT**: Keep responses simple, natural, and easy to understand. The users are distributor owners, billing operators, warehouse staff, and accountants. Never use complex, academic, or high-flown words (e.g. avoid words like "heuristics", "orthogonal", "telemetry", "deterministic", "subsumed", "paradigm", "discrepancies"). Speak in normal, everyday English that anyone can follow easily.
  9. **DISTRIBUTOR CLIENT PREFERENCES (devaki_hul - sathish)**:
     - Always follow confirmed report preferences in [`docs/REPORTS_NUANCES.md`](file:///home/ubuntu/myerpv3/docs/REPORTS_NUANCES.md):
       * **Line Combinations**: Group and add **D1 + D2**, **F + H**, and **P**.
       * **Bill Value ONLY**: Report ONLY the Invoice Bill Value (in ₹). Do NOT include bill counts, bill-wise summary tables, taxable, or schemes unless asked.
       * **2-Table Output**: Header + Wholesale Line Combinations + Beat Breakdown (for sales register / party sales).
       * **CCFOT Reports**: Report Pricelist Group-wise (PLG-wise) sales totals ONLY. Do NOT include beat-wise breakdown for CCFOT.
       * **PLG-Wise Sales Format**: Standard 2-table presentation (Shop PLG Bill Value + % Share of Shop + Territory Share % + MOC-wise % trend table) with multi-sheet Excel export.

---

## 2. Progressive Disclosure & Documentation Routing

To preserve context window tokens, **do not read every file at once**. Use the directory below to read only the dedicated guide for your target app:

### System & Scraper Architecture
- **[System Overview & Constraints](file:///home/ubuntu/myerpv3/docs/SYSTEM_OVERVIEW.md)**: Hardware, multi-tenancy (`Organization` -> `Company`), background services.
- **[Report Nuances & Distributor Learnings](file:///home/ubuntu/myerpv3/docs/REPORTS_NUANCES.md)**: Operational nuances, learned distributor preferences, bill value rules, wholesale line groupings.
- **[Scraper Architecture & Classes](file:///home/ubuntu/myerpv3/docs/CLASSES_GUIDE.md)**: `custom/classes.py`, cURL pipeline, session management, and the semantic report disambiguation resolver.
- **[Apps Master Matrix](file:///home/ubuntu/myerpv3/docs/APPS_GUIDE.md)**: Master routing table connecting domain workflows to app code.

### Individual App Guides (`docs/apps/<app>.md`)
- **[Banking & Auto-Reconciliation](file:///home/ubuntu/myerpv3/docs/apps/bank.md)** (`bank`): Statement parsing (SBI/KVB), Scikit-learn TF-IDF narration matching, combinatorial invoice matching, collection push to IKEA.
- **[Inbound Purchase Load Check](file:///home/ubuntu/myerpv3/docs/apps/load.md)** (`load`): HUL purchase invoice PDF coordinate extraction via `pdfplumber`, carton box scanning, CBU/MRP discrepancy reporting.
- **[Sales Carton Packing Audit](file:///home/ubuntu/myerpv3/docs/apps/product_scan.md)** (`product_scan`): Physical item scanning against IKEA bills, barcode resolution, Hikvision CCTV video clipping.
- **[Market Order Billing](file:///home/ubuntu/myerpv3/docs/apps/bill.md)** (`bill`): Order intake, credit risk decision engine (`PartyCreditLogic`), invoice posting, delivery trigger, sales register reconciliation.
- **[Delivery Dispatch & E-Way](file:///home/ubuntu/myerpv3/docs/apps/bill_scan.md)** (`bill_scan`): Delivery vehicle loading verification, gate-pass manifest, NIC E-Way bills, Unilever Impact sync.
- **[Production Invoice Printing](file:///home/ubuntu/myerpv3/docs/apps/printing.md)** (`printing`): TVS MSP 250 Star dot-matrix & laser printing, two-pass corruption check, Aztec 2D code stamping.
- **[Statutory GST & E-Invoicing](file:///home/ubuntu/myerpv3/docs/apps/gst.md)** (`gst`): Monthly GSTR-1 return reconciliation against live portal data, statutory JSON generation, NIC IRN filing, portal captchas.
- **[Accounting & Data Ingestion](file:///home/ubuntu/myerpv3/docs/apps/erp.md)** (`erp`): Normalized double-entry schema, `erp_import.py` pipeline, `SalesChanges` audit replay.
- **[Generic Report ETL & Cache](file:///home/ubuntu/myerpv3/docs/apps/report.md)** (`report`): BaseReportModel, DateReportModel, disk pickling, SQLAlchemy bulk insertion.
- **[Unilever SAP Vendor Ledger](file:///home/ubuntu/myerpv3/docs/apps/ledger.md)** (`ledger`): SAP export ingestion, MOC 21st-cutoff cycles, discrepancy verification.
- **[Multi-Tenancy & Core Auth](file:///home/ubuntu/myerpv3/docs/apps/core.md)** (`core`): Organization/Company models, `UserSession`, desktop client bridge.
- **[Scheduled Operations & Archiving](file:///home/ubuntu/myerpv3/docs/apps/misc.md)** (`misc`): Daily 28-day overdue summary emails, monthly 7z bill archives, beat export.

---

## 3. Skills Integration
This project provides specialized Antigravity workflow skills:
- **Client Interaction & Master Dispatcher**: [`.agents/skills/hul-client-assistant/SKILL.md`](file:///home/ubuntu/myerpv3/.agents/skills/hul-client-assistant/SKILL.md) (frontline conversational handler for non-technical clients, zero-interrogation error correlation, distributor vocabulary translation, and sub-workflow routing).
- **Bug Fixing & Diagnostics**: [`.agents/skills/hul-bug-investigation-fix/SKILL.md`](file:///home/ubuntu/myerpv3/.agents/skills/hul-bug-investigation-fix/SKILL.md) (triage checklist, log forensics, auth recovery, deadlock clearing, and auto-repair).
- **Querying, Reports & Data Analytics**: [`.agents/skills/hul-query-reports/SKILL.md`](file:///home/ubuntu/myerpv3/.agents/skills/hul-query-reports/SKILL.md) (autonomous data querying, report extraction, and analytics engine across internal DB tables and live reports, with Excel export and cached collection guardrails).
- **Feature Addition & Integration**: [`.agents/skills/hul-feature-addition/SKILL.md`](file:///home/ubuntu/myerpv3/.agents/skills/hul-feature-addition/SKILL.md) (adding reports, REST APIs, composite PK models, ERP pipeline hooks).
- **Operations & Reconciliations**: [`.agents/skills/hul-reconciliation-ops/SKILL.md`](file:///home/ubuntu/myerpv3/.agents/skills/hul-reconciliation-ops/SKILL.md) (monthly GST filing, bank matching, truckload audit, ledger verification, service restarts).
