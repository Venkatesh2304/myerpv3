from django.core.mail import send_mail
import json
from custom.classes import IkeaBank
from custom.classes import Ikea
from collections import defaultdict
from django.http.response import JsonResponse
from core.models import UserSession
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
import boto3

IKEA_CLASS_MAP = { 
    "ikea": Ikea,
    "ikea_bank": IkeaBank
}

@api_view(["GET","POST"])
@permission_classes([AllowAny])
def ikea_login(request):
    if request.method == "GET":
        #Get method gets the username,password,dbName(config) and url (config) from coreusersession
        company = request.GET.get("company")
        key = request.GET.get("key")
        usersession = UserSession.objects.get(user=company, key=key)
        config:dict = usersession.config #type: ignore
        return JsonResponse({"username": usersession.username, "password": usersession.password, 
                              "dbName": config["dbName"], "url": config["home"]})
    if request.method == "POST":
        #POST Method Updates the cookies
        company = request.data.get("company")
        key = request.data.get("key")
        cookies = request.data.get("cookies")
        print("For company", company, ", key", key, ", Got cookies:", cookies)
        usersession = UserSession.objects.get(user=company, key=key)
        usersession.cookies = cookies
        usersession.save(update_fields=["cookies"])
        try :
            i = IKEA_CLASS_MAP[key](company)
            is_logged_in = i.is_logged_in()
            return JsonResponse({"status": "success", "is_logged_in": is_logged_in})
        except Exception as e :
            return JsonResponse({"status": "error", "is_logged_in": False, "error": str(e)})
    
@api_view(["GET"])
@permission_classes([AllowAny])
def trigger_ikea_login(request):

    def get_not_logged_in_users():
        keys = ["ikea","ikea_bank"]
        not_logged_in = defaultdict(list)
        for key in keys:
            users = UserSession.objects.filter(key=key).values_list("user",flat=True)
            for user in users:
                try:
                    i = IKEA_CLASS_MAP[key](user)
                    is_logged_in = i.is_logged_in()
                    if not is_logged_in :
                        not_logged_in[key].append(user)
                except Exception as e :
                    not_logged_in[key].append(user)
        return not_logged_in
        
    trigger_login_users:dict[str,list[str]] = get_not_logged_in_users()
    if not trigger_login_users:
        return JsonResponse({"status": "success", "message": "All users are logged in"})
    
    print("Triggering login for users:", trigger_login_users)
    client = boto3.client('ecs', region_name='ap-south-1')
    response = client.run_task(
        cluster='ikeatoken',
        taskDefinition='IkeaToken',
        count=1,
        capacityProviderStrategy=[
            {
                'capacityProvider': 'FARGATE_SPOT',
                'weight': 1
            }
        ],
        networkConfiguration = {
            'awsvpcConfiguration': {
                'subnets': [
                    'subnet-045ce52845b1f856f', 
                    'subnet-06a27107a14f8d3d7', 
                    'subnet-0561f493ff9eaf27e'
                ],
                'securityGroups': ['sg-0d842ab2d4c70684c'],
                'assignPublicIp': 'ENABLED' 
            }
        },
        overrides={
            'containerOverrides': [
                {
                    'name': 'IkeaToken',
                    'environment': [
                        {'name': 'EVENT_PAYLOAD', 'value': json.dumps(trigger_login_users)},
                    ]
                }
            ]
        }
    )

    task_arn = response['tasks'][0]['taskArn']
    print(f"Task started! ARN: {task_arn}")
    print("Waiting for task to stop...")
    waiter = client.get_waiter('tasks_stopped')
    waiter.wait(
        cluster='ikeatoken',
        tasks=[task_arn],
        WaiterConfig={
            'Delay': 10,      # Check every 10 seconds
            'MaxAttempts': 20 # Stop waiting after 200 seconds
        }
    )
    print("Task stopped!")

    #Final check if the users are logged in
    failed_users = get_not_logged_in_users()
    print("Failed Login users:", failed_users)
    mail_body = "Failed Login users: " + str(failed_users) if failed_users else "All users are logged in"
    mail_subject = "Ikea Login Failed" if failed_users else "Ikea Login Success"
    send_mail(
        subject=mail_subject,
        message=mail_body,
        from_email="noreply@devaki.shop",
        recipient_list=["venkateshks2304@gmail.com"],
        fail_silently=False,
    )
    return JsonResponse({"status": "success", "failed_users": failed_users})
    
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

@api_view(["GET"])
@permission_classes([AllowAny])
def ikea_health(request):
    keys = ["ikea", "ikea_bank"]
    health_status = {
        "logged_in": [],
        "not_logged_in": []
    }
    
    for key in keys:
        sessions = UserSession.objects.filter(key=key)
        for session in sessions:
            try:
                i = IKEA_CLASS_MAP[key](session.user)
                if i.is_logged_in():
                    health_status["logged_in"].append(f"{key}: {session.user}")
                else:
                    health_status["not_logged_in"].append(f"{key}: {session.user}")
            except Exception as e:
                health_status["not_logged_in"].append(f"{key}: {session.user} (Error: {str(e)})")
    
    mail_body = f"IKEA Health Check Report:\n\n"
    mail_body += "Logged In:\n" + ("\n".join(health_status["logged_in"]) if health_status["logged_in"] else "None") + "\n\n"
    mail_body += "Not Logged In:\n" + ("\n".join(health_status["not_logged_in"]) if health_status["not_logged_in"] else "None")
    
    send_mail(
        subject="IKEA Health Check Report",
        message=mail_body,
        from_email="noreply@devaki.shop",
        recipient_list=["venkateshks2304@gmail.com"],
        fail_silently=False,
    )
    
    return JsonResponse({"status": "success", "health_status": health_status})
@permission_classes([AllowAny])
def ikea_health(request):
    keys = ["ikea", "ikea_bank"]
    health_status = {
        "logged_in": [],
        "not_logged_in": []
    }
    
    for key in keys:
        sessions = UserSession.objects.filter(key=key)
        for session in sessions:
            try:
                i = IKEA_CLASS_MAP[key](session.user)
                if i.is_logged_in():
                    health_status["logged_in"].append(f"{key}: {session.user}")
                else:
                    health_status["not_logged_in"].append(f"{key}: {session.user}")
            except Exception as e:
                health_status["not_logged_in"].append(f"{key}: {session.user} (Error: {str(e)})")
    
    mail_body = f"IKEA Health Check Report:\n\n"
    mail_body += "Logged In:\n" + ("\n".join(health_status["logged_in"]) if health_status["logged_in"] else "None") + "\n\n"
    mail_body += "Not Logged In:\n" + ("\n".join(health_status["not_logged_in"]) if health_status["not_logged_in"] else "None")
    
    send_mail(
        subject="IKEA Health Check Report",
        message=mail_body,
        from_email="noreply@devaki.shop",
        recipient_list=["venkateshks2304@gmail.com"],
        fail_silently=False,
    )
    
    return JsonResponse({"status": "success", "health_status": health_status})
