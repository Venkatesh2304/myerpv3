import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

# Adjusted to match manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myerpv2.settings')
django.setup()

from custom.classes import Unilever
import logging
import pandas as pd

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger('unilever')

try:
    username = "demo_unilever"
    print(f"\n--- Initializing Unilever Session for user: {username} ---")
    unilever = Unilever(user=username)

    print("\n--- Final Session Cookies ---")
    for cookie in unilever.cookies:
        print(f"{cookie.name}: {cookie.value[:20]}... (Domain: {cookie.domain})")

    print("\n--- Final Login Verdict ---")
    verified = unilever.is_logged_in()
    print(f"Logged in: {verified}")

    if verified:
        print("\n--- Fetching Ledger Data ---")
        from_date = "01.02.2026"
        to_date = "22.02.2026"
        df = unilever.ledger(from_date, to_date)
        
        if not df.empty:
            print(f"Successfully retrieved {len(df)} records!")
            print("\nSample Data (First 5 rows):")
            print(df.head())
            
            # Save to Excel for inspection
            output_file = 'ledger_test_output.xlsx'
            df.to_excel(output_file, index=False)
            print(f"\nSaved results to {output_file}")
        else:
            print("Ledger retrieval returned no data.")

except Exception as e:
    print(f"\n!!! TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
