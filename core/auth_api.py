from core.models import Company
from django.contrib.auth import authenticate, login as dj_login, logout as dj_logout
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import JsonResponse
from core.models import UserSession

@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if not user:
        return Response({"ok": False, "error": "invalid_credentials"}, status=400)
    dj_login(request, user)
    return Response({"ok": True, "user": {"id": user.pk, "username": user.get_username()}})

@api_view(["POST"])
def logout(request):
    dj_logout(request)
    return Response({"ok": True})

@api_view(["GET"])
def me(request):
    u = request.user
    return Response({"authenticated": u.is_authenticated, "user": None if not u.is_authenticated else {"id": u.pk, "username": u.get_username()}})

@api_view(["GET","POST"])
def usersession_update(request):

    if request.method == "GET":
        sessions = UserSession.objects.all().values("key", "user", "username", "password")
        grouped = {}
        for s in sessions:
            k = s["key"]
            grouped.setdefault(k, []).append(
                {
                    "user": s["user"],
                    "username": s["username"],
                    "password": s["password"],
                }
            )
        return JsonResponse(grouped)

    # POST
    key = request.data.get("key")
    user = request.data.get("user")
    new_username = request.data.get("username")
    new_password = request.data.get("password")

    session = UserSession.objects.get(key=key, user=user)
    session.username = new_username
    session.password = new_password
    session.save(update_fields=["username", "password"])

    return JsonResponse({"status": "updated", "key": session.key, "user": session.user})


@api_view(["GET"])
def get_companies(request):
    companies = Company.objects.filter(user = request.user).values_list("name",flat=True)
    return JsonResponse(list(companies), safe=False)