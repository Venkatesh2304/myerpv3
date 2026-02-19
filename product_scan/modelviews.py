from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import SalesScan
from .serializers import SalesScanSummarySerializer, SalesScanDetailSerializer
from custom.classes import Ikea

class SalesScanPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 25

class SalesScanViewSet(viewsets.ModelViewSet):
    queryset = SalesScan.objects.all().order_by('-created_at')
    pagination_class = SalesScanPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return SalesScanSummarySerializer
        return SalesScanDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return super().get_queryset().filter(company__in=user.companies.all())
        return super().get_queryset().none()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            self._update_unposted_bills(page)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        self._update_unposted_bills(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def _update_unposted_bills(self, bills):
        for bill in bills:
            if not bill.is_posted:
                try:
                    ikea = Ikea(bill.company_id)
                    bill_data = ikea.retrive_bill(bill.bill_no)
                    if not bill_data or 'billingProductMasterVOList' not in bill_data:
                        continue
                    
                    bill.update_from_bill_data(bill_data)
                except Exception as e:
                    print(f"Error updating bill {bill.bill_no}: {e}")
                    continue
