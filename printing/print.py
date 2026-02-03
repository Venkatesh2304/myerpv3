from django.db import transaction
import datetime
from django.http.response import JsonResponse
from requests.models import Response
from printing.lib.einvoice import EinvoiceResult
from printing.lib.einvoice import EinvoiceHandler
from custom.classes import Billing
import os
from typing import Dict, List, Any
from PyPDF2 import PdfMerger
from django.conf import settings
from core.utils import get_media_url


from bill.models import Bill, SalesmanLoadingSheet
from .printers import FirstCopyPrinter, SecondCopyPrinter, LoadingSheetPrinter, SalesmanLoadingSheetPrinter, PrintContext, PrintType, Printer
from .lib.pdf import LoadingSheetPDF, PendingSheetPDF, PDFEditor
from .lib.aztec import AztecCodeGenerator
from .lib.secondary_bills import SecondaryBillGenerator
from custom.classes import Einvoice
from rest_framework.response import Response

class BillPrintingService:
    def __init__(self, company):
        self.company = company
        self.files_dir = os.path.join(settings.MEDIA_ROOT, "bills", str(company.pk))
        os.makedirs(self.files_dir, exist_ok=True)
        
        # Initialize Generators
        # Initialize Generators
        self.pending_sheet_pdf = PendingSheetPDF()
        self.einvoice_handler = EinvoiceHandler(self.company)
        
        # Initialize Printers
        self.printers: Dict[PrintType, Printer] = {
            PrintType.FIRST_COPY: FirstCopyPrinter(self.files_dir),
            PrintType.SECOND_COPY: SecondCopyPrinter(self.files_dir),
            PrintType.LOADING_SHEET: LoadingSheetPrinter(self.files_dir),
            PrintType.LOADING_SHEET_SALESMAN: SalesmanLoadingSheetPrinter(self.files_dir),
        }

    def print_bills(self, data: Dict[str, Any]) -> Dict[str, Any]:
        full_print_type = data.get("print_type")
        bills = data.get("bills", [])
        bills.sort()
        
        if not bills:
            return {"status": "error", "error": "Zero Bills Selected to print"}

        qs = Bill.objects.filter(company=self.company, bill_id__in=bills)

        # Remove already printed, if not loading sheet
        if full_print_type in ["both_copy", "first_copy", "double_first_copy", "loading_sheet_salesman", "reload_bill"]:
            loading_sheets = list(qs.values_list("loading_sheet_id", flat=True).distinct())
            with transaction.atomic() :
                for bill in qs.filter(print_time__isnull = False) : 
                    bill.add_notes(f"bill_reload: {bill.print_type} was reprinted as {full_print_type} @ {datetime.datetime.now()}")
                    bill.is_reloaded = True
                    bill.print_time = None
                    bill.loading_sheet_id = None
                    bill.save()
            SalesmanLoadingSheet.objects.filter(company=self.company, inum__in=loading_sheets).delete()
            qs = qs.all() # Refetch

        if full_print_type == "reload_bill":
            return {"status": "success"}

        # Context
        context = PrintContext(
            company=self.company,
            salesman=data.get("salesman"),
            beat=data.get("beat"),
            party=data.get("party"),
            inum="SM" + bills[0] if bills else None
        )

        # E-Invoice Handling
        error = ""
        einvoice_enabled = self.company.einvoice_enabled
        

        if einvoice_enabled:
            einv_qs = qs.filter(ctin__isnull=False, irn__isnull=True)
            if einv_qs.exists():
                einvoice_result:EinvoiceResult = self.einvoice_handler.handle_upload(einv_qs)
                if not einvoice_result.success:
                    if not einvoice_result.is_einvoice_logged_in :
                        return {"status": "error", "error": "E-Invoice Login Failed", "is_logged_in": False}
                    else:
                        return {"status": "error", "error": einvoice_result.error}
                
        # Determine Print Types
        print_types_map = {
            "both_copy": [PrintType.FIRST_COPY, PrintType.SECOND_COPY],
            "first_copy": [PrintType.FIRST_COPY],
            "double_first_copy": [PrintType.FIRST_COPY],
            "second_copy": [PrintType.SECOND_COPY],
            "loading_sheet": [PrintType.LOADING_SHEET],
            "loading_sheet_salesman": [PrintType.LOADING_SHEET_SALESMAN]
        }
        
        if full_print_type not in print_types_map:
            return {"status": "error", "error": "Invalid print type"}
        
        required_print_types = print_types_map.get(full_print_type)
        
        # Generate Files
        generated_files = {} # Map PrintType -> List[str] (paths)
        
        # Instantiate Billing object once
        billing = Billing(self.company.pk)

        for print_type in required_print_types:
            printer = self.printers.get(print_type)
            if printer:
                try:
                    paths = printer.generate(bills, context, billing)
                    generated_files[print_type] = paths
                except Exception as e:
                    return {"status": "error", "error": f"Printing failed for {print_type}: {e}"}

        # Merge Files
        print_files_map = {
            "both_copy": [ (PrintType.SECOND_COPY, 0), (PrintType.FIRST_COPY, 0) ], # secondary_bill.docx, bill.pdf
            "first_copy": [ (PrintType.FIRST_COPY, 0) ],
            "double_first_copy": [ (PrintType.FIRST_COPY, 0), (PrintType.FIRST_COPY, 0) ],
            "second_copy": [ (PrintType.SECOND_COPY, 0) ],
            "loading_sheet": [ (PrintType.LOADING_SHEET, 0) ],
            "loading_sheet_salesman": [ (PrintType.LOADING_SHEET_SALESMAN, 0), (PrintType.LOADING_SHEET_SALESMAN, 0) ]
        }
        
        if full_print_type not in print_files_map:
            return {"status": "error", "error": "Invalid print type ,not in print_files_map"}
        
        files_to_merge_config = print_files_map.get(full_print_type)

        merger = PdfMerger()
        final_pdf_path = os.path.join(self.files_dir, "bill.pdf")
        
        for print_type, index in files_to_merge_config:
            if print_type in generated_files:
                paths = generated_files[print_type]
                if index < len(paths):
                    file_path = paths[index]
                    
                    # Convert DOCX to PDF if needed
                    if file_path.endswith(".docx"):
                        self._convert_docx_to_pdf(file_path)
                        file_path = file_path.replace(".docx", ".pdf")
                    
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as pdf_file:
                            merger.append(pdf_file)
        
        with open(final_pdf_path, "wb") as f:
            merger.write(f)
        merger.close()

        return {"status": "success", "error": error, "filepath" : get_media_url(final_pdf_path)}

    def _convert_docx_to_pdf(self, docx_path: str):
        # Using libreoffice as in original code
        # os.system is blocking, which is what we want here
        cmd = f"libreoffice --headless --convert-to pdf {docx_path} --outdir {self.files_dir}"
        os.system(cmd)
