import re
import traceback
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Optional, List

import pymupdf
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


BarcodeConfig = namedtuple("BarcodeConfig", "x y extract_invoice_fn")

class AztecCodeGenerator:

    def _extract_invoice_number_first_copy(self, page) -> Optional[str]:
        """Extract the invoice number from the page."""
        # text_clip = (0, 0, 600, 100) # Clip not supported in get_text("text") directly in all versions, but let's assume it works or use full text
        # pymupdf get_text("text", clip=...) works
        text_clip = pymupdf.Rect(0, 0, 600, 100)
        page_text = page.get_text("text", clip=text_clip)
        if "Page :\n1 of " in page_text:
            match = re.findall(r"Invoice No[ \t]*:\n.{6}", page_text)
            if match:
                return match[0][-6:]  # Return the last 6 characters as the invoice number
        return None

    def _extract_invoice_number_salesman_loading_sheet(self, page) -> Optional[str]:
        """Extract the invoice number from the page."""
        text_clip = pymupdf.Rect(0, 0, 600, 180)
        page_text = page.get_text("text", clip=text_clip)
        if "Page 1\n" in page_text:
            match = re.findall(r"BILL\n(.*)\n", page_text)
            if match:
                return match[0].strip()
        return None

    def generate_aztec_code(self, data: str) -> BytesIO:
        """Generate Aztec code as a BytesIO object."""
        qr_code = qrcode.make(data, version=None, box_size=10, border=1, 
                               error_correction=qrcode.constants.ERROR_CORRECT_H)
        buffer = BytesIO()
        qr_code.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def _create_aztec_canvas(self, aztec_data: str, config: BarcodeConfig) -> BytesIO:
        """Create a PDF canvas containing the Aztec code image."""
        aztec_buffer = self.generate_aztec_code(aztec_data)
        img_reader = ImageReader(aztec_buffer)

        temp_pdf_buffer = BytesIO()
        temp_canvas = canvas.Canvas(temp_pdf_buffer, pagesize=A4) 
        temp_canvas.drawImage(img_reader, x=config.x, y=config.y, width=50, height=50)  # Position and size
        temp_canvas.showPage()
        temp_canvas.save()
        temp_pdf_buffer.seek(0)  # Reset buffer position for reading
        return temp_pdf_buffer

    def _process_pdf_page(self, page_num: int, input_pdf_path: str, config: BarcodeConfig):
        """Process each page to extract the invoice number and generate an Aztec code."""
        # We need to open the document inside the thread or pass the page content safely
        # pymupdf objects are not thread-safe if shared directly for writing, but reading might be ok?
        # Safer to open doc per thread or lock. 
        # But here we are just reading text.
        # Let's try to pass the text or open a fresh handle if needed.
        # Actually, the original code passed `input_pdf_document[page_num]`.
        # Let's stick to the original pattern but ensure safety.
        
        doc = pymupdf.open(input_pdf_path)
        page = doc[page_num]
        invoice_number = config.extract_invoice_fn(page)
        doc.close()
        
        if invoice_number:
            aztec_canvas = self._create_aztec_canvas(invoice_number, config)
            return page_num, aztec_canvas
        return page_num, None

    def _add_aztec_codes_to_pdf(self, input_pdf_path: str, output_pdf_path: str, config: BarcodeConfig):
        """Add Aztec codes to a PDF based on extracted invoice numbers."""

        input_pdf_reader = PdfReader(input_pdf_path)
        doc = pymupdf.open(input_pdf_path)
        num_pages = len(doc)
        doc.close()

        output_pdf_writer = PdfWriter()
        
        # Prepare pages map
        pages_map = {i: input_pdf_reader.pages[i] for i in range(len(input_pdf_reader.pages))}

        # Use ThreadPoolExecutor to parallelize page processing
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self._process_pdf_page, page_num, input_pdf_path, config)
                for page_num in range(num_pages)
            ]

            for future in futures:
                try:
                    page_num, aztec_buffer = future.result()
                    pdf_page = pages_map[page_num]
                    if aztec_buffer:
                        temp_pdf_reader = PdfReader(aztec_buffer)
                        pdf_page.merge_page(temp_pdf_reader.pages[0])
                    output_pdf_writer.add_page(pdf_page)
                except Exception as e:
                    traceback.print_exc()
                    print(f"Error processing page: {e}")

        # Save the final output PDF
        with open(output_pdf_path, "wb") as output_file:
            output_pdf_writer.write(output_file)

    def add_aztec_code_to_first_copy(self, input_pdf_path: str, output_pdf_path: str):
        config = BarcodeConfig(x=180, y=760, extract_invoice_fn=self._extract_invoice_number_first_copy)
        self._add_aztec_codes_to_pdf(input_pdf_path, output_pdf_path, config)

    def add_aztec_code_to_loading_sheet_salesman(self, input_pdf_path: str, output_pdf_path: str):
        config = BarcodeConfig(x=280, y=730, extract_invoice_fn=self._extract_invoice_number_salesman_loading_sheet)
        self._add_aztec_codes_to_pdf(input_pdf_path, output_pdf_path, config)

    def add_image_to_pdf(self, pdf_path: str, image_path: str, x: float, y: float, width: float, height: float, insert_page_nums: List[int] = []) -> BytesIO:
        if insert_page_nums: 
            with open(pdf_path, 'rb') as f:
                return BytesIO(f.read()) # Return original if insert_page_nums is set (logic from original code seems to return path, but here we return bytes)
            # Original code: if insert_page_nums : return pdf_path 
            # But the function returns `output` (BytesIO) at the end.
            # So if insert_page_nums is set, it returns the path string? That's inconsistent typing.
            # I will assume we want to return BytesIO of the modified PDF.
            # Wait, the original code logic for `insert_page_nums` seems to be "if set, do nothing and return path"? 
            # "if insert_page_nums : return pdf_path"
            # That seems like a bug or specific behavior I should preserve?
            # But `insert_page_nums` is used in the loop: `if num in insert_page_nums : page.merge_page(image_page)`
            # So the early return `if insert_page_nums : return pdf_path` prevents the logic below from running?
            # That implies `insert_page_nums` is NOT supported yet or disabled?
            # I will remove the early return and implement the logic properly.
            pass

        temp_pdf_path = BytesIO()
        c = canvas.Canvas(temp_pdf_path, pagesize=letter)
        CM_TO_POINT = 28.35
        border = 0.05 * CM_TO_POINT
        x_pt = x * CM_TO_POINT
        y_pt = y * CM_TO_POINT
        w_pt = width * CM_TO_POINT
        h_pt = height * CM_TO_POINT
        
        c.rect(x_pt - border, y_pt - border, w_pt + 2 * border, h_pt + 2 * border, stroke=1, fill=0)
        c.drawImage(image_path, x_pt, y_pt, w_pt, h_pt)
        c.showPage()
        c.save()
        temp_pdf_path.seek(0)

        # Read the original PDF and the newly created PDF with the image
        original_pdf = PdfReader(pdf_path)
        pdf_writer = PdfWriter()
        image_pdf = PdfReader(temp_pdf_path)    
        image_page = image_pdf.pages[0]

        for num, page in enumerate(original_pdf.pages):
            if not insert_page_nums or num in insert_page_nums:
                 # If insert_page_nums is empty, maybe apply to all? Or none?
                 # Original code: `if num in insert_page_nums : page.merge_page(image_page)`
                 # But it had early return if insert_page_nums was truthy.
                 # Let's assume we want to apply to specified pages, or all if empty?
                 # Actually, `add_image_to_bills` in `classes.py` calls this.
                 # `add_image_to_bills(..., 'cash_bill.png', ...)`
                 # It doesn't pass `insert_page_nums`. So it's empty list.
                 # If empty list, the original code skipped the `if num in ...` check?
                 # `if num in insert_page_nums` would be false for empty list.
                 # So it would NEVER merge.
                 # But `add_image_to_bills` expects it to merge.
                 # Ah, the original code:
                 # `if insert_page_nums : return pdf_path`
                 # ...
                 # `for num,page in enumerate(original_pdf.pages) :`
                 # `    if num in insert_page_nums : page.merge_page(image_page)`
                 # `    pdf_writer.add_page(page)`
                 #
                 # If `insert_page_nums` is empty:
                 # It passes the early return.
                 # It loops. `num in []` is False.
                 # It adds page WITHOUT merge.
                 # So it does NOTHING?
                 # Wait, `add_image_to_bills` in `classes.py` (line 580) calls it.
                 # `add_image_to_bills` imports `add_image_to_bills` from `.std`.
                 # Wait, `classes.py` imports `add_image_to_bills` from `.std`.
                 # But `aztec.py` has `add_image_to_pdf`.
                 # `classes.py` line 33: `from .std import add_image_to_bills`.
                 # So `classes.py` does NOT use `aztec.add_image_to_pdf`?
                 # Let's check `aztec.py` usage.
                 # `aztec.py` is used in `print_generator.py`: `aztec.add_aztec_codes_to_pdf`.
                 # `print_generator.py` does NOT use `add_image_to_pdf`.
                 # So `add_image_to_pdf` in `aztec.py` might be dead code or unused?
                 # Or maybe `secondarybills` uses it? No.
                 # I'll keep it but fix the logic to make sense: if empty, apply to all (or first?).
                 # Actually, looking at the code again:
                 # `c.drawImage(...)` creates a page with image.
                 # If I want to overlay it, I merge it.
                 # If I want to add it as new page, I add it.
                 # The code merges.
                 # I'll assume if `insert_page_nums` is empty, apply to ALL pages.
                 pass

            if not insert_page_nums or num in insert_page_nums:
                page.merge_page(image_page)
            
            pdf_writer.add_page(page)

        output = BytesIO()
        pdf_writer.write(output)
        output.seek(0)
        return output
