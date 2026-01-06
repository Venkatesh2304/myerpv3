from rest_framework import viewsets
from django_filters import rest_framework as filters
from report.models import OutstandingReport
from report.serializers import OutstandingReportSerializer

class OutstandingReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OutstandingReport.objects.all()
    serializer_class = OutstandingReportSerializer
    ordering = ['bill_date']
    
    class OutstandingFilter(filters.FilterSet):
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        party = filters.CharFilter(field_name='party_id', lookup_expr='exact')
        
        class Meta:
            model = OutstandingReport
            fields = ['company', 'beat', 'party','inum']

    filterset_class = OutstandingFilter
