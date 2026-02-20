from rest_framework import viewsets
from rest_framework.response import Response
from .models import SalesScan
from .serializers import SalesScanSummarySerializer, SalesScanDetailSerializer
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from custom.classes import Ikea
from bill.modelviews import Pagination
from django.core.cache import cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import time
from report.models import SalesRegisterReport, DateRangeArgs
from collections import defaultdict

class SalesScanFilter(filters.FilterSet):
    scan_type = filters.CharFilter(method='filter_scan_type')

    class Meta:
        model = SalesScan
        fields = {
            'bill_date': ['exact', 'gte', 'lte'],
        }

    def filter_scan_type(self, queryset, name, value):
        if value == 'scanned':
            return queryset.exclude(
                Q(scanned_products=[]) | 
                Q(scanned_products=[{}]) | 
                Q(scanned_products__isnull=True)
            )
        elif value == 'not_scanned':
            return queryset.filter(
                Q(scanned_products=[]) | 
                Q(scanned_products=[{}]) | 
                Q(scanned_products__isnull=True)
            )
        return queryset

class SalesScanViewSet(viewsets.ModelViewSet):
    queryset = SalesScan.objects.all().order_by('-created_at')
    pagination_class = Pagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = SalesScanFilter

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
        user = self.request.user
        if not user.is_authenticated:
            return Response({"error": "Unauthorized"}, status=401)

        # 1. Sync and create placeholders (runs for all companies in parallel)
        ikea_map = self._process_parallel_salesregister_sync(user)
        
        # 2. Get fresh queryset after initialization
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        target_bills = page if page is not None else list(queryset)
        
        # 3. Update details for unposted bills (parallel across companies and bills)
        if target_bills:
            self._process_parallel_updates(target_bills, ikea_map)

        # 4. Fresh fetch for synchronization before serialization
        ids = [obj.id for obj in target_bills]
        fresh_data = SalesScan.objects.filter(id__in=ids).order_by('-created_at')
        
        if page is not None:
            serializer = self.get_serializer(fresh_data, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(fresh_data, many=True)
        return Response(serializer.data)

    def _process_parallel_salesregister_sync(self, user):
        lock_key = f"sync_scans_lock_{user.id}"
        if not cache.add(lock_key, True, timeout=120):
            return {}

        ikea_map = {}
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        date_args = DateRangeArgs(fromd=yesterday, tod=today)
        companies = list(user.companies.all())

        def sync_company(company):
            ikea_obj = None
            try:
                # Sync report if needed
                if SalesRegisterReport.get_oldness(company) > datetime.timedelta(minutes=10):
                    ikea_obj = Ikea(company.pk)
                    SalesRegisterReport.update_db(ikea_obj, company, date_args)
                
                # Check for and create missing placeholders
                bill_nos = SalesRegisterReport.objects.filter(
                    company=company, 
                    date__gte=yesterday
                ).values_list('inum', flat=True)
                
                for b_no in bill_nos:
                    SalesScan.objects.get_or_create(bill_no=b_no, company=company)
                    
            except Exception as e:
                print(f"Sync error for {company.name}: {e}")
            return company.pk, ikea_obj

        try:
            with ThreadPoolExecutor(max_workers=min(len(companies), 5)) as executor:
                results = executor.map(sync_company, companies)
                for comp_id, ikea_obj in results:
                    if ikea_obj:
                        ikea_map[comp_id] = ikea_obj
        finally:
            cache.delete(lock_key)
        
        return ikea_map

    def _process_parallel_updates(self, bills, ikea_map):
        user = self.request.user
        lock_key = f"update_bills_lock_{user.id}"
        if not cache.add(lock_key, True, timeout=120):
            return

        try:
            # Group bills by company
            company_groups = defaultdict(list)
            for b in bills:
                if not b.is_posted:
                    company_groups[b.company_id].append(b)

            if not company_groups:
                return

            def update_company_bills(comp_id, comp_bills):
                try:
                    ikea = ikea_map.get(comp_id) or Ikea(comp_id)
                    
                    def fetch_and_update(single_bill):
                        for attempt in range(2):
                            try:
                                data = ikea.retrive_bill(single_bill.bill_no)
                                if data and 'billingProductMasterVOList' in data:
                                    single_bill.update_from_bill_data(data)
                                    return True
                                time.sleep(1)
                            except Exception as e:
                                print(f"Fetch error {single_bill.bill_no}: {e}")
                        return False

                    # Within a company, fetch bills in parallel
                    with ThreadPoolExecutor(max_workers=min(len(comp_bills), 10)) as bill_executor:
                        list(bill_executor.map(fetch_and_update, comp_bills))
                except Exception as e:
                    print(f"Company update error {comp_id}: {e}")

            # Parallelize across companies
            with ThreadPoolExecutor(max_workers=min(len(company_groups), 4)) as company_executor:
                futures = [
                    company_executor.submit(update_company_bills, cid, cbills) 
                    for cid, cbills in company_groups.items()
                ]
                for future in as_completed(futures): # Wait for all companies
                    pass

        finally:
            cache.delete(lock_key)
