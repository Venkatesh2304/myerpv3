from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import modelviews

router = DefaultRouter()
router.register(r'outstanding', modelviews.OutstandingReportViewSet)

urlpatterns = [
    path("salesman/", views.salesman_names, name="salesman_names"),
    path("party/", views.party_names, name="party_names"),
    path("party_credibility/", views.party_credibility, name="party_credibility"),
    path("", include(router.urls)),
]
