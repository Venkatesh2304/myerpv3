from rest_framework.authentication import SessionAuthentication

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return

from rest_framework.authentication import BaseAuthentication
from django.conf import settings
from django.contrib.auth import get_user_model

class DevAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if settings.DEBUG:
            User = get_user_model()
            try:
                user = User.objects.get(username="devaki")
                return (user, None)
            except User.DoesNotExist:
                return None
        return None
