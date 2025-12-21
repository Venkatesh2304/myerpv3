from django.test import TransactionTestCase, RequestFactory
from core.models import Company, User, UserSession
import datetime
from django.urls import reverse
import json
import unittest.mock

class RealBillingIntegrationTest(TransactionTestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.factory = RequestFactory()
        
        # Ensure User and Company exist (or use existing if DB is persistent across tests which it isn't usually)
        # Ensure User and Company exist (or use existing if DB is persistent across tests which it isn't usually)
        from core.models import Organization
        self.org, _ = Organization.objects.get_or_create(name="HUL")
        self.company, _ = Company.objects.get_or_create(name="devaki_hul", organization=self.org)
        self.user, _ = User.objects.get_or_create(username="devaki", organization=self.org)
        self.user.companies.add(self.company)
        
        # Ensure UserSession exists with REAL credentials
        UserSession.objects.update_or_create(
            user="devaki_hul",
            key="ikea",
            defaults={
                "username": "IIT",
                "password": "Ven@1234",
                "config": {
                    "dbName": "41A392",
                    "home": "https://leveredge18.hulcd.com",
                    "bill_prefix" : "A",
                    "auto_delivery_process" : True
                }
            }
        )
        self.client.force_authenticate(user=self.user)

    def test_real_get_order(self):
        """
        Integration test for get_order API with REAL Ikea backend.
        """
        print("\nRunning Real Integration Test for get_order...")
        url = reverse('get_order')
        data = {
            "company": self.company.pk,
            "order_date": str(datetime.date.today()),
            "lines": 100
        }
        
        response = self.client.post(url, data, format='json')
        
        if response.status_code != 200:
            print(f"Test failed with status {response.status_code}: {response.content}")
        
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        
        self.assertIn("orders", json_response)
        self.assertIn("hash", json_response)
        
        orders = json_response["orders"]
        print(f"Received {len(orders)} orders from Ikea.")
        
        if len(orders) > 0:
            first_order = orders[0]
            print("Sample Order Data:", first_order)
            
            # Print RAW data for debugging
            raw_mol = json_response.get("raw_data", {}).get("mol", [])
            if raw_mol:
                print("Raw MOL Item:", raw_mol[0])

            self.assertIn("order_no", first_order)
            self.assertIn("party", first_order)
            self.assertIn("bill_value", first_order)
            self.assertIn("lines", first_order)

        for order in orders:
            print(order)

       