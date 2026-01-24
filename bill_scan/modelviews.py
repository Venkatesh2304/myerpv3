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
    