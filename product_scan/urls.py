from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import modelviews

router = DefaultRouter()
router.register(r'sales_scan', modelviews.SalesScanViewSet)

urlpatterns = [
    path('sales_scan_id/', views.sales_scan_id),
    path('sales_box/', views.scan_sales_box),
    path('sales_scan_summary/', views.sales_scan_summary),
    path('sales_scan_mismatch/', views.sales_scan_mismatch),
    path('', include(router.urls)),
]
