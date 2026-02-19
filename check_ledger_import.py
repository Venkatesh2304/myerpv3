import os
import django
import pandas as pd
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myerpv2.settings")
django.setup()

from core.models import Company, Organization
from ledger.logic import import_ledger_data
from ledger.models import Ledger

def test_ledger_import():
    # Setup company
    org, _ = Organization.objects.get_or_create(name="TestOrg")
    company, _ = Company.objects.get_or_create(name="TestCompany", organization=org)

    # Create dummy CSV
    data = {
        'Date': ['2023-01-01', '2023-01-02'],
        'Transaction Type': ['Sale', 'Payment'],
        'Customer Reference': ['REF001', 'REF002'],
        'Debit': [1000, 0],
        'Credit': [0, 500]
    }
    df = pd.DataFrame(data)
    csv_path = 'test_ledger.csv'
    df.to_csv(csv_path, index=False)

    print("Created test CSV")

    # Run import
    success, message = import_ledger_data(company, csv_path)
    print(f"Import result: {success}, {message}")

    # Verify
    ledgers = Ledger.objects.filter(company=company).order_by('date')
    print(f"Found {ledgers.count()} ledger entries")
    
    for l in ledgers:
        print(f"Date: {l.date}, Type: {l.type}, Ref: {l.ref}, Amt: {l.amt}")

    # Clean up
    if os.path.exists(csv_path):
        os.remove(csv_path)

if __name__ == "__main__":
    test_ledger_import()
