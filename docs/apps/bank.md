# App: `bank` — Bank Statement Reconciliation, ML Narration Matching & Collection Settlement

> Purpose: Complete guide to bank statement ingestion, machine learning party classification, combinatorial invoice matching, and automated collection push back into Unilever RSUnify (IKEA).

---

## 1. Business Purpose & Operational Context

In FMCG distribution, distributors collect money daily from hundreds of retail outlets via:
- Physical Cheques collected on salesmen beats.
- Direct Bank Transfers (NEFT / IMPS / RTGS).
- UPI / QR Payments (Unilever RSUnify QR or distributor direct).
- Cash deposits at bank branches.

The distributor has two competing records:
1. **The Bank Accounts** (SBI, KVB): Raw credit transactions with messy narration strings (e.g. `NEFT-AXISP00123-SRI GANESH STORES-CHETPET-UTR...`).
2. **Unilever RSUnify ("IKEA") ERP**: The distributor's operational ERP where customer bills/invoices reside. Outstanding balances must be formally knocked off in RSUnify by recording collections and settling cheques, which releases customer credit limits.

The `bank` app bridges these systems through automated statement parsing, ML text classification, combinatorial bill matching, and direct push to RSUnify.

---

## 2. Core Models & Schema (`bank/models.py`)

### [`ChequeDeposit`](file:///home/ubuntu/myerpv3/bank/models.py#L11)
Represents a physical cheque received from a retailer prior to banking.
- `company`: `ForeignKey("core.Company")`
- `party_id`: Retailer code.
- `party`: Virtual `ForeignObject` linking `(company_id, party_id)` to [`PartyReport`](file:///home/ubuntu/myerpv3/report/models.py#L692).
- `bank`: Retailer's issuing bank name (e.g. `KVB 650`, `SBI`, `HDFC`, `ICICI`).
- `cheque_no`: Cheque number string.
- `amt`: Cheque amount (FloatField).
- `cheque_date`: Date on the cheque face.
- `deposit_date`: Date deposited into distributor bank (set when deposit slip is generated; `null` before deposit).

### [`BankStatement`](file:///home/ubuntu/myerpv3/bank/models.py#L59)
Represents a single credit line from a parsed bank statement.
- `bank`: `ForeignKey("bank.Bank")`
- `date`: Transaction date.
- `idx`: Integer sequence index within that date.
- **Constraint**: `unique_together = ('date', 'idx', 'bank')`.
- `ref`: Reference number or cheque number from the statement.
- `desc`: Narrative transaction description.
- `amt`: Transaction amount (IntegerField).
- `company`: `ForeignKey("core.Company", null=True)` — assigned when matched.
- `statement_id`: 6-digit unique integer string (`100000..999999`) pushed to RSUnify as the Cheque/DD identifier.
- `type`: Enum (`cheque`, `neft`, `upi`, `cash_deposit`, `self_transfer`, `others`).
- `cheque_entry`: `OneToOneField(ChequeDeposit, null=True, related_name='bank_entry')`.
- `cheque_status`: Enum (`passed`, `bounced`).
- `events`: JSONField audit trail list (`uploaded_from_statement`, `saved`, `pushed`, `unpushed`, etc.).

### [`BankCollection`](file:///home/ubuntu/myerpv3/bank/models.py#L32)
Allocates a payment entry (`ChequeDeposit` or `BankStatement`) to an outstanding invoice (`bill`).
- `bill`: Invoice number (`inum`).
- `amt`: Allocated amount.
- `cheque_entry`: `ForeignKey(ChequeDeposit, null=True)`.
- `bank_entry`: `ForeignKey(BankStatement, null=True)`.
- **Constraint**: `unique_together = ('bill', 'cheque_entry', 'bank_entry')`.

---

## 3. Reconciliation & Matching Engine (`bank/views.py`)

```
Bank Statement Upload (SBI / KVB)
             │
             ▼
      [find_cheque_match]
      - Matches ChequeDeposit by amount, deposit date (within 7d), and cheque number
      ├── Match Found ──> Set type='cheque', link cheque_entry
      │
      └── No Match ──> [find_party_match] (ML Character N-Gram Classifier)
                             │
                             ▼
                   [find_outstanding_match]
                   - Queries open bills from OutstandingReport (< 90 days)
                   - Combinatorial subset-sum: abs(sum(bills) - amt) <= 0.5
                   - Coherence scoring breaks ties: clears oldest cluster
                   ├── Match Found ──> Set type='neft', create BankCollection
                   └── No Match ──> Stays unclassified for manual review
```

### 1. Machine Learning Party Classifier (`find_party_match`)
- Trained via character n-grams: `TfidfVectorizer(analyzer='char', ngram_range=(3, 6))` + `LogisticRegression`.
- Serialized models: `party_classifier_{bank_id}.joblib` and `tfidf_vectorizer_{bank_id}.joblib`.
- Character n-grams allow matching squashed retailer names inside unformatted bank transfer strings without token boundaries.
- Returns predicted `{company_id}/{party_id}` above probability threshold 0.05.

### 2. Combinatorial Bill Matching (`find_outstanding_match` & `get_match`)
- Subtracts pending allocations from any unpushed `BankCollection` records to obtain true pending balances.
- Uses sliding windows of candidate invoices to find subsets where `abs(sum(balances) - amt) <= 0.5`.
- **Coherence Scoring**:
  $$\text{Score} = \frac{\min(\text{ages})}{\text{std\_dev}(\text{ages}) + 1}$$
  Favors subsets of invoices with a tight age cluster (low standard deviation) and clears older outstanding invoices first.

### 3. UPI Matching (`auto_match_upi`)
- Auto-detects cash deposits via keywords (`cash` and `deposit`).
- Pulls live UPI settlement reports from RSUnify via `IkeaBank(company_id).upi_statement(fromd - 3 days, tod)`.
- Matches Unilever UPI `PAYMENT ID` embedded in the bank narrative and tags as `type = "upi"`.

---

## 4. Pushing Collections to Unilever RSUnify (`push_collection`)

1. **Statement ID Allocation**: Assigns random unique 6-digit integers (`100000..999999`) as the receipt reference.
2. **Pre-emptive Bounce (`bounce_cheques`)**: Cancels any previously stuck `PENDING` cheques in RSUnify to avoid collisions.
3. **Two Push Channels**:
   - **Fast Excel Upload (`process_excel_collection`)**: Used when every invoice for that cheque is fully settled (`coll_obj.amt == outstanding_amt`). Uploads to `/rsunify/app/collection/collectionUpload`.
   - **Collection Grid API (`process_grid_collection`)**: **Fallback rule**: If even a single bill is partially settled, all bills for that cheque fall back to posting JSON to `/rsunify/app/collection/insertcollection`.
4. **Cheque Settlement (`settle_cheques`)**: Downloads pending cheque template from RSUnify, sets `STATUS = "SETTLED"`, and uploads back to clear credit limits.
5. **Reversals (`unpush_collection`)**: RSUnify has no delete endpoint; reversals download the cheque from RSUnify and upload a status setting it to `"BOUNCED"`.

---

## 5. Key API Endpoints (`bank/urls.py`)

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/bank/bank_statement_upload/` | `views.bank_statement_upload` | Uploads SBI/KVB statement, checks date continuity, triggers smart match. |
| `POST` | `/bank/deposit_slip/` | `views.generate_deposit_slip` | Generates deposit slip Excel for selected cheques; updates `deposit_date` to today. |
| `POST` | `/bank/smart_match/` | `views.smart_match_view` | Triggers automated cheque + ML NEFT matching on selected statement lines. |
| `POST` | `/bank/push_collection/` | `views.push_collection` | Assigns statement IDs, pushes to RSUnify via Excel/Grid, settles cheques. |
| `POST` | `/bank/unpush_collection/` | `views.unpush_collection` | Marks settled collections as BOUNCED in RSUnify to reverse them. |
| `POST` | `/bank/refresh_bank/` | `views.refresh_bank` | Re-fetches last 7 days collections and current outstandings from RSUnify. |
| `POST` | `/bank/bank_summary/` | `views.bank_summary` | Generates cross-entity Excel reconciling bank credits vs RSUnify collections. |
| `GET` | `/bank/cheque/` | `modelviews.ChequeViewSet` | Filterable list of cheques (`is_depositable`, `company`, `party`). |
| `GET` | `/bank/bankstatement/` | `modelviews.BankStatementViewSet` | Filterable list of statements (`status`, `company`, `party`, `type`). |

---

## 6. Edge Cases & Gotchas

1. **Date Continuity Enforcement**: Uploading a statement with gaps in dates is rejected. The start date must overlap with or immediately follow the latest transaction in the database.
2. **Decimal Cheque Numbers**: KVB bank statements often format integer cheque numbers as floats (`123456.0`). The parser explicitly strips `.0`.
3. **Leading Zero Stripping**: Retailer cheque numbers often drop leading zeros. Matching logic always normalizes with `.lstrip('0')`.
