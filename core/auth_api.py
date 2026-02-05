from core.models import Company
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import JsonResponse
from core.models import UserSession


@api_view(["GET"])
def get_companies(request):
    companies = request.user.companies.values_list("name", flat=True)
    return JsonResponse(list(companies), safe=False)