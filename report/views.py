from django.db.models.expressions import F
import datetime
from report.models import SalesRegisterReport
from report.models import BeatReport
from django.http import JsonResponse
from rest_framework.decorators import api_view

@api_view(["GET"])
def salesman_names(request):
    company = request.query_params.get("company")
    if not company:
        return JsonResponse({"error": "Company is required"}, status=400)
    
    salesman = list(BeatReport.objects.filter(company_id=company).values_list("salesman_name", flat=True).distinct())
    return JsonResponse(salesman, safe=False)

@api_view(["GET"])
def party_names(request) :
    company = request.query_params.get("company")
    if not company:
        return JsonResponse({"error": "Company is required"}, status=400)
    
    qs = SalesRegisterReport.objects.filter(date__gte = datetime.date.today() - datetime.timedelta(weeks=16),company_id = company)
    beat = request.query_params.get('beat')
    if beat : qs = qs.filter(beat = beat)
    parties = qs.annotate(
        label = F("party_name"),
        value = F("party_id")
    ).values("label","value").distinct() #warning
    return JsonResponse(list(parties),safe=False)
