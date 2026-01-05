from django.db.models.expressions import OuterRef,Exists
from report.models import CollectionReport
from django.db.models.aggregates import Count
from bank.serializer import BankSerializer, BankNameSerializer
from bank.models import BankStatement, Bank
import datetime
from bill.modelviews import Pagination
from bank.serializer import ChequeSerializer
from bank.models import ChequeDeposit
from rest_framework import viewsets
from django_filters import rest_framework as filters
from django.db.models import Q

class ChequeViewSet(viewsets.ModelViewSet):
    queryset = ChequeDeposit.objects.all()
    serializer_class = ChequeSerializer
    pagination_class = Pagination
    ordering = ["-id"]
    ordering_fields = ["id"]
    
    class ChequeFilter(filters.FilterSet):
        is_depositable = filters.BooleanFilter(method ='filter_is_depositable')
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        def filter_is_depositable(self, queryset, name, value):
            if value : 
                return queryset.filter(deposit_date__isnull = True,cheque_date__lte = datetime.date.today())
            return queryset

    filterset_class = ChequeFilter

class BankStatementViewSet(viewsets.ModelViewSet):
    queryset = BankStatement.objects.all()
    serializer_class = BankSerializer
    pagination_class = Pagination
    ordering = ["-date","-id"]
    
    class BankFilter(filters.FilterSet):
        date = filters.DateFilter(field_name='date', lookup_expr='exact')
        type = filters.CharFilter(field_name='type', lookup_expr='exact')
        bank = filters.CharFilter(field_name='bank', lookup_expr='exact')
        company = filters.CharFilter(field_name='bank__companies', lookup_expr='exact')
        status = filters.CharFilter(method='filter_status')
        class Meta:
            model = BankStatement
            fields = []

        def filter_status(self, queryset, name, status):
            cutoff_date = datetime.date.today() - datetime.timedelta(days=30)
            if status == "not_pushed" : 
                queryset = queryset.filter(date__gte = cutoff_date
                                       ).filter(type__in = ["neft","cheque"]).exclude(cheque_status = "bounced").filter()
                queryset = queryset.annotate(
                    has_ikea_collection=Exists(
                        CollectionReport.objects.filter(
                            bank_entry_id=OuterRef("statement_id"),
                            company_id=OuterRef("company_id")
                    ))
                ).filter(has_ikea_collection = False)
                return queryset
            elif status == "not_saved" : 
                return queryset.filter(type__isnull = True,date__gte = cutoff_date)
            return queryset
        

    filterset_class = BankFilter

class BankViewSet(viewsets.ModelViewSet):
    queryset = Bank.objects.all()
    serializer_class = BankNameSerializer
    pagination_class = None
    
    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(companies=company_id)
        return queryset
