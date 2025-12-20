from report.models import PartyReport
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

@api_view(["GET"])
def party_credibility(request):
    from report.models import BillAgeingReport
    from django.db.models import Avg

    company = request.query_params.get("company")
    party_id = request.query_params.get("party_id")

    if not company:
        return JsonResponse({"error": "Company is required"}, status=400)
    
    if not party_id:
        return JsonResponse({"error": "Party Id is required"}, status=400)
        
    try :
        party_name = PartyReport.objects.get(company_id=company, code=party_id).name
    except :
        return JsonResponse({"error": "Party not found"}, status=400)
    
    qs = BillAgeingReport.objects.filter(company_id=company, party_name=party_name).values("bill_amt", "days", "collected")
    
    data = list(qs)
    
    all_values = [int(d["bill_amt"]) for d in data]
    collected_days = [d["days"] for d in data if d["collected"]]
    
    avg_value = sum(all_values) / len(all_values) if all_values else 0
    avg_days = sum(collected_days) / len(collected_days) if collected_days else 0

    return JsonResponse({
        "avg_days": round(avg_days),
        "avg_value": round(avg_value),
        "days": collected_days,
        "values": all_values
    })
