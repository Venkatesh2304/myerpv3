import os
import datetime
from typing import List, Dict, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from core.models import Company
from bill.models import Bill, SalesmanLoadingSheet
from .lib.pdf import LoadingSheetPDF, LoadingSheetType, PDFEditor
from custom.classes import Billing

if TYPE_CHECKING:
    from .lib.aztec import AztecCodeGenerator
    from .lib.secondary_bills import SecondaryBillGenerator

class PrintType(Enum):
    FIRST_COPY = "first_copy"
    DOUBLE_FIRST_COPY = "double_first_copy"
    SECOND_COPY = "second_copy"
    LOADING_SHEET = "loading_sheet"
    LOADING_SHEET_SALESMAN = "loading_sheet_salesman"

@dataclass
class PrintContext:
    company: Company
    salesman: Optional[str] = None
    beat: Optional[str] = None
    party: Optional[str] = None
    inum: Optional[str] = None
    
    # Allow extra context if needed
    extra: Dict = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

class Printer(ABC):
    @abstractmethod
    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        """
        Generates print files for the given bills and context.
        Returns a list of absolute file paths to the generated files.
        """
        pass

class FirstCopyPrinter(Printer):
    def __init__(self, files_dir: str, pdf_editor: PDFEditor, aztec_generator: 'AztecCodeGenerator'):
        self.files_dir = files_dir
        self.pdf_editor = pdf_editor
        self.aztec_generator = aztec_generator

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        # Download PDF
        pdf_bytes = billing.fetch_bill_pdfs(bills=bills)
        
        bill_pdf_path = os.path.join(self.files_dir, "bill.pdf")
        
        with open(bill_pdf_path, "wb") as f:
            f.write(pdf_bytes.read())
        
        if not os.path.exists(bill_pdf_path):
            raise FileNotFoundError(f"Generated bill PDF not found at {bill_pdf_path}")

        self.pdf_editor.remove_blank_pages_from_first_copy(bill_pdf_path)
        self.aztec_generator.add_aztec_code_to_first_copy(bill_pdf_path, bill_pdf_path)
        
        # Update DB
        Bill.objects.filter(company=context.company, bill_id__in=bills).update(
            print_type=PrintType.FIRST_COPY.value, 
            print_time=datetime.datetime.now()
        )
        
        return [bill_pdf_path]

class SecondCopyPrinter(Printer):
    def __init__(self, files_dir: str, secondary_bill_generator: 'SecondaryBillGenerator', aztec_generator: 'AztecCodeGenerator'):
        self.files_dir = files_dir
        self.secondary_bill_generator = secondary_bill_generator
        self.aztec_generator = aztec_generator

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        # Download TXT
        txt_bytes = billing.fetch_bill_txts(bills=bills)
        
        txt_path = os.path.join(self.files_dir, "bill.txt")
        docx_path = os.path.join(self.files_dir, "secondary_bill.docx")
        
        with open(txt_path, "wb") as f:
            f.write(txt_bytes.read())
        
        if not os.path.exists(txt_path):
             raise FileNotFoundError(f"Generated bill TXT not found at {txt_path}")

        # Config for secondary bills
        sec_config = {'lines': 15, 'secadd': 'ARIYA', 'secname': 'DEVAKI'}
        
        self.secondary_bill_generator.generate(
            txt_path, 
            docx_path, 
            self.aztec_generator.generate_aztec_code, 
            config=sec_config
        )
        
        return [docx_path]

class LoadingSheetPrinter(Printer):
    def __init__(self, files_dir: str, loading_sheet_pdf: LoadingSheetPDF):
        self.files_dir = files_dir
        self.loading_sheet_pdf = loading_sheet_pdf

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        tables = billing.loading_sheet(bills)
        
        output_path = self.loading_sheet_pdf.generate(
            tables, 
            sheet_type=LoadingSheetType.Plain,
            context={},
            output_dir=self.files_dir
        )
        
        Bill.objects.filter(company=context.company, bill_id__in=bills).update(plain_loading_sheet=True)
        
        return [output_path]

class SalesmanLoadingSheetPrinter(Printer):
    def __init__(self, files_dir: str, loading_sheet_pdf: LoadingSheetPDF, aztec_generator: 'AztecCodeGenerator'):
        self.files_dir = files_dir
        self.loading_sheet_pdf = loading_sheet_pdf
        self.aztec_generator = aztec_generator

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        tables = billing.loading_sheet(bills)
        
        # Prepare context dict for PDF generator
        pdf_context = {
            "salesman": context.salesman,
            "beat": context.beat,
            "party": context.party,
            "inum": context.inum
        }
        
        output_path = self.loading_sheet_pdf.generate(
            tables, 
            sheet_type=LoadingSheetType.Salesman,
            context=pdf_context,
            output_dir=self.files_dir
        )
        
        self.aztec_generator.add_aztec_code_to_loading_sheet_salesman(output_path, output_path)
        
        # Create Loading Sheet Record
        # Note: context.inum is "SM" + bill_id usually.
        loading_sheet = SalesmanLoadingSheet.objects.create(
            company=context.company, 
            inum=context.inum,
            salesman=context.salesman,
            beat=context.beat,
            party=context.party
        )
        
        Bill.objects.filter(company=context.company, bill_id__in=bills).update(
            print_type=PrintType.LOADING_SHEET_SALESMAN.value, 
            print_time=datetime.datetime.now(), 
            loading_sheet_id=loading_sheet.inum
        )
        
        return [output_path]
