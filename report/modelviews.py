
from report.serializers import BeatReportSerializer
from report.models import BeatReport
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
        inum = filters.CharFilter(field_name='inum', lookup_expr='iexact')
        
        class Meta:
            model = OutstandingReport
            fields = ['company', 'beat', 'party','inum']

    filterset_class = OutstandingFilter



class BeatReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BeatReport.objects.all()
    serializer_class = BeatReportSerializer
    ordering = ['salesman_name']
    
    class BeatFilter(filters.FilterSet):
        company = filters.CharFilter(field_name='company_id', lookup_expr='exact')
        date = filters.DateFilter(method="filter_date")
        beat_type = filters.CharFilter(method="filter_beat_type")
        
        class Meta:
            model = BeatReport
            fields = ['company', 'date']
        
        def filter_date(self, queryset, name, date):
            day = date.strftime("%A").lower()
            return queryset.filter(days__contains=day)

        def filter_beat_type(self, queryset, name, beat_type):
            if beat_type == "retail" : 
                return queryset.exclude(name__contains="WHOLESALE")
            elif beat_type == "wholesale" :
                return queryset.filter(name__contains="WHOLESALE")
            else : 
                return queryset

    filterset_class = BeatFilter

