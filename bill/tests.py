from django.test import TransactionTestCase, RequestFactory
from unittest.mock import patch, MagicMock
from .models import Billing
from core.models import Company, User
import datetime
import json
from django.urls import reverse

class BaseBillingTest(TransactionTestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.factory = RequestFactory()
        from core.models import Organization
        self.org = Organization.objects.create(name="HUL")
        
        self.company = Company.objects.create(name="devaki_hul", organization=self.org)
        self.company.save()

        self.user = User.objects.create(username="devaki", organization=self.org)
        self.user.companies.add(self.company)
        self.user.save()

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

class BillingApiTest(BaseBillingTest):
    
    @patch('bill.views.Billing')
    @patch('report.models.CollectionReport')
    @patch('report.models.OutstandingReport')
    def test_get_order(self, MockOutstandingReport, MockCollectionReport, MockBilling):
        mock_billing_instance = MockBilling.return_value
        # Mock get_market_order to return correct structure
        mock_billing_instance.get_market_order.return_value = [
            {"on": "ORD001", "p": "Party1", "cq": 10, "t": 10, "aq": 5, "s": "Salesman1", "m": "Beat1", "ot": "Type1", "pc": "Code1"}
        ]
        
        url = reverse('get_order')
        data = {
            "company": self.company.pk,
            "order_date": str(datetime.date.today()),
            "lines": 100
        }
        
        response = self.client.post(url, data, format='json')
        
        if response.status_code != 200:
            print(f"Test failed: {response.content}")
            
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertIn("orders", json_response)
        self.assertIn("hash", json_response)
        
        # Verify Billing model state
        billing = Billing.objects.get(company=self.company)
        self.assertEqual(billing.process, "getorder")
        self.assertFalse(billing.ongoing) # Should be reset to False
        self.assertIsNotNone(billing.market_order_data)
        self.assertEqual(billing.order_date, datetime.date.today())
        
        # Verify calls
        mock_billing_instance.Sync.assert_called_once()
        mock_billing_instance.Collection.assert_called_once()
        mock_billing_instance.get_market_order.assert_called_once()

    @patch('bill.views.Billing')
    @patch('report.models.SalesRegisterReport')
    def test_post_order(self, MockSalesRegisterReport, MockBilling):
        mock_billing_instance = MockBilling.return_value
        mock_billing_instance.bills = ["B001", "B002"]
        
        # Configure SalesRegisterReport mock
        MockSalesRegisterReport.objects.filter.return_value.exclude.return_value.aggregate.return_value = {
            "bill_count": 5,
            "start_bill_no": "B001",
            "end_bill_no": "B005"
        }
        
        # Create Billing object with state
        today = datetime.date.today()
        market_data = [{"on": "ORD001"}]
        import hashlib
        import json
        data_hash = hashlib.md5(json.dumps(market_data, sort_keys=True).encode('utf-8')).hexdigest()
        
        Billing.objects.create(
            company=self.company, 
            process="getorder", 
            market_order_data=market_data,
            order_date=today,
            order_hash=data_hash
        )

        url = reverse('post_order')
        data = {
            "company": self.company.pk,
            "order_date": str(today),
            "lines": 100,
            "order_numbers": ["ORD001"],
            "hash": data_hash
        }
        
        response = self.client.post(url, data, format='json')
        
        if response.status_code != 200:
            print(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Order posted successfully. Log saved.")
        
        # Verify Billing model state
        billing = Billing.objects.get(company=self.company)
        self.assertEqual(billing.process, "postorder")
        self.assertFalse(billing.ongoing)
        
        # Verify calls
        mock_billing_instance.Prevbills.assert_called_once()
        mock_billing_instance.post_market_order.assert_called_once()
        mock_billing_instance.Delivery.assert_called_once()
