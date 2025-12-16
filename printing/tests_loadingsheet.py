from django.test import TestCase
from unittest.mock import patch
from bill.models import Bill, SalesmanLoadingSheet
from core.models import Company, User
from printing.print import BillPrintingService
from printing.printers import PrintType
import os
from django.conf import settings

class SalesmanLoadingSheetTest(TestCase):
    """
    Unit tests for Salesman Loading Sheet functionality.
    Verifies model updates and logic without actual PDF generation.
    """
    def setUp(self):
        super().setUp()
        self.user = User.objects.create(username="testuser")
        self.company = Company.objects.create(name="testcompany", user=self.user)
        
        # Create dummy bills
        self.bill1 = Bill.objects.create(
            company=self.company,
            bill_id="B001",
        )
        self.bill2 = Bill.objects.create(
            company=self.company,
            bill_id="B002",
        )
        
        # Create a dummy PDF file for testing
        self.dummy_pdf = os.path.join(settings.MEDIA_ROOT, "dummy.pdf")
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(self.dummy_pdf)
        c.drawString(100, 100, "Hello World")
        c.save()

    def tearDown(self):
        if os.path.exists(self.dummy_pdf):
            os.remove(self.dummy_pdf)
        super().tearDown()
        
    @patch('printing.print.Billing')
    @patch('printing.printers.LoadingSheetPDF')
    @patch('printing.printers.AztecCodeGenerator')
    def test_single_bill_loading_sheet(self, mock_aztec, mock_loading_sheet_pdf, MockBilling):
        """
        Verifies that a single bill is correctly processed for a salesman loading sheet.
        """
        # Setup Mocks
        mock_billing_instance = MockBilling.return_value
        mock_billing_instance.loading_sheet.return_value = "dummy_data"
        
        # Configure LoadingSheetPDF mock to return dummy PDF path
        mock_loading_sheet_pdf_instance = mock_loading_sheet_pdf.return_value
        mock_loading_sheet_pdf_instance.generate.return_value = self.dummy_pdf
        
        self.service = BillPrintingService(self.company)
        
        data = {
            "print_type": "loading_sheet_salesman",
            "bills": ["B001"],
            "salesman": "Salesman A",
            "beat": "Beat A",
            "party": "Party A"
        }
        
        # Execute
        response = self.service.print_bills(data)
        
        # Verify Response
        self.assertEqual(response["status"], "success")
        
        # Verify Bill Update
        self.bill1.refresh_from_db()
        self.assertEqual(self.bill1.print_type, PrintType.LOADING_SHEET_SALESMAN.value)
        self.assertIsNotNone(self.bill1.loading_sheet_id)
        self.assertIsNotNone(self.bill1.print_time)
        
        # Verify Loading Sheet Creation
        loading_sheet = SalesmanLoadingSheet.objects.get(inum=self.bill1.loading_sheet_id)
        self.assertEqual(loading_sheet.salesman, "Salesman A")
        self.assertEqual(loading_sheet.beat, "Beat A")
        
        # Verify PDF Generation calls
        mock_loading_sheet_pdf.return_value.generate.assert_called_once()
        mock_aztec.return_value.add_aztec_code_to_loading_sheet_salesman.assert_called_once()

    @patch('printing.print.Billing')
    @patch('printing.printers.LoadingSheetPDF')
    @patch('printing.printers.AztecCodeGenerator')
    def test_multiple_bills_loading_sheet(self, mock_aztec, mock_loading_sheet_pdf, MockBilling):
        """
        Verifies that multiple bills selected for a loading sheet are assigned the same loading_sheet_id.
        """
        # Setup Mocks
        mock_billing_instance = MockBilling.return_value
        
        # Configure LoadingSheetPDF mock
        mock_loading_sheet_pdf_instance = mock_loading_sheet_pdf.return_value
        mock_loading_sheet_pdf_instance.generate.return_value = self.dummy_pdf

        self.service = BillPrintingService(self.company)
        
        data = {
            "print_type": "loading_sheet_salesman",
            "bills": ["B001", "B002"],
            "salesman": "Salesman A",
            "beat": "Beat A",
            "party": "Party A"
        }
        
        # Execute
        response = self.service.print_bills(data)
        
        # Verify Response
        self.assertEqual(response["status"], "success")
        
        # Verify Bills Update
        self.bill1.refresh_from_db()
        self.bill2.refresh_from_db()
        
        self.assertEqual(self.bill1.loading_sheet_id, self.bill2.loading_sheet_id)
        self.assertIsNotNone(self.bill1.loading_sheet_id)
        
        # Verify Loading Sheet Count (Should be 1)
        self.assertEqual(SalesmanLoadingSheet.objects.count(), 1)

    @patch('printing.print.Billing')
    @patch('printing.printers.LoadingSheetPDF')
    @patch('printing.printers.AztecCodeGenerator')
    def test_reprint_loading_sheet(self, mock_aztec, mock_loading_sheet_pdf, MockBilling):
        """
        Verifies that reprinting a loading sheet (same bills) updates the existing loading sheet logic.
        """
        # Configure LoadingSheetPDF mock
        mock_loading_sheet_pdf_instance = mock_loading_sheet_pdf.return_value
        mock_loading_sheet_pdf_instance.generate.return_value = self.dummy_pdf

        self.service = BillPrintingService(self.company)
        # 1. First Print
        data = {
            "print_type": "loading_sheet_salesman",
            "bills": ["B001"],
            "salesman": "Salesman A",
            "beat": "Beat A",
            "party": "Party A"
        }
        self.service.print_bills(data)
        self.bill1.refresh_from_db()
        first_loading_sheet_id = self.bill1.loading_sheet_id
        
        # 2. Second Print (Reprint)
        self.service.print_bills(data)
        self.bill1.refresh_from_db()
        second_loading_sheet_id = self.bill1.loading_sheet_id
        
        # Verify IDs are same (deterministic generation)
        self.assertEqual(first_loading_sheet_id, second_loading_sheet_id)
        
        # Verify old loading sheet is deleted (by checking we have one valid sheet)
        self.assertTrue(SalesmanLoadingSheet.objects.filter(inum=second_loading_sheet_id).exists())
        
        # Verify Bill is updated
        self.assertTrue(self.bill1.is_reloaded)

    @patch('printing.print.Billing')
    @patch('printing.printers.LoadingSheetPDF')
    @patch('printing.printers.AztecCodeGenerator')
    def test_mixed_bills_loading_sheet(self, mock_aztec, mock_loading_sheet_pdf, MockBilling):
        """
        Verifies behavior when bills from different previous loading sheets are merged into a new one.
        """
        # Configure LoadingSheetPDF mock
        mock_loading_sheet_pdf_instance = mock_loading_sheet_pdf.return_value
        mock_loading_sheet_pdf_instance.generate.return_value = self.dummy_pdf

        self.service = BillPrintingService(self.company)
        
        # Print Bill 1
        self.service.print_bills({
            "print_type": "loading_sheet_salesman",
            "bills": ["B001"], "salesman": "S1", "beat": "B1"
        })
        self.bill1.refresh_from_db()
        sheet_a_id = self.bill1.loading_sheet_id
        
        # Print Bill 2
        self.service.print_bills({
            "print_type": "loading_sheet_salesman",
            "bills": ["B002"], "salesman": "S1", "beat": "B1"
        })
        self.bill2.refresh_from_db()
        sheet_b_id = self.bill2.loading_sheet_id
        
        # Print Both
        self.service.print_bills({
            "print_type": "loading_sheet_salesman",
            "bills": ["B001", "B002"], "salesman": "S1", "beat": "B1"
        })
        
        self.bill1.refresh_from_db()
        self.bill2.refresh_from_db()
        
        # Verify both have same new sheet ID
        self.assertEqual(self.bill1.loading_sheet_id, self.bill2.loading_sheet_id)
        new_sheet_id = self.bill1.loading_sheet_id
        
        # new_sheet_id will be SMB001 (from B001)
        self.assertEqual(new_sheet_id, sheet_a_id)
        self.assertNotEqual(new_sheet_id, sheet_b_id)
        
        # Verify only one sheet exists now (the merged one)
        self.assertTrue(SalesmanLoadingSheet.objects.filter(inum=sheet_a_id).exists())
        self.assertFalse(SalesmanLoadingSheet.objects.filter(inum=sheet_b_id).exists())
