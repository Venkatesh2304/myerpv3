from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime
import pandas as pd
from core.models import Company
from custom.classes import Ikea
from ledger.verification import (
    VerificationDataLoader, 
    ClaimsVerification, 
    ShortageVerification, 
    CDTStats, 
    DamageVerification, 
    NMSMVerification
)

class Command(BaseCommand):
    help = 'Runs ledger verification for a company and exports to Excel'

    def add_arguments(self, parser):
        parser.add_argument('company_name', type=str, help='Name of the company')

    def handle(self, *args, **options):
        company_name = options['company_name']
        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Company "{company_name}" not found'))
            return

        # Date range: Start of FY (01/04/2025) to Today
        # Note: Hardcoded as per user request "this year 01/04/2025 to today"
        fromd = datetime.date(2025, 4, 1)
        tod = datetime.date(2026,2,7)

        self.stdout.write(f"Running verification for {company.name} from {fromd} to {tod}")

        # Initialize Loader and Download
        ikea = Ikea(company.pk) # Assuming Ikea class takes company object
        loader = VerificationDataLoader(ikea)
        loader.download_all(fromd, tod)

        # Initialize Verifiers
        verifiers = {
            "Claims": ClaimsVerification(company.pk, fromd, tod, loader),
            "Shortage": ShortageVerification(company.pk, fromd, tod, loader),
            "CDT": CDTStats(company.pk, fromd, tod, loader),
            "Damage": DamageVerification(company.pk, fromd, tod, loader),
            "NMSM": NMSMVerification(company.pk, fromd, tod, loader)
        }

        # Run Verification and Collect Results
        writer = pd.ExcelWriter("a.xlsx", engine='xlsxwriter')
        
        for name, verifier in verifiers.items():
            self.stdout.write(f"Verifying {name}...")
            # try:
            df_result = verifier.verify()
            # Write to sheet
            df_result.to_excel(writer, sheet_name=name)
            # except Exception as e:
            # self.stdout.write(self.style.ERROR(f"Error in {name}: {e}"))
            # Create empty sheet or error sheet?
            # pd.DataFrame({'Error': [str(e)]}).to_excel(writer, sheet_name=name)

        writer.close()
        self.stdout.write(self.style.SUCCESS('Verification completed. Results saved to a.xlsx'))
