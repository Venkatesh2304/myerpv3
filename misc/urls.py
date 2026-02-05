from django.urls import path
from . import views

urlpatterns = [
    path("mail_reports/", views.mail_reports, name="mail_reports"),
    path("mail_bills/", views.mail_bills, name="mail_bills"),
    path("monthly_gst_import/", views.monthly_gst_import, name="monthly_gst_import"),
    path("beat_export/", views.beat_export, name="beat_export"),
]
