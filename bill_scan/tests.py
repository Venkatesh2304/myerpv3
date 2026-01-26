from django.test import TestCase
from bill.models import Bill
from core.models import Company, Organization
from .pdf_helper import generate_bill_list_pdf
import random

class BillPdfTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="TestOrg")
        self.company = Company.objects.create(name="TestCompany", organization=self.org)
        
        # Create 100 bills
        bills = []
        for i in range(10000,10100):
            bill_id = f"AB{i:05d}"
            bills.append(Bill(
                company=self.company,
                bill_id=bill_id,
                bill_amt=100.0,
                party_name="Test Party"
            ))
        Bill.objects.bulk_create(bills)

    def test_generate_bill_pdf(self):
        # Get 100 bill numbers from the Bill model
        bill_numbers = list(Bill.objects.values_list('bill_id', flat=True))
        
        # Shuffle them just to be random as requested
        random.shuffle(bill_numbers)
        
        # Generate PDF
        pdf_buffer = generate_bill_list_pdf(bill_numbers, "Test Vehicle", "2026-01-26", columns=6)
        with open("files/test/bill_scan.pdf", "wb+") as f:
            f.write(pdf_buffer.getvalue())
        
        # Check if it looks like a PDF
        content = pdf_buffer.getvalue()
        self.assertTrue(content.startswith(b'%PDF'), "Output should be a PDF")
        
        # Check if content is not empty
        self.assertGreater(len(content), 0)
