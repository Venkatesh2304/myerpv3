from django.http import JsonResponse
from rest_framework.decorators import api_view
from core.models import Company
from .print import BillPrintingService

@api_view(["POST"])
def print_bills(request):
    company = Company.objects.get(pk=request.data["company"])
    service = BillPrintingService(company)
    response:dict = service.print_bills(request.data)
    if response.get("is_logged_in",True) == False:
        return JsonResponse({"key": "einvoice"}, status=501)
    if response["status"] == "error":
        return JsonResponse(response,status=409)
    return JsonResponse(response,status=200)
