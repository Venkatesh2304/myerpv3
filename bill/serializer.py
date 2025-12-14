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

class BillingProcessStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingProcessStatus
        fields = ["process", "status", "time"]

class OrderSerializer(serializers.ModelSerializer):
    party = serializers.CharField(source="party_name", read_only=True)
    potential_release = serializers.SerializerMethodField()

    class Meta:
        model = Orders
        fields = [
            "order_no",
            "party",
            "lines",
            "bill_value",
            "OS",
            "coll",
            "salesman",
            "beat",
            "phone",
            "type",
            "potential_release",
        ]

    def get_potential_release(self, order):
        if not order.place_order : return False 
        today = datetime.date.today()
        outstanding_qs = OutstandingReport.objects.filter(
            party_id=order.party_id , beat=order.beat , company_id = order.company_id
        )
        today_bill_count = SalesRegisterReport.objects.filter(
            party_id=order.party_id, company_id = order.company_id , date=today, type = "sales"
        ).count()
        if (today_bill_count == 0) and (outstanding_qs.count() == 1):
            bill_value = order.bill_value
            outstanding_bill = outstanding_qs.first()
            outstanding_value = -outstanding_bill.balance
            if bill_value < 200:
                return False

            max_outstanding_day = (today - outstanding_bill.bill_date).days
            max_collection_day = CollectionReport.objects.filter(
                party_name=order.party_name, date=today, company_id = order.company_id
            ).aggregate(date=Max("bill_date"))["date"]
            max_collection_day = (
                (today - max_collection_day).days if max_collection_day else 0
            )
            if (max_collection_day > 21) or (max_outstanding_day > 21):
                return False
            if (bill_value <= 500) or (outstanding_value <= 500):
                return True
        return False

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

        today_stats |= Billing.objects.filter(start_time__gte=today,company_id = obj.company_id).aggregate(
            success=Count("status", filter=Q(status=BillingStatus.Success)),
            failures=Count("status", filter=Q(status=BillingStatus.Failed)),
        )

        orders_qs = Orders.objects.filter(billing=obj).exclude(
            beat__contains="WHOLE"
        )

        stats = {
            "today": {
                "TODAY BILLS COUNT": today_stats["bill_count"],
                "TODAY BILLS": f'{today_stats["start_bill_no"]} - {today_stats["end_bill_no"]}',
                "SUCCESS": today_stats["success"],
                "FAILURES": today_stats["failures"],
            },
            "last": {
                "LAST BILLS COUNT": obj.bill_count
                or "-", 
                "LAST BILLS": f'{obj.start_bill_no or ""} - {obj.end_bill_no or ""}',
                "LAST STATUS": BillingStatus(obj.status).name.upper(),
                "LAST TIME": f'{obj.start_time.strftime("%H:%M:%S") if obj.start_time else "-"}',
                "LAST REJECTED": orders_qs.filter(place_order=False).count(),
                "LAST PENDING": orders_qs.filter(
                    place_order=True, creditlock=False
                ).count(),
            },
            "bill_counts": {
                "rejected": orders_qs.filter(place_order=False).count(),
                "pending": orders_qs.filter(place_order=True, creditlock=False).count(),
                "creditlock": orders_qs.filter(
                    place_order=True, creditlock=True
                ).count(),
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
