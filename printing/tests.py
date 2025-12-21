from django.test import TestCase, TransactionTestCase, RequestFactory
from unittest.mock import patch, MagicMock
from bill.models import Bill, SalesmanLoadingSheet
from core.models import Company, User, UserSession
from printing.print import BillPrintingService
from printing.printers import PrintType
from custom.classes import Billing
import os
from django.conf import settings
from report.models import SalesRegisterReport, DateRangeArgs
import datetime

class PrintingTestMixin:
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.factory = RequestFactory()
        from core.models import Organization
        self.org = Organization.objects.create(name="HUL")
        
        self.company = Company.objects.create(name="devaki_hul", organization=self.org, einvoice_enabled=False)
        self.company.save()

        self.user = User.objects.create(username="devaki", organization=self.org)
        self.user.companies.add(self.company)
        self.user.save()

        UserSession.objects.update_or_create(
            user="devaki_hul",
            key="ikea",
            username="IIT",
            password="Ven@1234",
            config={
                "dbName": "41A392",
                "home": "https://leveredge18.hulcd.com",
                "bill_prefix" : "A",
                "auto_delivery_process" : True
            }
        )
        self.client.force_authenticate(user=self.user)

class BillPrintingTest(PrintingTestMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
    
        # 1. Login to IKEA (Real Credentials)
        # This will trigger network call. User says credentials are valid.
        billing = Billing(self.company.pk)
        
        # 2. Sync Reports to get actual bills
        # This will fetch SalesRegisterReport and populate Bill table
        today = datetime.date.today()
        args = DateRangeArgs(fromd=today-datetime.timedelta(days=1), tod=today)
        SalesRegisterReport.update_db(billing, self.company, args)
        Bill.sync_with_salesregister(self.company, fromd=args.fromd, tod=args.tod)
        
        # 3. Get a valid bill from DB
        bill = Bill.objects.filter(company=self.company).first()
        
        if not bill:
            raise Exception("No Bills Found Yesterday & Today")
        else:
            self.bill_id = bill.bill_id
            print(f"Testing with actual bill ID: {self.bill_id}")

    def test_print_bills(self):
        """
        Integration test for print_bills view.
        Uses real company and syncs reports to get valid bills.
        Tests FIRST_COPY, SECOND_COPY, and LOADING_SHEET.
        """
        from django.urls import reverse
        
        url = reverse('print_bills')
        data = {
            "company": self.company.pk,
            "print_type": "first_copy",
            "bills": [self.bill_id],
            "salesman": "Test Salesman",
            "beat": "Test Beat",
            "party": "Test Party",
            "inum": "12345"
        }

        # Helper to verify and move file
        def verify_and_move(print_type_suffix):
            final_pdf = os.path.join(settings.MEDIA_ROOT, "bills", str(self.company.pk), "bill.pdf")
            self.assertTrue(os.path.exists(final_pdf), f"bill.pdf not found for {print_type_suffix}")
            
            test_dir = os.path.join(settings.MEDIA_ROOT, "test")
            os.makedirs(test_dir, exist_ok=True)
            
            target_name = f"bill_{self.bill_id}_{print_type_suffix}.pdf"
            target_path = os.path.join(test_dir, target_name)
            
            import shutil
            shutil.move(final_pdf, target_path)
            print(f"Moved {final_pdf} to {target_path}")

        # 4. Test FIRST_COPY
        response = self.client.post(url, data, format='json')
        
        if response.status_code != 200:
            print(f"Test failed with status {response.status_code}: {response.content}")
        
        filepath = f'/media/bills/{self.company.pk}/bill.pdf'
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'error': '', 'filepath': filepath})
        verify_and_move("first_copy")
        
        # 5. Test SECOND_COPY
        data["print_type"] = "second_copy"
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'error': '', 'filepath': filepath})
        verify_and_move("second_copy")
            
        # 6. Test LOADING_SHEET
        data["print_type"] = "loading_sheet"
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'error': '', 'filepath': filepath})
        verify_and_move("loading_sheet")

        # 7. Test LOADING_SHEET_SALESMAN
        data["print_type"] = "loading_sheet_salesman"
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'error': '', 'filepath': filepath})
        verify_and_move("loading_sheet_salesman")


