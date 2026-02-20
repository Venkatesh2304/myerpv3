from django.core.management.base import BaseCommand
from core.models import Company

class Command(BaseCommand):
    help = 'Update print_types for specific companies'

    def handle(self, *args, **options):
        all_print_types = [
            "both_copy",
            "first_copy", 
            "first_copy_new",
            "double_first_copy", 
            "second_copy", 
            "loading_sheet", 
            "loading_sheet_salesman", 
            "picking_sheet"
        ]

        # 1. devaki_hul: all except picking_sheet and first_copy_new
        try:
            devaki = Company.objects.get(name="devaki_hul")
            devaki.print_types = [pt for pt in all_print_types if pt not in ["picking_sheet", "first_copy_new"]]
            devaki.save()
            self.stdout.write(self.style.SUCCESS(f"Updated devaki_hul with: {devaki.print_types}"))
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR("Company devaki_hul does not exist"))

        # 2. lakme_rural: only picking_sheet and first_copy_new
        try:
            rural = Company.objects.get(name="lakme_rural")
            rural.print_types = ["picking_sheet", "first_copy_new"]
            rural.save()
            self.stdout.write(self.style.SUCCESS(f"Updated lakme_rural with: {rural.print_types}"))
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR("Company lakme_rural does not exist"))

        # 3. lakme_urban: only picking_sheet and first_copy_new
        try:
            urban = Company.objects.get(name="lakme_urban")
            urban.print_types = ["picking_sheet", "first_copy_new"]
            urban.save()
            self.stdout.write(self.style.SUCCESS(f"Updated lakme_urban with: {urban.print_types}"))
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR("Company lakme_urban does not exist"))
