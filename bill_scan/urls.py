from bill_scan.views import upload_company_eway
from bill_scan.views import push_impact
from bill_scan.views import upload_vehicle_eway
from bill_scan.views import delivery_applicable
from bill_scan.views import download_scan_pdf
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import scan_bill, scan_summary
from .modelviews import VehicleViewSet
from .modelviews import BillScanViewSet

router = DefaultRouter()
router.register(r'vehicle', VehicleViewSet)
router.register(r'bill_scan', BillScanViewSet,basename="bill_scan")

urlpatterns = [
    path('', include(router.urls)),
    path('scan_bill/', scan_bill, name='scan_bill'),
    path('download_scan_pdf/', download_scan_pdf, name='download_scan_pdf'),
    path('scan_summary/', scan_summary, name='scan_summary'),
    path('delivery_applicable/', delivery_applicable, name='delivery_applicable'),
    path('upload_vehicle_eway/', upload_vehicle_eway, name='upload_vehicle_eway'),
    path('upload_company_eway/', upload_company_eway, name='upload_company_eway'),
    path('push_impact/', push_impact, name='push_impact'),
]
