from django.urls import include
from django.urls import path
from . import views
from . import modelviews
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'load_summary', modelviews.LoadSummaryViewSet, basename="load_summary")
router.register(r'load_detail', modelviews.LoadDetailViewSet, basename="load_detail")
urlpatterns = [ 
    path("upload_purchase_invoice/", views.upload_purchase_invoice, name="upload_purchase_invoice"),
    path("get_last_load/", views.get_last_load, name="get_last_load"),
    path("box/", views.box, name="box"),
    path("download_load_summary/", views.download_load_summary, name="download_load_summary"),
    path("", include(router.urls)),
]


 