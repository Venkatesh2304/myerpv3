from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import modelviews

router = DefaultRouter()
router.register(r'outstanding', modelviews.OutstandingReportViewSet)
router.register(r'beat', modelviews.BeatReportViewSet)

urlpatterns = [
    path("salesman/", views.salesman_names, name="salesman_names"),
    path("party/", views.party_names, name="party_names"),
    path("party_credibility/", views.party_credibility, name="party_credibility"),
    path("sync_reports/", views.sync_reports, name="sync_reports"),
    path("outstanding_report/", views.outstanding_report_view, name="outstanding_report"),
    path("stock_report/", views.stock_report, name="stock_report"),
    path("stock_ageing_report/", views.stock_ageing_report, name="stock_ageing_report"),
    path("pending_sheet/", views.pending_sheet, name="pending_sheet"),
    path("mail_reports/", views.mail_reports, name="mail_reports"),
    path("", include(router.urls)),
]
