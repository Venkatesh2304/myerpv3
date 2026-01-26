from bill.modelviews import Pagination
from bill_scan.serializers import BillScanSerializer
from bill.models import Bill
from rest_framework import viewsets
from bill.models import Vehicle
from django_filters import rest_framework as filters
from .serializers import VehicleSerializer



class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

    class VehicleFilter(filters.FilterSet):
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        class Meta:
            model = Vehicle
            fields = ['company']
    filterset_class = VehicleFilter
    
class BillScanViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillScanSerializer
    pagination_class = Pagination
    
    class BillFilter(filters.FilterSet):
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        vehicle = filters.CharFilter(field_name='vehicle_id', lookup_expr='exact')
        type = filters.CharFilter(field_name='type', method='filter_by_type')
        bill_date = filters.DateFilter(field_name='bill_date', lookup_expr='exact')
        loading_date = filters.DateFilter(field_name='loading_time', lookup_expr='date')
        delivery_date = filters.DateFilter(field_name='delivery_time', lookup_expr='date')
        party = filters.CharFilter(field_name='party_id', lookup_expr='exact')
        bill = filters.CharFilter(field_name='bill_id', lookup_expr='contains')
        is_loading_sheet = filters.BooleanFilter(field_name='loading_sheet_id', lookup_expr='isnull',exclude=True)
        class Meta:
            model = Bill
            fields = ['company','vehicle','type','bill_date','loading_date','delivery_date','party','bill','is_loading_sheet']
        
        def filter_by_type(self, queryset, name, value):
            if value == "not_delivered" : 
                return queryset.filter(delivery_time__isnull=True,loading_time__isnull=False)
            if value == "not_loaded" : 
                return queryset.filter(loading_time__isnull=True)
            if value == "loaded" : 
                return queryset.filter(loading_time__isnull=False)
            if value == "delivered" : 
                return queryset.filter(delivery_time__isnull=False)
            return queryset

    filterset_class = BillFilter