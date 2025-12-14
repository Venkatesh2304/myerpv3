from django.test import TestCase
from printing.lib.pdf import LoadingSheetPDF, PendingSheetPDF, BaseTablePDF, LoadingSheetType
import pandas as pd
import os
import datetime
from io import BytesIO

class PDFGenerationTest(TestCase):
    def setUp(self):
        self.files_dir = "files/test"
        os.makedirs(self.files_dir, exist_ok=True)

    def test_loading_sheet_salesman(self):
        # Create dummy data
        df = pd.DataFrame({
            "Sr No": [1, 2],
            "Product Name": ["Prod A", "Prod B"],
            "MRP": ["100.0", "200.0"],
            "Total LC.Units": ["1.0", "2.5"],
            "Total FC": [10, 20],
            "Total Gross Sales": [1000, 2000],
            "UPC": ["123", "456"],
            "Division Name": ["Div 1", "Div 2"]
        })
        party_sales = pd.DataFrame({
            "Bill No": ["B1", "B2"],
            "Party": ["P1", "P2"],
            "Gross Amount": [500, 600],
            "Sch.Disc": [10, 20],
            "Net Amt": [490, 580]
        })
        tables = (df, party_sales)
        context = {"salesman": "S1", "beat": "B1", "party": "P1", "inum": "I1"}
        
        # Test direct class usage
        generator = LoadingSheetPDF()
        output_path = generator.generate(tables, LoadingSheetType.Salesman, context, self.files_dir)
        self.assertTrue(os.path.exists(output_path))
        self.assertTrue(output_path.endswith("loading.pdf"))

    def test_loading_sheet_plain(self):
        # Create dummy data
        df = pd.DataFrame({
            "Sr No": [1, 2],
            "Product Name": ["Prod A", "Prod B"],
            "MRP": ["100.0", "200.0"],
            "Total LC.Units": ["1.0", "2.5"],
            "Total FC": [10, 20],
            "Total Gross Sales": [1000, 2000],
            "UPC": ["123", "456"],
            "Division Name": ["Div 1", "Div 2"]
        })
        party_sales = pd.DataFrame({
            "Bill No": ["B1", "B2"],
            "Party": ["P1", "P2"],
            "Gross Amount": [500, 600],
            "Sch.Disc": [10, 20],
            "Net Amt": [490, 580]
        })
        tables = (df, party_sales)
        
        # Test direct class usage
        generator = LoadingSheetPDF()
        output_path = generator.generate(tables, LoadingSheetType.Plain, {}, self.files_dir)
        self.assertTrue(os.path.exists(output_path))

    def test_pending_sheet(self):
        df = pd.DataFrame({
            "Bill No": ["B1"],
            "Party Name": ["P1"],
            "Salesperson Name": ["S1"],
            "Bill Net Amt": ["100"],
            "Collected Amount": ["0"],
            "OutstANDing Amount": ["100"],
            "Bill Ageing (In Days)": ["10"],
            "Date": ["2023-01-01"]
        })
        
        # Test direct class usage
        generator = PendingSheetPDF()
        output = generator.generate(df, "Sheet1", "S1", "B1", datetime.date.today())
        self.assertIsInstance(output, BytesIO)
        self.assertTrue(output.getbuffer().nbytes > 0)
        with open(os.path.join(self.files_dir, "pending.pdf"), "wb") as f:
            f.write(output.getvalue())

