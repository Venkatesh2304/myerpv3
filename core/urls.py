from core.views import trigger_ikea_login
from core.views import ikea_login
from django.urls import include
from core.auth_api import get_companies
from django.urls import path
from .views import usersession_update, ikea_health
from .assistant import assistant_chat, recent_failures
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.routers import DefaultRouter
from . import modelviews


router = DefaultRouter()
router.register(r'company', modelviews.CompanyModelViewSet)

urlpatterns = [
    path("login", TokenObtainPairView.as_view(), name="auth-login"),
    path("usersession", usersession_update, name="usersession"),
    path("companies", get_companies, name="companies"),
    path("ikea_login", ikea_login, name="ikea_login"),
    path("trigger_ikea_login", trigger_ikea_login, name="trigger_ikea_login"),
    path("ikea_health", ikea_health, name="ikea_health"),
    path("assistant/chat", assistant_chat, name="assistant-chat"),
    path("assistant/failures", recent_failures, name="assistant-failures"),
    path("api/assistant/chat", assistant_chat, name="api-assistant-chat"),
    path("api/assistant/failures", recent_failures, name="api-assistant-failures"),
    path("", include(router.urls)),
]
