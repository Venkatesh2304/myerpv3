from printing.lib.secondary_bills import SecondaryBillGeneratorWeasy
import os
import pandas as pd
import datetime
from typing import List, Dict, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from core.models import Company
from bill.models import Bill, SalesmanLoadingSheet
from .lib.pdf import LoadingSheetPDF, LoadingSheetType, PDFEditor, PickingLoadingSheetPDF
from custom.classes import Billing

from .lib.aztec import AztecCodeGenerator
from .lib.secondary_bills import SecondaryBillGenerator

class PrintType(Enum):
    FIRST_COPY = "first_copy"
    FIRST_COPY_NEW = "first_copy_new"
    DOUBLE_FIRST_COPY = "double_first_copy"
    SECOND_COPY = "second_copy"
    LOADING_SHEET = "loading_sheet"
    LOADING_SHEET_SALESMAN = "loading_sheet_salesman"
    PICKING_LOADING_SHEET = "picking_loading_sheet"

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

class BaseFirstCopyPrinter(Printer):
    old_pdf = True
    print_type = PrintType.FIRST_COPY

    def __init__(self, files_dir: str):
        self.files_dir = files_dir
        self.pdf_editor = PDFEditor()
        self.aztec_generator = AztecCodeGenerator()

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        # Download PDF
        pdf_bytes = billing.fetch_bill_pdfs(bills=bills, old_pdf=self.old_pdf)
        
        bill_pdf_path = os.path.join(self.files_dir, "bill.pdf")
        
        with open(bill_pdf_path, "wb") as f:
            f.write(pdf_bytes.read())
        
        if not os.path.exists(bill_pdf_path):
            raise FileNotFoundError(f"Generated bill PDF not found at {bill_pdf_path}")

        self.pdf_editor.remove_blank_pages_from_first_copy(bill_pdf_path)
        self.aztec_generator.add_aztec_code_to_first_copy(bill_pdf_path, bill_pdf_path)
        
        # Update DB
        Bill.objects.filter(company=context.company, bill_id__in=bills).update(
            print_type=self.print_type.value, 
            print_time=datetime.datetime.now()
        )
        
        return [bill_pdf_path]

class FirstCopyPrinter(BaseFirstCopyPrinter):
    old_pdf = True
    print_type = PrintType.FIRST_COPY

class FirstCopyPrinterNew(BaseFirstCopyPrinter):
    old_pdf = False
    print_type = PrintType.FIRST_COPY_NEW

class SecondCopyPrinter(Printer):
    def __init__(self, files_dir: str):
        self.files_dir = files_dir
        self.secondary_bill_generator =  SecondaryBillGeneratorWeasy() #SecondaryBillGenerator()
        self.aztec_generator = AztecCodeGenerator()

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
        sec_config = {'secadd': 'ARIYA', 'secname': 'DEVAKI'}
        
        self.secondary_bill_generator.generate(
            txt_path, 
            docx_path, 
            self.aztec_generator.generate_aztec_code, 
            config=sec_config
        )
        
        return [docx_path]

class LoadingSheetPrinter(Printer):
    def __init__(self, files_dir: str):
        self.files_dir = files_dir
        self.loading_sheet_pdf = LoadingSheetPDF()

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
    def __init__(self, files_dir: str):
        self.files_dir = files_dir
        self.loading_sheet_pdf = LoadingSheetPDF()
        self.aztec_generator = AztecCodeGenerator()

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

class PickingLoadingSheetPrinter(Printer):
    def __init__(self, files_dir: str):
        self.files_dir = files_dir
        self.picking_pdf = PickingLoadingSheetPDF()

    def generate(self, bills: List[str], context: PrintContext, billing: Billing) -> List[str]:
        data_list = []
        for bill_no in bills:
            try:
                # Use retrieve_bill instead of loading_sheet
                bill_data = billing.retrive_bill(bill_no)
                if not bill_data:
                    continue
                
                party_name = bill_data.get("partyInfoVO", {}).get("partyName", "N/A")
                products = bill_data.get("billingProductMasterVOList", []) or []
                
                if not products:
                    continue
                    
                # Convert to DataFrame
                df = pd.DataFrame(products)
                
                # Standardize columns for PickingLoadingSheetPDF
                df = df.rename(columns={
                    "prodName": "Product Name",
                    "mrp": "MRP",
                    "qCase": "Case",
                    "qUnits": "Units"
                })
                
                data_list.append({
                    "bill_no": bill_no,
                    "party_name": party_name,
                    "df": df
                })
            except Exception as e:
                print(f"Error retrieving bill {bill_no}: {e}")
                continue

        if not data_list:
            raise Exception("No data found for the selected bills")

        buffer = self.picking_pdf.generate(data_list)
        output_path = os.path.join(self.files_dir, "picking_loading_sheet.pdf")
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())
        
        return [output_path]
