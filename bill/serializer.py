# Create a serialiser for BillingProcess
from bill.billing import BillingStatus
import datetime
from bill.models import *
from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db.models import Max, F, Subquery, OuterRef, Q, Min, Sum, Count
from report.models import CollectionReport, SalesRegisterReport, OutstandingReport

class BillingSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = Billing
        fields = ["stats"]

    def get_stats(self, obj):
        today = datetime.date.today()

        today_stats = (
            SalesRegisterReport.objects.filter(date=today, type="sales",company_id = obj.company_id)
            .exclude(beat__contains="WHOLE")
            .aggregate(
                bill_count=Count("inum"),
                start_bill_no=Min("inum"),
                end_bill_no=Max("inum"),
            )
        )

        today_stats |= Billing.objects.filter(time__date=today,company_id = obj.company_id).aggregate(
            success=Count("status", filter=Q(status="postorder")),
            failures=Count("status", filter=Q(status="failed")), # Assuming failed status might be added later or just 0
        )

        stats = {
            "today": {
                "TODAY BILLS COUNT": today_stats["bill_count"],
                "TODAY BILLS": f'{today_stats["start_bill_no"]} - {today_stats["end_bill_no"]}',
                "SUCCESS": today_stats["success"],
                "FAILURES": today_stats["failures"],
            },
            "last": {
                "LAST BILLS COUNT": "-", 
                "LAST BILLS": "-",
                "LAST STATUS": obj.status.upper(),
                "LAST TIME": f'{obj.time.strftime("%H:%M:%S") if obj.time else "-"}',
                "LAST REJECTED": "-",
                "LAST PENDING": "-",
            },
            "bill_counts": {
                "rejected": 0,
                "pending": 0,
                "creditlock": 0,
            },
        }
        return stats

class BillSerializer(serializers.ModelSerializer):
    bill = serializers.SlugField(source="bill_id", read_only=True)
    date = serializers.SlugField(source="bill_date", read_only=True)
    amt = serializers.DecimalField(source="bill_amt",max_digits=10,decimal_places=0)
    party = serializers.SlugField(source="party_name", read_only=True)
    einvoice = serializers.SerializerMethodField()
    class Meta:
        model = Bill
        fields = ["company_id","bill", "party", "date", "salesman", "beat","amt","print_time","print_type","einvoice","delivered"]

    def get_einvoice(self, obj):
        return bool(obj.ctin is None) or bool(obj.irn)
