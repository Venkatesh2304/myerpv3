from django.urls import path
import gst.api as api

urlpatterns = [
    path("einvoice/reload", api.einvoice_reload, name="einvoice-reload"),
    path("einvoice/stats", api.einvoice_stats, name="einvoice-stats"),
    path("einvoice/file", api.file_einvoice, name="einvoice-file"),
    path("einvoice/excel", api.einvoice_excel, name="einvoice-excel"),
    path("einvoice/pdf", api.einvoice_pdf, name="einvoice-pdf"),
    path("gst/generate", api.generate_gst_return, name="generate-gst-return"),
    path("gst/summary", api.gst_summary, name="gst-summary"),
    path("gst/json", api.gst_json, name="gst-json"),
    path("gst/upload", api.upload_gst_return, name="upload-gst-return"),
    path("gst/download", api.download_gst_return, name="download-gst-return"),
    path("custom/captcha", api.get_captcha, name="captcha"),
    path("custom/login", api.captcha_login, name="login"),
]
