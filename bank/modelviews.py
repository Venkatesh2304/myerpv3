from django.db.models.aggregates import Sum
from django.db.models.expressions import Subquery
from django.db.models.expressions import F
from bank.models import BankCollection
from django.db.models.fields import BooleanField
from django.db.models.expressions import When
from django.db.models.expressions import Case
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
        deposit_date = filters.DateFilter(field_name='deposit_date', lookup_expr='exact')
        party = filters.CharFilter(field_name='party_id', lookup_expr='exact')

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
    
    def perform_update(self, serializer):
        obj = serializer.save()
        obj.add_event("saved",by = self.request.user.pk,message = f"Mapped to {obj.type}")
        obj.save()

    class BankFilter(filters.FilterSet):
        fromd = filters.DateFilter(field_name='date', lookup_expr='gte')
        tod = filters.DateFilter(field_name='date', lookup_expr='lte')
        type = filters.CharFilter(field_name='type', lookup_expr='exact')
        bank = filters.CharFilter(field_name='bank', lookup_expr='exact')
        company = filters.CharFilter(method='filter_company')
        status = filters.CharFilter(method='filter_status')
        class Meta:
            model = BankStatement
            fields = []

        def filter_status(self, queryset, name, status):
            company_id = self.data.get("company")
            #This month first day
            today = datetime.date.today()
            cutoff_date = datetime.date(today.year, today.month, 1)
            if status == "not_pushed" : 
                queryset = queryset.filter(date__gte = cutoff_date,company_id = company_id).filter(type__in = ["neft","cheque"]).exclude(cheque_status = "bounced")

                #Find statement ids which dont match the ikea collection amount
                ALLOWED_DIFF = 100
                statement_ids = queryset.filter(statement_id__isnull = False).values_list("statement_id",flat=True)
                ikea_collection = list(CollectionReport.objects.filter(bank_entry_id__in = statement_ids, company_id = company_id).values('bank_entry_id').annotate(
                    total_amt=Sum('amt')
                ).values("bank_entry_id","total_amt"))
                ikea_collection = { i["bank_entry_id"] : i["total_amt"] for i in ikea_collection }
                not_pushed_statement_ids = [] #Contains partial also (ideally this should be empty only failures)
                for obj in queryset : 
                    if abs(obj.amt - ikea_collection.get(obj.statement_id,0)) > ALLOWED_DIFF :
                        not_pushed_statement_ids.append(obj.statement_id)

                queryset = queryset.filter(Q(statement_id__in = not_pushed_statement_ids) | Q(statement_id__isnull = True))
                return queryset
            elif status == "not_saved" :
                return queryset.filter(type__isnull = True,date__gte = cutoff_date)
            return queryset

        def filter_company(self, queryset, name, company_id):
            return queryset.filter(bank__companies=company_id) #.filter(Q(company_id = company_id) | Q(company_id__isnull = True))
            
    filterset_class = BankFilter

class BankViewSet(viewsets.ModelViewSet):#
    queryset = Bank.objects.all()
    serializer_class = BankNameSerializer
    pagination_class = None
    
    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(companies=company_id)
        return queryset
