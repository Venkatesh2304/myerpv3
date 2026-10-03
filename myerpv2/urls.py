from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static

api_patterns = [
    path("", include("core.urls")),
    path("", include("gst.urls")),
    path("", include("bill.urls")),
    path("", include("printing.urls")),
    path("", include("report.urls")),
    path("", include("bank.urls")),
    path("", include("load.urls")),
    path("", include("bill_scan.urls")),
    path("", include("ledger.urls")),
    path("", include("product_scan.urls")),
    path("", include("misc.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_patterns)),
    path("", include(api_patterns)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True)
