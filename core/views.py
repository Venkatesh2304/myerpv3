from custom.classes import Ikea
from collections import defaultdict
from django.http.response import JsonResponse
from core.models import UserSession
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

@api_view(["GET","POST"])
@permission_classes([AllowAny])
def ikea_login(request):
    if request.method == "GET":
        #Get method gets the username,password,dbName(config) and url (config) from coreusersession
        company = request.GET.get("company")
        usersession = UserSession.objects.get(user=company, key="ikea")
        config:dict = usersession.config #type: ignore
        return JsonResponse({"username": usersession.username, "password": usersession.password, 
                              "dbName": config["dbName"], "url": config["home"]})
    if request.method == "POST":
        #POST Method Updates the cookies
        company = request.data.get("company")
        cookies = request.data.get("cookies")
        usersession = UserSession.objects.get(user=company, key="ikea")
        usersession.cookies = cookies
        usersession.save(update_fields=["cookies"])
        try :
            i = Ikea(company)
            is_logged_in = i.is_logged_in()
            return JsonResponse({"status": "success", "is_logged_in": is_logged_in})
        except Exception as e :
            return JsonResponse({"status": "error", "is_logged_in": False, "error": str(e)})
    

@api_view(["GET","POST"])
def usersession_update(request):
    if request.method == "GET":
        company = request.query_params.get("company")
        users = [request.user.organization.pk , company]
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