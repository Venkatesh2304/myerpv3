import pandas as pd
from django.core.management.base import BaseCommand
from django.utils import timezone
from product_scan.models import SalesScan
import datetime
import os

class Command(BaseCommand):
    help = 'Export scan logs to Excel and print to stdout'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format (default: today)')

    def handle(self, *args, **options):
        date_str = options.get('date')
        if date_str:
            try:
                # Handle YYYY-MM-DD
                date_val = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {date_str}. Use YYYY-MM-DD."))
                return
        else:
            date_val = timezone.now().date()

        self.stdout.write(self.style.SUCCESS(f"Fetching logs for date: {date_val}"))

        # Filter SalesScan by scanned_time__date
        scans = SalesScan.objects.filter(scanned_time__date=date_val)

        log_entries = []
        for scan in scans:
            bill_no = scan.bill_no
            # scan.logs is a list of box logs: [ [log_item, ...], [log_item, ...] ]
            # Each box log is a list of log items.
            if not scan.logs:
                continue
                
            for box_idx, box_logs in enumerate(scan.logs):
                box_no = box_idx + 1
                if not box_logs:
                    continue
                    
                for log in box_logs:
                    if isinstance(log, dict):
                        log_entries.append({
                            'bill_no': bill_no,
                            'box_no': box_no,
                            'type': log.get('type'),
                            'sku': log.get('sku'),
                            'value': log.get('value'),
                            'desc': log.get('desc'),
                            'timestamp': log.get('timestamp'),
                        })

        if not log_entries:
            self.stdout.write(self.style.WARNING(f"No scan logs found for the date: {date_val}"))
            return

        df = pd.DataFrame(log_entries)
        
        # Convert timestamp to readable format if it exists
        if 'timestamp' in df.columns:
            try:
                # Assuming timestamp is in milliseconds (Date.now() in JS)
                df['readable_time'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.strftime('%H:%M:%S')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not convert timestamp: {e}"))

        # Print to stdout
        self.stdout.write("\n--- Scan Logs Output ---")
        self.stdout.write(df.to_string(index=False))
        self.stdout.write("------------------------\n")

        # Save to Excel
        excel_file = 'scan.xlsx'
        try:
            df.to_excel(excel_file, index=False)
            self.stdout.write(self.style.SUCCESS(f"Logs saved to {os.path.abspath(excel_file)}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to save Excel file: {e}"))
