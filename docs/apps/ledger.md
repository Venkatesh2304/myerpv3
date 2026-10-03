# App: `ledger` — Unilever SAP Vendor Ledger Reconciliation

> Purpose: Ingestion, classification, and verification of Unilever SAP vendor ledger statements against distributor operational reports.

---

## 1. Business Purpose & Operational Context

In the Unilever distribution model:
- Unilever bills the distributor for stock purchases and software charges.
- The distributor passes trade schemes, retailer discounts, damages, and shortages back to Unilever via claims and debit notes.
- Unilever credits or debits the distributor's SAP vendor account for these transactions.

Distributors regularly face balance divergences against Unilever's SAP vendor ledger due to rejected claims, timing differences, unadjusted damage notes, or rate discrepancies. The `ledger` app parses SAP vendor ledger exports and verifies them against RSUnify operational reports (Claims, Shortages, Damages, NMSM, CDT) on an MOC basis.

---

## 2. Core Model (`ledger/models.py`)

### [`Ledger`](file:///home/ubuntu/myerpv3/ledger/models.py) (CompanyModel)
- `date`: Transaction date from Unilever SAP.
- `doc_no`: Unilever SAP document number (CharField).
- `type`: Classified transaction category (`LedgerType` enum: `PURCHASE`, `CLAIMS`, `SHORTAGE`, `DAMAGE`, `DSE`, `NMSM`, `CDTSL`, `CDTSR`, `USHOP_SI`, `SOFTWARE_CHARGES`, `TDS`, `CHEQUES`, `OTHERS`).
- `ref`: Reference string (extracted invoice number, debit note number, or activity code).
- `moc`: Unilever Month of Closure cycle string (`MM/YYYY`).
- `amt`: Net amount (`Credit - Debit`). Positive = Credit to distributor; Negative = Debit (distributor purchase/charge).
- `notes`: JSONField audit trail.

---

## 3. SAP Ledger Ingestion & Document Classification (`ledger/logic.py`)

The parser inspects SAP export columns (`Document Details`, `Remarks`, `Remarks2`, `Text`):
- `AR TDS Receivable` $\rightarrow$ `TDS`
- `Credit invoice` $\rightarrow$ `NMSM` (if remarks present) or `DSE`
- `G/L account document` $\rightarrow$ `CDTSR` (if activity == "CDTSR") or `USHOP_SI`
- `GT Rtn Bill No Tax` $\rightarrow$ `DAMAGE`
- `HUL New Manual Bill`, `Invoice` $\rightarrow$ `PURCHASE`
- `HUL Services Debit` $\rightarrow$ `SOFTWARE_CHARGES`
- `Post-tax claim` $\rightarrow$ `CDTSL` (if remarks == "CDTSL"), `SHORTAGE` (if remarks starts with `SHT_HUL`), else `CLAIMS`
- `Rcpt doc - Cheques` $\rightarrow$ `CHEQUES`

**Ingestion Rule**: Only rows with `Adj. Amt. (Rs.) == 0` (unadjusted) are ingested. Existing `Ledger` rows between `min_date` and `max_date` in the file are deleted before bulk insertion.

---

## 4. The Verification Engine (`ledger/verification.py`)

### The MOC (Month of Closure) Cycle
Unilever does not operate on standard calendar months. Financial cycles run from the **21st of the previous month to the 20th of the current month**:
- If date day $\ge 21$ $\rightarrow$ belongs to $(M+1)$'s MOC cycle.
- If date day $< 21$ $\rightarrow$ belongs to $M$'s MOC cycle.

### Verification Subsystems
Merges RSUnify operational reports against Unilever SAP `Ledger` entries:
1. **`ClaimsVerification`**: Compares `SalesRegisterReport` discount columns (`schdisc`, `btpr`, `outpyt`, `ushop`, `pecom`, `shikhar_scheme`) against SAP ledger `CLAIMS` and `USHOP_SI`. (*Note: `USHOP_SI` is normalized by dividing by 1.16 for GST*).
2. **`ShortageVerification`**: Compares warehouse `damage_proposals` starting with `SHT` against SAP `SHORTAGE` entries.
3. **`DamageVerification`**: Compares registered `damage_debit_notes` against SAP `DAMAGE` entries.
4. **`NMSMVerification`**: Compares non-proposal merchandising debit notes against SAP `DSE` entries starting with `DN`.
5. **`CDTStats`**: Aggregates Cash Discount Trade entries (`CDTSL` and `CDTSR`).

---

## 5. Endpoints & CLI Commands

- `POST /ledger/import/`: Multipart file upload (`company` + `file`).
- CLI: `python manage.py import_ledger <company> <file_path>`
- CLI: `python manage.py verify_ledger <company>`: Runs all 5 verifiers from the start of the fiscal year and writes results to `a.xlsx`.

---

## 6. Edge Cases & Gotchas

1. **The 21st Boundary**: Calendar month groupings will fail reconciliation. Always use `MOC.get_moc_for_date()`.
2. **Date Range Wipe**: Uploading a ledger file deletes all existing data between the file's minimum and maximum dates. Avoid uploading files with missing internal date ranges.
3. **UShop 1.16 GST Divisor**: SAP entries for UShop schemes include 16% GST; verification code divides by 1.16 before comparing with net invoice discounts.
