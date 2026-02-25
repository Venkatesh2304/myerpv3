import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

# Adjusted to match manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myerpv2.settings')
django.setup()

from custom.classes import Unilever
from core.models import UserSession
import logging

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger('unilever')

try:
    username = "lakme_rural"
    
    # Ensure UserSession exists for testing
    UserSession.objects.get_or_create(
        user=username,
        key='unilever',
        defaults={
            'username': 'R41B862',
            'password': 'Lakme$$2026'
        }
    )

    print(f"\n--- Initializing Unilever Session for user: {username} ---")
    unilever = Unilever(user=username)

    print("\n--- Final Session Cookies ---")
    for cookie in unilever.cookies:
        print(f"{cookie.name}: {cookie.value[:20]}... (Domain: {cookie.domain})")

    print("\n--- Final Login Verdict ---")
    verified = unilever.is_logged_in()
    print(f"Logged in: {verified}")

    if verified:
        from datetime import date
        print("\n--- Testing SAP Ledger ---")
        # Record count should be around 41 for this user/range
        df = unilever.ledger(from_date=date(2025, 11, 1), to_date=date(2025, 11, 30))
        if not df.empty:
            print(f"Successfully retrieved {len(df)} ledger records.")
        else:
            print("Ledger retrieval failed or returned empty.")
        print("\n--- Testing ILM PDF Fetch (Memory) ---")
        # Fetching for Nov 2025
        documents = unilever.ilm_pdf(month=11, year=2025)
        
        if documents:
            print(f"Successfully retrieved {len(documents)} document entries with PDF data.")
            # Verify the first one has data
            first_doc = documents[0]
            print(f"First Doc: {first_doc['doc_no']} | Date: {first_doc['date']} | PDF Size: {len(first_doc['pdf'].getvalue())} bytes")
        else:
            print("No ILM documents processed.")

except Exception as e:
    print(f"\n!!! TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
