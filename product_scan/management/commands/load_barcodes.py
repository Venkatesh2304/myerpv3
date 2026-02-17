from django.core.management.base import BaseCommand
import json
import os
from django.conf import settings
from product_scan.models import Barcode

class Command(BaseCommand):
    help = 'Load barcodes from barcodes.json'

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'barcodes.json')
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r') as f:
            data = json.load(f)

        barcodes_to_create = []
        for barcode, basepack in data.items():
            barcodes_to_create.append(Barcode(barcode=barcode, basepack=basepack))
        
        # Using ignore_conflicts=True to avoid errors if run multiple times
        Barcode.objects.bulk_create(barcodes_to_create, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(f'Successfully loaded {len(barcodes_to_create)} barcodes.'))
