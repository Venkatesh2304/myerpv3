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

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for barcode_val, basepack_val in data.items():
            barcode_obj, created = Barcode.objects.get_or_create(
                barcode=barcode_val,
                defaults={'basepack': str(basepack_val), 'manual': False}
            )
            if created:
                created_count += 1
            else:
                if not barcode_obj.manual:
                    if barcode_obj.basepack != str(basepack_val):
                        barcode_obj.basepack = str(basepack_val)
                        barcode_obj.save()
                        updated_count += 1
                else:
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully processed barcodes. Created: {created_count}, Updated: {updated_count}, Skipped (Manual): {skipped_count}'))
