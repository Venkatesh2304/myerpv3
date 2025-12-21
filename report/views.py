from django.db.models.expressions import F
import datetime
from report.models import SalesRegisterReport
from report.models import BeatReport
from django.http import JsonResponse
from rest_framework.decorators import api_view
from custom.classes import Ikea
from core.models import Company
from report.models import *

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
    beat = request.query_params.get('beat','')

    if not company:
        return JsonResponse({"error": "Company is required"}, status=400)
    
    if not party_id:
        return JsonResponse({"error": "Party Id is required"}, status=400)
        
    try :
        party_name = PartyReport.objects.get(company_id=company, code=party_id).name
    except :
        return JsonResponse({"error": "Party not found"}, status=400)
    
    qs = BillAgeingReport.objects.filter(company_id=company, party_name=party_name).values()
    bills = list(qs)
    if beat : 
        bill_numbers = [d["inum"] for d in bills]
        beat_bills = SalesRegisterReport.objects.filter(company_id=company,inum__in = bill_numbers,beat = beat,type = "sales").values_list("inum",flat=True)
        bills = [d for d in bills if d["inum"] in beat_bills]
        
    all_values = [int(d["bill_amt"]) for d in bills]
    collected_bills = [d for d in bills if d["collected"]]
    bills = [ {"name" : d["inum"] , "amt": int(d["bill_amt"]), "days": d["days"] ,
                                   "collected": d["collected"] } for d in bills ]
    
    #Average Bill Value
    avg_value = sum(all_values) / len(all_values) if all_values else 0
    #Weighted average
    avg_days = sum([d["days"] * d["bill_amt"] for d in collected_bills]) / sum([d["bill_amt"] for d in collected_bills]) if collected_bills else 0
    #Average Monthly Value
    avg_monthly = sum(all_values) / 6 if all_values else 0

    return JsonResponse({
        "avg_days": round(avg_days),
        "avg_value": round(avg_value),
        "avg_monthly": round(avg_monthly),
        "bills": bills
    })

@api_view(["GET"])
def sync_reports(request):
    company_id = request.query_params.get("company")
    reports_param = request.query_params.get("reports", "")
    
    if not company_id:
        return JsonResponse({"error": "Company is required"}, status=400)
        
    try:
        company = Company.objects.get(name=company_id)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    reports = [r.strip() for r in reports_param.split(",") if r.strip()]
    
    if not reports:
        return JsonResponse({"error": "No reports specified"}, status=400)

    ikea = Ikea(company_id)
    results = {}
    
    today = datetime.date.today()
    
    report_handlers = {
        "party": (PartyReport, EmptyArgs()),
        "beat": (BeatReport, EmptyArgs()),
        "bill_ageing": (BillAgeingReport, EmptyArgs()),
        "outstanding": (OutstandingReport, EmptyArgs()),
        "salesregister": (SalesRegisterReport, DateRangeArgs(fromd=today - datetime.timedelta(days=30), tod=today)),
        "collection": (CollectionReport, DateRangeArgs(fromd=today - datetime.timedelta(days=15), tod=today)),
    }

    for report_name in reports:
        if report_name not in report_handlers:
            results[report_name] = "Unknown report"
            continue
            
        model, args = report_handlers[report_name]
        try:
            inserted_rows = model.update_db(ikea, company, args)
            results[report_name] = f"Success: {inserted_rows} rows inserted"
        except Exception as e:
            results[report_name] = f"Error: {str(e)}"
            
    return JsonResponse(results)
