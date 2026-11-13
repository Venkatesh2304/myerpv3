# Payslip / Salary Voucher Generator — Architecture & Rules

## Overview
The Payslip / Salary Voucher Generator provides an end-to-end workflow inside the **Reports** module to generate, review, persist, and export weekly wage/salary vouchers for employees across any date range.

### Core Design Principles
1. **Weekly Salary Voucher (2 per A4 Sheet)**: Generates 2 weekly vouchers per page, formatted cleanly with blank spacing between them.
2. **Title**: `Salary Voucher`.
3. **Company Header**:
   - `DEVAKI ENTERPRISES,`
   - `F/4 INDUSTRIAL ESTATE, ARIYAMANGALAM, TRICHY - 620010`
   - `GSTIN : 33AAPFD1365C1ZR`
4. **Calendar Rules (Sunday Exclusion & Month Boundaries)**:
   - **Sundays Strictly Excluded**: Date ranges span working days only (Monday to Saturday, or Month-Start to Saturday). Sundays are never part of any date range.
   - **Month-End Closing**: The final period of the month closes on the last day of the month, and the next month starts fresh from that month's first working day.
   - **Voucher Date = Last Day of Salary Period**: The `Dated :` field on the voucher is always the exact end date of that voucher's salary period (e.g. `03 Oct 26`, `10 Oct 26`, `17 Oct 26`, `24 Oct 26`, `31 Oct 26`).
5. **Dual Signatures**:
   - Bottom-left: `Employee Signature`
   - Bottom-right: `Employer Signature`
6. **No Clutter**: Stripped out `Through / Cash` block, `Account` wording, and `No. :`.
7. **Database as Source of Truth**: Data is uploaded and stored in PostgreSQL (`PayslipRecord`), and PDFs are generated directly from the database.

---

## Code Locations
* Backend generator: `report/payslip_generator.py`
* Backend endpoints: `report/views.py` (`payslip_generate_helper`, `payslip_upload_excel`, `payslip_generate_pdf`)
* Backend URLs: `report/urls.py`
* Frontend UI: `src/pages/reports/payslip.tsx` and `src/pages/reports/list.tsx`
