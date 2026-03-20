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
    path('anomaly_analysis/', views.anomaly_analysis),
    path('barcode/', views.barcode_view),
    path('video_tasks/', views.get_video_tasks),
    path('video_upload/', views.upload_scan_video),
    path('video_fail/', views.fail_video_task),
    path('video_process/', views.get_processed_video),
    path('', include(router.urls)),
]
