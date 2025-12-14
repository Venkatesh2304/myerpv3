from django.core.management.base import BaseCommand
from bill.models import Billing, BillingProcessStatus, Orders
from bill.billing import run_billing_process, billing_process_names, BillingStatus
from core.models import Company
import datetime
import json
import threading

class Command(BaseCommand):
    help = 'Run billing process manually'

    def add_arguments(self, parser):
        parser.add_argument('company', type=str, help='Company Name or ID')
        parser.add_argument('--date', type=str, help='Order Date (YYYY-MM-DD)', default=None)
        parser.add_argument('--force', nargs='+', help='List of order numbers to force place', default=[])
        parser.add_argument('--delete', nargs='+', help='List of order numbers to delete', default=[])

    def handle(self, *args, **options):
        company_name = options['company']
        order_date_str = options['date']
        force_orders = options['force']
        delete_orders = options['delete']

        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Company '{company_name}' not found"))
            return

        if order_date_str:
            try:
                order_date = datetime.datetime.strptime(order_date_str, "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(self.style.ERROR("Invalid date format. Use YYYY-MM-DD"))
                return
        else:
            order_date = datetime.date.today()

        data = {
            "company": company.pk,
            "order_date": str(order_date),
            "force_place": {order_no: True for order_no in force_orders},
            "delete": {order_no: True for order_no in delete_orders},
            "max_lines": 100 # Default
        }

        self.stdout.write(self.style.SUCCESS(f"Starting billing for {company.name} on {order_date}"))
        self.stdout.write(f"Force Orders: {data['force_place']}")
        self.stdout.write(f"Delete Orders: {data['delete']}")

        # Create Billing Log
        billing_log = Billing.objects.create(
            company=company,
            start_time=datetime.datetime.now(),
            status=BillingStatus.Started,
            date=order_date
        )
        
        for process_name in billing_process_names:
            BillingProcessStatus.objects.create(
                billing=billing_log,
                process=process_name,
                status=BillingStatus.NotStarted
            )

        # Run Synchronously for the command
        # We can just call the function directly, bypassing the thread creation in the view
        try:
            run_billing_process(billing_log.id, data)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Billing Process Failed: {e}"))
            # The error is likely already logged in billing_log.error

        # Reload to get updated status
        billing_log.refresh_from_db()
        
        self.stdout.write("\n" + "="*30)
        self.stdout.write(f"Billing ID: {billing_log.id}")
        self.stdout.write(f"Status: {BillingStatus(billing_log.status).name}")
        if billing_log.error:
            self.stdout.write(self.style.ERROR(f"Error: {billing_log.error}"))

        self.stdout.write("\nProcess Statuses:")
        for status in BillingProcessStatus.objects.filter(billing=billing_log):
            status_name = BillingStatus(status.status).name
            color = self.style.SUCCESS if status.status == BillingStatus.Success else self.style.ERROR if status.status == BillingStatus.Failed else self.style.WARNING
            self.stdout.write(f"  {status.process}: {color(status_name)}")

        self.stdout.write("\nOrders:")
        orders = Orders.objects.filter(billing=billing_log)
        if orders.exists():
            for order in orders:
                self.stdout.write(f"  {order.order_no} - {order.party_name} ({order.bill_value}) [{'PLACED' if order.place_order else 'SKIPPED'}]")
        else:
            self.stdout.write("  No orders created.")
            
        self.stdout.write("="*30 + "\n")
