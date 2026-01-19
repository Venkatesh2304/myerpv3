
from collections import defaultdict
from core.models import Company
from django.http.response import JsonResponse
from core.models import UserSession
from rest_framework.decorators import api_view

@api_view(["GET","POST"])
def usersession_update(request):
    if request.method == "GET":
        company = request.query_params.get("company")
        users = [request.user.pk , company]
        sessions = UserSession.objects.filter(user__in=users).values("pk","key", "username", "password")
        data = {}
        for s in sessions:
            key = s["key"]
            if key in data : 
                raise Exception(f"Key already exists {key} and entry {data[key]}")
            data[key] = {"id": s["pk"],
                         "username": s["username"],
                         "password": s["password"]}
        return JsonResponse(data)

    # POST
    usersession_id = request.data.get("id")
    new_username = request.data.get("username")
    new_password = request.data.get("password")

    session = UserSession.objects.get(pk = usersession_id)
    session.username = new_username
    session.password = new_password
    session.cookies = []
    session.save(update_fields=["username", "password","cookies"])

    return JsonResponse({"status": "updated", "id": session.pk, "user": session.user})