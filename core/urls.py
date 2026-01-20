from core.auth_api import get_companies
from django.urls import path
from .views import usersession_update
from rest_framework_simplejwt.views import TokenObtainPairView

urlpatterns = [
    path("login", TokenObtainPairView.as_view(), name="auth-login"),
    path("usersession", usersession_update, name="usersession"),
    path("companies", get_companies, name="companies"),
]
