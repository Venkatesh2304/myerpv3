from report.models import CollectionReport
from report.models import SalesRegisterReport
from report.models import OutstandingReport
from django.test import TransactionTestCase, RequestFactory
from unittest.mock import patch, MagicMock
from .billing import  BillingStatus, run_billing_process
from .models import Billing, Orders, BillingProcessStatus
from core.models import Company, User
import datetime
import json
import threading
import time
from django.conf import settings

class BaseBillingTest(TransactionTestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.factory = RequestFactory()
        self.user = User.objects.create(username="devaki")
        self.user.save()

        self.company = Company.objects.create(name="devaki_hul", user=self.user)
        self.company.save()

        from core.models import UserSession
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

class BillingTest(BaseBillingTest):
    @patch('bill.billing.models.Bill') #Need tp mock this as it take daterange args
    @patch('bill.billing.report_models')
    @patch('bill.billing.Billing')
    def test_run_billing_process_company_isolation(self, MockBilling, MockReportModels, MockBillModel):
        import pandas as pd
        # Mock the custom Billing class
        mock_billing_instance = MockBilling.return_value
        mock_billing_instance.prevbills = []
        mock_billing_instance.pushed_collection_party_ids = []
        
        # Create dummy orders DataFrame
        data = {
            'p': ['Party1', 'Party2'],
            'pc': ['P001', 'P002'],
            'on': ['ORD001', 'ORD002'],
            'ph': ['HUL001', 'HUL002'],
            's': ['Salesman1', 'Salesman2'],
            'ar': ['Reason1', 'Credit Exceeded'],
            'm': ['Beat1', 'Beat2'],
            'ot': ['Type1', 'Type2'],
            'bd': ['Prod1', 'Prod2'],
            'bc': ['Batch1', 'Batch2'],
            'cq': [10, 20],
            'aq': [10, 0],
            't': [100.0, 200.0]
        }
        df = pd.DataFrame(data)
        mock_billing_instance.all_orders = df
        mock_billing_instance.filtered_orders = df # All orders are "placed"
        
        mock_billing_instance.bills = []
        mock_billing_instance.user = self.company # Ensure user attribute is set
        mock_billing_instance.order_date = datetime.date.today()
        
        # Create a billing log
        billing_log = Billing.objects.create(company=self.company, start_time=datetime.datetime.now(), status=BillingStatus.Started, date=datetime.date.today())
        for process_name in ["SYNC" , "PREVBILLS" , "RELEASELOCK" , "COLLECTION", "ORDER" , "DELIVERY", "REPORTS"]:
             BillingProcessStatus.objects.create(billing=billing_log, process=process_name, status=BillingStatus.NotStarted)

        data = {"order_date": str(datetime.date.today()), "delete": {}, "force_place": {}, "max_lines": 100}
        
        run_billing_process(billing_log.id, data)
        
        # Verify OrderProducts
        from .models import OrderProducts, BillStatistics
        order_products = OrderProducts.objects.filter(order__company=self.company)
        self.assertTrue(order_products.exists())
        self.assertEqual(order_products.count(), 2)
        self.assertEqual(order_products.get(order__order_no="ORD001").product, "Prod1")
        self.assertEqual(order_products.get(order__order_no="ORD002").product, "Prod2")

        # Verify BillingProcessStatus
        statuses = BillingProcessStatus.objects.filter(billing=billing_log)
        self.assertEqual(statuses.count(), 7) # 7 processes
        self.assertTrue(all(s.status == BillingStatus.Success for s in statuses))
        
        billing_log.refresh_from_db()
        self.assertEqual(billing_log.status, BillingStatus.Success)

        # Print created orders
        print("\n--- Created Orders ---")
        orders = Orders.objects.filter(billing=billing_log)
        for order in orders:
            print(f"Order No: {order.order_no}, Party: {order.party_id}, Company: {order.company.name}, Credit Lock: {order.creditlock}")
        print("----------------------\n")

    @patch('bill.billing.models.Bill')
    @patch('bill.billing.report_models')
    @patch('requests.Session.send')
    def test_run_billing_process_real_instance(self, mock_send, MockReportModels, MockBillModel):
        from core.models import UserSession
        
        # Mock responses
        def mocked_send(request, *args, **kwargs):
            method = request.method
            url = request.url
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.content = b"OK" # Default content as bytes
            mock_resp.request = request # Attach request to response for logging
            mock_resp.elapsed = MagicMock()
            mock_resp.elapsed.total_seconds.return_value = 0.1
            
            if "authentication" in url:
                mock_resp.text = "OK" 
            elif "authenSuccess" in url:
                mock_resp.status_code = 200
            elif "getdelivery" in url or "billsToBeDeliver" in url:
                mock_resp.json.return_value = {"billHdBeanList": []}
            elif "getshikhar" in url or "shikharlist" in url:
                mock_resp.json.return_value = {"shikharOrderList": [None]} 
            elif "getmarketorder" in url or "validateloadcollection" in url or "validateload" in url:
                 mock_resp.json.return_value = {
                     "mcl": [],
                     "mol": [
                         {
                             "on": "REAL001", "p": "Real Party 1", "pc": "RP001", "ph": "HUL001", 
                             "s": "Salesman 1", "ar": "Reason", "m": "Beat 1", "ot": "SH", 
                             "bd": "Prod 1", "bc": "B001", "cq": 10, "aq": 10, "t": 100.0,
                             "pi": "PI001", "m": "RETAIL"
                         }
                     ]
                 }
            elif "postmarketorder" in url or "importSelected" in url:
                mock_resp.json.return_value = {"filePath": "dummy_path"}
            elif "quantumImport" in url:
                if "validateloadcollection" in url:
                    mock_resp.json.return_value = {"mcl": []}
                else:
                    mock_resp.json.return_value = {}
            elif "delete_orders" in url:
                mock_resp.text = "Deleted"
            else:
                mock_resp.text = "OK"
                mock_resp.json.return_value = {}
            
            return mock_resp

        mock_send.side_effect = mocked_send

        # Create billing log
        billing_log = Billing.objects.create(company=self.company, start_time=datetime.datetime.now(), status=BillingStatus.Started, date=datetime.date.today())
        for process_name in ["SYNC" , "PREVBILLS" , "RELEASELOCK" , "COLLECTION", "ORDER" , "DELIVERY", "REPORTS"]:
             BillingProcessStatus.objects.create(billing=billing_log, process=process_name, status=BillingStatus.NotStarted)

        data = {"order_date": str(datetime.date.today()), "delete": {}, "force_place": {}, "max_lines": 100}

        # Run process
        run_billing_process(billing_log.id, data)

        # Verify orders created
        print("\n--- Real Instance Created Orders ---")
        orders = Orders.objects.filter(billing=billing_log)
        for order in orders:
            print(f"Order No: {order.order_no}, Party: {order.party_id}, Company: {order.company.name}")
        print("------------------------------------\n")
        
        self.assertTrue(orders.exists())
        self.assertEqual(orders.first().order_no, "REAL001")

    @patch('bill.billing.models.Bill')
    @patch('bill.billing.report_models')
    @patch('requests.Session.send')
    def test_run_billing_process_comprehensive(self, mock_send, MockReportModels, MockBillModel):
        from bill.models import OrderProducts
        
        # Setup Pre-existing Orders (Simulating previous run today)
        today = datetime.date.today()
        
        # Order A: Value 100. Will change to 200. Forced. -> Should be KEPT.
        ord_a = Orders.objects.create(
            order_no="ORD_A", party_id="P1", party_hul_code="H1", salesman="S1",
            creditlock=True, place_order=False, beat="B1", billing=None,
            date=today, type="SH", company=self.company
        )
        OrderProducts.objects.create(order=ord_a, product="Prod", batch="Batch", quantity=1, allocated=1, rate=100.0, reason="")

        # Order B: Value 100. Will change to 200. Not Forced. -> Should be DROPPED (diff > 1).
        ord_b = Orders.objects.create(
            order_no="ORD_B", party_id="P2", party_hul_code="H2", salesman="S2",
            creditlock=False, place_order=True, beat="B2", billing=None,
            date=today, type="SH", company=self.company
        )
        OrderProducts.objects.create(order=ord_b, product="Prod", batch="Batch", quantity=1, allocated=1, rate=100.0, reason="")

        # Mock responses
        def mocked_send(request, *args, **kwargs):
            method = request.method
            url = request.url
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.content = b"OK"
            mock_resp.elapsed = MagicMock()
            mock_resp.elapsed.total_seconds.return_value = 0.1
            
            if "authentication" in url:
                mock_resp.text = "OK" 
            elif "authenSuccess" in url:
                mock_resp.status_code = 200
            elif "getdelivery" in url or "billsToBeDeliver" in url:
                mock_resp.json.return_value = {"billHdBeanList": []}
            elif "getshikhar" in url or "shikharlist" in url:
                mock_resp.json.return_value = {"shikharOrderList": [None]} 
            elif "getmarketorder" in url or "validateloadcollection" in url or "validateload" in url:
                 mock_resp.json.return_value = {
                     "mcl": [],
                     "mol": [
                         # Order A: Value changed to 200
                         {"on": "ORD_A", "p": "Party A", "pc": "P1", "ph": "H1", "s": "S1", "ar": "Credit Exceeded", "m": "B1", "ot": "SH", "bd": "Prod", "bc": "Batch", "cq": 1, "aq": 1, "t": 200.0, "pi": "PI1", "m": "RETAIL"},
                         # Order B: Value changed to 200
                         {"on": "ORD_B", "p": "Party B", "pc": "P2", "ph": "H2", "s": "S2", "ar": "", "m": "B2", "ot": "SH", "bd": "Prod", "bc": "Batch", "cq": 1, "aq": 1, "t": 200.0, "pi": "PI2", "m": "RETAIL"},
                         # Order C: New Order. Value 300. -> Should be KEPT.
                         {"on": "ORD_C", "p": "Party C", "pc": "P3", "ph": "H3", "s": "S3", "ar": "", "m": "B3", "ot": "SH", "bd": "Prod", "bc": "Batch", "cq": 1, "aq": 1, "t": 300.0, "pi": "PI3", "m": "RETAIL"},
                         # Order D: To be deleted. -> Should be DROPPED.
                         {"on": "ORD_D", "p": "Party D", "pc": "P4", "ph": "H4", "s": "S4", "ar": "", "m": "B4", "ot": "SH", "bd": "Prod", "bc": "Batch", "cq": 1, "aq": 1, "t": 400.0, "pi": "PI4", "m": "RETAIL"},
                     ]
                 }
            elif "postmarketorder" in url or "importSelected" in url:
                mock_resp.json.return_value = {"filePath": "dummy_path"}
            elif "delete_orders" in url:
                mock_resp.text = "Deleted"
            elif "quantumImport" in url:
                if "validateloadcollection" in url:
                    mock_resp.json.return_value = {"mcl": []}
                else:
                    mock_resp.json.return_value = {}
            else:
                mock_resp.text = "OK"
                mock_resp.json.return_value = {}
            
            return mock_resp

        mock_send.side_effect = mocked_send

        # Create billing log
        billing_log = Billing.objects.create(company=self.company, start_time=datetime.datetime.now(), status=BillingStatus.Started, date=today)
        for process_name in ["SYNC" , "PREVBILLS" , "RELEASELOCK" , "COLLECTION", "ORDER" , "DELIVERY", "REPORTS"]:
             BillingProcessStatus.objects.create(billing=billing_log, process=process_name, status=BillingStatus.NotStarted)

        # Input Data
        data = {
            "order_date": str(today),
            "delete": {"ORD_D": True},
            "force_place": {"ORD_A": True},
            "max_lines": 100
        }

        # Run process
        run_billing_process(billing_log.id, data)

        # Verify Orders
        print("\n--- Comprehensive Test Orders ---")
        orders = Orders.objects.filter(billing=billing_log)
        order_nos = list(orders.values_list('order_no', flat=True))
        print(f"Created Orders: {order_nos}")
        print("---------------------------------\n")

        self.assertIn("ORD_A", order_nos, "Forced order A should be present")
        self.assertTrue(orders.get(order_no="ORD_A").place_order, "Forced order A should have place_order=True")
        
        self.assertIn("ORD_B", order_nos, "Changed order B should be present but not placed")
        self.assertFalse(orders.get(order_no="ORD_B").place_order, "Changed order B should have place_order=False")
        
        self.assertIn("ORD_C", order_nos, "New order C should be present")
        self.assertTrue(orders.get(order_no="ORD_C").place_order, "New order C should have place_order=True")
        
        self.assertNotIn("ORD_D", order_nos, "Deleted order D should be filtered out entirely")

    def test_billing_view_integration_no_mocks(self):
        from bill.views import start_billing as billing_view
        from bill.billing import run_billing_process, run_billing_process_thread_safe
        from rest_framework.test import APIRequestFactory
        import threading

        # Custom Thread class to run synchronously ONLY for run_billing_process
        # This avoids deadlocks with ThreadPool used inside run_billing_process
        class SmartThread(threading.Thread):
            def start(self):
                if getattr(self, "_target", None) in [run_billing_process, run_billing_process_thread_safe]:
                    self.run()
                else:
                    super().start()

        # Patch threading.Thread to use SmartThread
        # Patch report_models to avoid external calls
        with patch('bill.billing.threading.Thread', SmartThread):
            
            # Setup
            today = datetime.date.today()
            
            # Prepare Request Data
            data = {
                "company": self.company.pk,
                "order_date": str(today),
                "delete": {},
                "force_place": {},
                "max_lines": 100
            }
            
            # Make Request
            from rest_framework.test import APIClient
            from django.urls import reverse
            url = reverse('start_billing')
            response = self.client.post(url, data, format='json') # Use self.client for the request
            
            print(f"Billing View Response Status: {response.status_code}")
            import json
            resp_data = json.loads(response.content)
            print(f"Billing View Response Data: {resp_data}")
            
            self.assertEqual(response.status_code, 200)
            billing_id = resp_data.get("billing_id")
            self.assertIsNotNone(billing_id)
            
            # Verify Billing Log
            billing_log = Billing.objects.get(id=billing_id)
            print(f"Billing Log Status: {billing_log.status}")
            print(f"Billing Log Error: {billing_log.error}")
            
            # Verify Orders
            orders = Orders.objects.filter(billing=billing_log)
            print(f"Created Orders Count: {orders.count()}")
            print(f"Created Orders: {list(orders.values_list('order_no', flat=True))}")
            
            # Verify BillingProcessStatus
            statuses = BillingProcessStatus.objects.filter(billing=billing_log)
            print("Billing Process Statuses:")
            for s in statuses:
                print(f"  {s.process}: {s.status}")

            #Verify the reports
            outstanding_count = OutstandingReport.objects.count()
            sales_count = SalesRegisterReport.objects.count()
            collection_count = CollectionReport.objects.count()
            self.assertGreater(outstanding_count, 0)
            self.assertGreater(sales_count, 0)
            self.assertGreater(collection_count, 0)
            print(f"Sales Count: {sales_count}")
            print(f"Collection Count: {collection_count}")
            print(f"Outstanding Count: {outstanding_count}")
