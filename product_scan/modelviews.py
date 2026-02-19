from rest_framework import viewsets
from rest_framework.response import Response
from .models import SalesScan
from .serializers import SalesScanSummarySerializer, SalesScanDetailSerializer
from custom.classes import Ikea
from bill.modelviews import Pagination
from django.core.cache import cache

class SalesScanViewSet(viewsets.ModelViewSet):
    queryset = SalesScan.objects.all().order_by('-created_at')
    pagination_class = Pagination

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
            # Fresh fetch for the current page IDs to ensure DB state is reflected
            page_ids = [obj.id for obj in page]
            fresh_page = list(SalesScan.objects.filter(id__in=page_ids).order_by('-created_at'))
            serializer = self.get_serializer(fresh_page, many=True)
            return self.get_paginated_response(serializer.data)

        queryset_list = list(queryset)
        self._update_unposted_bills(queryset_list)
        # Fresh fetch for the whole filtered queryset
        ids = [obj.id for obj in queryset_list]
        fresh_queryset = SalesScan.objects.filter(id__in=ids).order_by('-created_at')
        serializer = self.get_serializer(fresh_queryset, many=True)
        return Response(serializer.data)

    def _update_unposted_bills(self, bills):
        user = self.request.user
        if not user.is_authenticated:
            return

        lock_key = f"update_bills_lock_{user.id}"
        # Use cache.add for an atomic lock (timeout 1 minutes to be safe)
        if not cache.add(lock_key, True, timeout=60):
            return
        try:
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
        finally:
            cache.delete(lock_key)
