# Payslip Generator — Idea, Context & Architecture

## Overview & Motivation
The Payslip Generator provides an end-to-end workflow inside the **Reports** module to prepare, review, store, and export statutory monthly wage slips for employees across any arbitrary date range (`YYYY-MM` to `YYYY-MM`).

### Core Design Principles
1. **Excel as a Helper, Database as Source of Truth**: Rather than building a complex spreadsheet editor in the browser, the system generates a pre-filled **Helper Excel (`.xlsx`)** that the user can easily review and edit in Excel/LibreOffice. Once finalized, the Excel is uploaded and persisted into PostgreSQL (`PayslipRecord`). **All final PDFs are generated strictly from the database**, never directly from an uploaded Excel file.
2. **No Hardcoded Financial Years**: Supports any custom `start_period` and `end_period` (`YYYY-MM`) so it works across any year or partial period going forward.
3. **Working Days & Sunday Exclusion**: Sundays are treated as holidays and excluded from `max_working_days` (`total_days - sundays`). Daily wage rates and prorated basic pay are computed against `max_working_days`.
4. **Statutory Format (Form VI)**: Generates **one individual A4 PDF per employee per month** formatted under the **Payment of Wages Act, 1936 — Form VI (Prescribed under The Tamil Nadu Payment of Wages Rules, 1937)**, with Earnings, generic Deductions (Advances, Loss/Damage, Other Deductions — no PF), Net Amount Payable, and Employer/Employee signature blocks, bundled into a `.zip` archive.

---

## 3-Step Workflow & API Contract

### Step 1: Config & Helper Excel
* **Endpoint**: `POST /api/payslip/generate-rough/`
* **Payload**:
  ```json
  {
    "company_id": "devaki_hul",
    "start_period": "2026-01",
    "end_period": "2026-04",
    "employees": [{ "name": "Sandhya", "salary": "15000" }]
  }
  ```
* **Behavior**: Generates a sorted `.xlsx` containing `Employee Name`, `Year`, `Month`, `Total Days`, `Working Days`, `Base Salary`, `Calculated Pay`, `Bonus`, and `Net Salary`, saved under `MEDIA_ROOT/report/<company_id>/`, returning `{"status": "success", "filepath": "/media/report/..."}`.

### Step 2: Upload Final Excel to DB
* **Endpoint**: `POST /api/payslip/upload/` (`multipart/form-data` with `file` and `company_id`)
* **Behavior**: Reads the finalized `.xlsx` and performs `PayslipRecord.objects.update_or_create(...)` keyed on `(company, employee_name, year, month)`. Note that `core.Company` uses `name` as its primary key (`varchar`).

### Step 3: Generate Final Payslip PDFs
* **Endpoint**: `GET /api/payslip/generate-pdf/?company_id=...&start_year=...&start_month=...&end_year=...&end_month=...`
* **Behavior**: Queries `PayslipRecord` from PostgreSQL for the requested range, renders one PDF per employee per month using `PayslipPDF` (`fpdf`), writes a `.zip` archive to `MEDIA_ROOT/report/<company_id>/`, and returns `{"status": "success", "filepath": "/media/report/..."}`.

---

## Code Locations

### Backend (`myerpv3/backend`)
* `report/models.py`: `PayslipRecord` model (`db_table = 'payslip_records'`, unique on `(company, employee_name, year, month)`).
* `report/payslip_generator.py`: `count_sundays`, `generate_rough_excel`, `PayslipPDF`, and `generate_pdf_zip`.
* `report/views.py`: `payslip_generate_helper`, `payslip_upload_excel`, `payslip_generate_pdf`.
* `report/urls.py`: Registers `payslip/generate-rough/`, `payslip/upload/`, and `payslip/generate-pdf/` under `/api/`.

### Frontend (`myerpv3/frontend`)
* `src/pages/reports/payslip.tsx`: `PayslipGenerator` 3-tab UI component using Refine's `dataProvider().custom()` (with `query` object for GET params and `FormData` for upload) and `downloadFromFilePath()` for file downloads.
* `src/pages/reports/list.tsx`: Adds `CustomComponent` support to `ReportConfig` and registers the `Payslip Generator` tab.
