import os
import sys
import django
import logging
from io import BytesIO

# Add current directory to path
sys.path.append(os.getcwd())

# Adjusted to match manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myerpv2.settings')
django.setup()

from custom.classes import Unilever
from core.models import UserSession

# Setup logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger('unilever_batch')

def main():
    username = "devaki_hul"
    
    print(f"\n--- Initializing Unilever Session for: {username} ---")
    unilever = Unilever(user=username)
    
    if not unilever.is_logged_in():
        logger.error("Failed to login to SAP. Check credentials or cookie injection.")
        return

    # User Request
    months_to_fetch = []
    curr_m, curr_y = 2, 2025
    to_m , to_y = 12, 2025
    while (curr_y, curr_m) <= (to_y, to_m):
        months_to_fetch.append((curr_m, curr_y))
        curr_m = curr_m + 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1

    for month, year in months_to_fetch:
        print(f"\n>>> Fetching ILM PDFs for {month:02d}/{year}")
        
        # Directory: ilm/username/monthyear(012025)/doc.pdf
        folder_suffix = f"{month:02d}{year}"
        dir_name = f"ilm/{username}/{folder_suffix}"
        os.makedirs(dir_name, exist_ok=True)

        #If folder already exists, skip
        if os.path.exists(dir_name) and len(os.listdir(dir_name)) > 0:
            print(f"Folder already exists for {month:02d}/{year}")
            continue
        
        try:
            results = unilever.ilm_pdf(month=month, year=year)
            if not results:
                print(f"No documents found for {month:02d}/{year}")
                continue
                
            for res in results:
                doc_no = res['doc_no']
                pdf_data = res['pdf']
                
                file_path = f"{dir_name}/{doc_no}.pdf"
                with open(file_path, 'wb') as f:
                    f.write(pdf_data.getvalue())
                # print(f"Saved: {file_path}") # Suppress individual file logs to keep output clean
            
            print(f"Completed {month:02d}/{year}: Downloaded {len(results)} PDFs.")
            
        except Exception as e:
            logger.error(f"Error processing {month:02d}/{year}: {e}")

    print("\nBatch download process finished.")

if __name__ == "__main__":
    main()
