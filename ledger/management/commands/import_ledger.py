from django.core.management.base import BaseCommand
from core.models import Company
from ledger.logic import import_ledger_data

class Command(BaseCommand):
    help = 'Import ledger from Excel/CSV file'

    def add_arguments(self, parser):
        parser.add_argument('company_name', type=str, help='Name of the company')
        parser.add_argument('file_path', type=str, help='Path to the ledger file')

    def handle(self, *args, **kwargs):
        company_name = kwargs['company_name']
        file_path = kwargs['file_path']

        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Company "{company_name}" does not exist'))
            return

        success, message = import_ledger_data(company, file_path)
        
        if success:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stdout.write(self.style.ERROR(message))
