from django.urls import include
from core.auth_api import get_companies
from django.urls import path
from .views import usersession_update
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.routers import DefaultRouter
from . import modelviews

router = DefaultRouter()
router.register(r'company', modelviews.CompanyModelViewSet)

urlpatterns = [
    path("login", TokenObtainPairView.as_view(), name="auth-login"),
    path("usersession", usersession_update, name="usersession"),
    path("companies", get_companies, name="companies"),
    path("", include(router.urls)),
]
