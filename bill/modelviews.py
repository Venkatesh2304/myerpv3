#Create a billing process status model view set 
from custom.classes import Ikea
from core.models import Company
from rest_framework import viewsets,mixins
from bill.serializer import *
from bill.models import *
from rest_framework.response import Response
from django_filters import rest_framework as filters
from rest_framework.pagination import LimitOffsetPagination
from report.models import DateRangeArgs,SalesRegisterReport

class BillingViewSet(mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    queryset = Billing.objects.all()
    serializer_class = BillingSerializer
    
class BillViewSet(viewsets.ModelViewSet):
    class BillFilter(filters.FilterSet):
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        date = filters.DateFilter(field_name='bill_date', lookup_expr='exact')
        is_printed = filters.BooleanFilter(method='filter_is_printed')
        salesman = filters.CharFilter(method='filter_salesman')
        beat_type = filters.CharFilter(method='filter_beat')
        class Meta:
            model = Bill
            fields = []

        def filter_is_printed(self, queryset, name, is_printed):
            return queryset.filter(print_time__isnull=(not is_printed))

        def filter_salesman(self, queryset, name, salesman):
            beats = list(BeatReport.objects.filter(salesman_name = salesman).values_list("name",flat=True).distinct())
            return queryset.filter(beat__in = beats)

        def filter_beat(self, queryset, name, beat_type):
            if beat_type == "retail" : 
                queryset = queryset.exclude(beat__contains = "WHOLESALE")
            elif beat_type == "wholesale" :
                queryset = queryset.filter(beat__contains = "WHOLESALE")
            return queryset

    def list(self, request, *args, **kwargs):
        company_id = request.query_params.get("company")
        company = Company.objects.get(name = company_id)
        date = request.query_params.get("date")
        if date :
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        else :
            raise Exception("Date is required For Bill")
        if SalesRegisterReport.get_oldness(company) > datetime.timedelta(minutes=5) :
            date_args = DateRangeArgs(fromd=date, tod=date)
            ikea = Ikea(company.pk)
            try:
                SalesRegisterReport.update_db(ikea,company,date_args)
            except Exception as e:
                print("Exception in SalesRegisterReport Sync From OrderListView :",e)
            Bill.sync_with_salesregister(company,fromd = date_args.fromd,tod = date_args.tod)
        return super().list(request, *args, **kwargs)

    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    filterset_class = BillFilter
    ordering = ["bill_id"]

class Pagination(LimitOffsetPagination):
    default_limit = 300
