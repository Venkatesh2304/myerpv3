from core.auth_api import get_companies
from django.urls import path
from .auth_api import login as auth_login, logout as auth_logout, me as auth_me
from .views import usersession_update

urlpatterns = [
    path("login", auth_login, name="auth-login"),
    path("logout", auth_logout, name="auth-logout"),
    path("me", auth_me, name="auth-me"),
    path("usersession", usersession_update, name="usersession"),
    path("companies", get_companies, name="companies"),
]
