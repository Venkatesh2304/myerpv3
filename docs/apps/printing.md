# App: `printing` — Production Invoice Printing, Dot-Matrix Formatting & Barcode Stamping

> Purpose: Multi-copy invoice printing engine, dot-matrix stream parsing (TVS MSP 250 Star), blank page removal, machine-readable Aztec 2D barcode stamping, two-pass corruption verification, and E-Invoice pre-print interception.

---

## 1. Business Purpose & Operational Context

In FMCG distribution depots, invoices must be printed immediately following bill generation under strict warehouse hardware constraints:
1. **Continuous Dot-Matrix Tractors (TVS MSP 250 Star)**: Used for compact **Store/Office Copies ("Second Copy")** to minimize paper and ribbon consumption.
2. **A4 Cut-Sheet Laser/Inkjet Printers**: Used for **Customer Invoices ("First Copy")** and **Salesman Loading Sheets**, requiring machine-readable 2D barcodes for delivery tracking.

The `printing` app abstracts portal PDF and text downloads, renders 2-per-page store copies via WeasyPrint, stamps Aztec barcodes, strips blank trailer pages, verifies PDF integrity character-by-character, and intercepts missing GST E-Invoices before printing.

---

## 2. Printer Strategy & Architecture (`printing/printers.py`)

[`BillPrintingService`](file:///home/ubuntu/myerpv3/printing/print.py) coordinates execution based on `print_type`:

| Print Type | Strategy Class | Output Format & Pipeline |
| :--- | :--- | :--- |
| `first_copy` | `FirstCopyPrinter` | Multi-bill PDF via `fetch_bill_pdfs(old_pdf=True)` $\rightarrow$ Blank page removal $\rightarrow$ Aztec barcode stamping. |
| `first_copy_new` | `FirstCopyPrinterNew` | PDF via visualizer stream (`old_pdf=False`). |
| `second_copy` | `SecondCopyPrinter` | Raw 108-col ASCII text via `fetch_bill_txts()` $\rightarrow$ Jinja2 parsing $\rightarrow$ 2-bills-per-page A4 PDF via WeasyPrint. |
| `both_copy` | Compound Printer | Concatenates `second_copy` followed by `first_copy` into a single print file via `PdfMerger`. |
| `loading_sheet` | `LoadingSheetPrinter` | Warehouse picking sheet from `Ikea.loading_sheet()`. |
| `loading_sheet_salesman` | `SalesmanLoadingSheetPrinter` | Salesman dispatch sheet with Aztec delivery barcode; registers [`SalesmanLoadingSheet`](file:///home/ubuntu/myerpv3/bill/models.py#L33) records. |
| `picking_sheet` | `PickingLoadingSheetPrinter` | Line-item SKU picking sheet generated via ReportLab. |
| `reload_bill` | Service method | Resets print state, sets `is_reloaded=True`, deletes existing loading sheets. |

---

## 3. The Two-Pass Corruption Verification Check

Upstream portal PDF generators intermittently suffer from concurrency bugs where multi-bill PDFs swap pages or drop headers.

To prevent printing defective invoices, [`Billing.fetch_bill_pdfs`](file:///home/ubuntu/myerpv3/custom/classes.py#L845) executes a strict verification check:
```python
pdf1 = self.get_bill_pdf(group[0], group[-1]) # Batch PDF
pdf2 = self.get_bill_pdf(group[0], group[0])  # Single-bill PDF

# Compare text extracted character-by-character
reader1 = PdfReader(pdf1).pages
reader2 = PdfReader(pdf2).pages
for page_no in range(len(reader2)):
    if reader2[page_no].extract_text() != reader1[page_no].extract_text():
        # Dumps first_copy_first_download.pdf & first_copy_second_download.pdf
        raise Exception("Print PDF Problem. Canceled First Copy Printing")
```
If text from the single-bill PDF does not match the corresponding page of the batch PDF exactly, printing is immediately aborted.

---

## 4. Document Processing Engine

### 1. Consecutive Bill Grouping (`__group_consecutive_bills`)
Parses bill numbers using regex `r'(\D+)(\d{5})$'` (prefix + 5-digit sequence). Contiguous sequences (e.g. `A1001`, `A1002`, `A1003`) are grouped into single range requests (`A1001` to `A1003`) to minimize portal load.

### 2. Dot-Matrix 2-per-Page Layout (`SecondaryBillGeneratorWeasy`)
- Parses 108-column fixed-pitch ASCII text.
- Extracts `Invoice No`, `Bill Amount`, and `Retailer Name`.
- Applies WeasyPrint styling using Courier 11.5px:
  - Odd bills: separated by 24 blank lines (`lines_spacing`).
  - Even bills: followed by `<div style="page-break-after: always;"></div>`.

### 3. Blank Page Pruning (`PDFEditor.remove_blank_pages_from_first_copy`)
- Inspects PyMuPDF text block coordinates.
- If the blank vertical area `(page.rect.height - max_y) >= 640 pt`, the trailing blank/footer page is pruned.

### 4. Machine-Readable Aztec Barcode Stamping (`AztecCodeGenerator`)
Stamps 2D Aztec barcodes using PyMuPDF + ReportLab:
- **First Copy Invoice**: Stamped at $(x=180, y=760)$, dimensions $50 \times 50\text{ pt}$.
- **Salesman Loading Sheet**: Stamped at $(x=280, y=730)$.

---

## 5. E-Invoice Compliance Interception (`EinvoiceHandler`)

Before physical printing:
1. Identifies bills requiring GST e-invoicing: `ctin__isnull=False, irn__isnull=True`.
2. If pending bills exist:
   - Verifies session: `einvoice_service.is_logged_in()`. If False $\rightarrow$ **returns HTTP 501 `{"key": "einvoice"}` to trigger portal login**.
   - Generates and uploads JSON to the government IRP portal.
   - Handles duplicate error code `2150` (extracts already-registered IRN from error message).
   - Updates `Bill.irn` and syncs IRNs back to IKEA via `Ikea.upload_irn()`.

---

## 6. API Reference (`printing/urls.py`)

### `POST /printing/print_bills/`
- **Request Payload**:
  ```json
  {
    "company": 1,
    "print_type": "both_copy",
    "bills": ["A10001", "A10002"],
    "salesman": "Ramesh K",
    "beat": "Main Bazaar",
    "party": "Murugan Stores",
    "inum": "SM10001"
  }
  ```
- **Responses**:
  - `200 OK`: `{"status": "success", "filepath": "/media/bills/1/bill.pdf"}`
  - `501 Not Implemented`: `{"key": "einvoice"}` (prompts frontend to display captcha login modal)
  - `409 Conflict`: `{"status": "error", "error": "<reason>"}`
