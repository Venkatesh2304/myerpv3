from io import BytesIO
from PyPDF2 import PdfReader
from PyPDF2 import PdfWriter
from report.helper import pending_sheet_pdf
from report.models import StockReport
from report.models import OutstandingReport
from core.utils import get_media_url
from django.db.models import Value
from django.db.models.functions import Concat
from django.db.models.expressions import F
import datetime
from report.models import SalesRegisterReport
from report.models import BeatReport
from django.http import JsonResponse
from rest_framework.decorators import api_view
from custom.classes import Ikea
from core.models import Company
from report.models import *
from django.core.mail import EmailMessage

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
        label = Concat(F("party_name"),Value(" ("),F("party_id"),Value(")")),
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

def outstanding_report(company_id,date,beat_type):
    today = datetime.date.today()
    day = date.strftime("%A").lower()

    ikea = Ikea(company_id)
    company = Company.objects.get(name = company_id)
    OutstandingReport.update_db(ikea, company, EmptyArgs())
    base_qs = OutstandingReport.objects.filter(company_id = company_id)
    if beat_type == "wholesale" : base_qs = base_qs.filter(beat__contains="WHOLESALE") 
    if beat_type == "retail" : base_qs = base_qs.exclude(beat__contains="WHOLESALE") 

    def get_dataframe(qs):
        df = pd.DataFrame(list(qs.values()))
        df = df.rename(columns={"party_name":"party","inum":"bill"})
        df = df.astype({"bill_amt":int,"balance":int})
        df["days"] = df["bill_date"].apply(lambda x : (today - x).days)
        df = df[df["days"] < 100] #Filter out bills older than 100 days
        #Populate Phone numbers
        phone_map = PartyReport.objects.filter(company_id=company_id).values('code','phone')
        phone_map = {d["code"]:d["phone"] for d in phone_map}
        df["phone"] = df["party_id"].apply(lambda x : phone_map.get(x,"-"))
        df["coll_amt"] = (df["bill_amt"] - df["balance"]).round()
        df["salesman"] = df["salesman"].str.split("-").str[0].str.strip() #Clean salesman , remove salesman code
        df = df.sort_values("days",ascending=False)
        df = df[["salesman","beat","party","bill","bill_amt","coll_amt","balance","phone","days"]]
        return df

    pivot_fn = lambda df : pd.pivot_table(df,index=["salesman","beat","party","bill"],values=["bill_amt","coll_amt","balance","days","phone"],aggfunc = "first")[['bill_amt','coll_amt','balance',"days","phone"]] # type: ignore
    
    today_beats = BeatReport.objects.filter(company_id = company_id,days__contains = day).values_list("name",flat=True)
    today_outstanding = get_dataframe(base_qs.filter(beat__in = today_beats))
    outstanding_greater_than_21 = today_outstanding[today_outstanding.days >= 21]
    today_beat_outstanding = pivot_fn(outstanding_greater_than_21)

    all_outstanding = get_dataframe(base_qs)
    outstanding_greater_than_28 = pivot_fn(all_outstanding[all_outstanding.days >= 28])
    return today_beat_outstanding,outstanding_greater_than_28,all_outstanding
    
@api_view(["POST"])
def outstanding_report_view(request):
    today = datetime.date.today()
    company_id = request.data.get("company")
    date = request.data.get("date",today.strftime("%Y-%m-%d"))
    beat_type = request.data.get("beat_type")
    date = datetime.datetime.strptime(date,"%Y-%m-%d").date()
    today_beat_outstanding,outstanding_greater_than_28,all_outstanding = outstanding_report(company_id,date,beat_type)
    company_dir = os.path.join(settings.MEDIA_ROOT, "report", company_id)
    os.makedirs(company_dir, exist_ok=True)
    OUTSTANDING_REPORT_FILE = os.path.join(company_dir,"outstanding.xlsx")
    with pd.ExcelWriter(open(OUTSTANDING_REPORT_FILE,"wb+"), engine='xlsxwriter') as writer:
        today_beat_outstanding.to_excel(writer,sheet_name="21 Days")
        outstanding_greater_than_28.to_excel(writer,sheet_name="28 Days")
        all_outstanding.to_excel(writer,sheet_name="ALL BILLS",index=False)

    return JsonResponse({"status":"success", "filepath": get_media_url(OUTSTANDING_REPORT_FILE)})

@api_view(["POST"])
def stock_report(request) : 
    companies = request.user.companies.all()
    dfs = {}
    for company in companies :
        i =  Ikea(company.pk)
        StockReport.update_db(i,company,EmptyArgs())
        qs = StockReport.objects.filter(company_id = company.pk, godown = "MAIN GODOWN").values("stock_id","name","mrp","qty")
        df = pd.DataFrame(qs)
        df = df.groupby(["stock_id","name","mrp"]).agg({"qty":"sum"}).reset_index()
        df = df.sort_values("mrp",ascending=False)
        dfs[company.pk] = df

    #All Companies
    qs  = StockReport.objects.filter(company__in = list(companies), godown = "MAIN GODOWN").values("company_id","stock_id","name","mrp","qty")
    df = pd.DataFrame(qs)
    df = df.pivot_table(index=["stock_id","name","mrp"],columns="company_id",values=["qty"],aggfunc={"qty":"sum"},margins=True,margins_name="Total")
    df = df.iloc[:-1, :]
    df = df.sort_values("mrp",ascending=False)
    # df["total"] = df.sum(axis=1)    

    user_dir = os.path.join(settings.MEDIA_ROOT, "report", request.user.pk)
    os.makedirs(user_dir, exist_ok=True)
    STOCK_REPORT_FILE = os.path.join(user_dir,"stock_report.xlsx")
    with pd.ExcelWriter(open(STOCK_REPORT_FILE,"wb+"), engine='xlsxwriter') as writer:
        df.to_excel(writer,sheet_name="All")
        for company_id, df in dfs.items() :
            df.to_excel(writer,sheet_name=company_id,index=False)
            
    return JsonResponse({"status":"success", "filepath": get_media_url(STOCK_REPORT_FILE)})

@api_view(["POST"])
def stock_ageing_report(request) : 
    companies = request.user.companies.all()
    days = int(request.data.get("days"))
    dfs = {}
    for company in companies :
        i =  Ikea(company.pk)
        tod = datetime.date.today()
        fromd = tod - datetime.timedelta(days = days)
        df = i.stock_movement_report(fromd,tod)
        df = df[df["Location"] == "MAIN GODOWN"]
        df = df.rename(columns = {"SKU7" : "code", #type: ignore
                                  "Product Name" : "name",
                                  "Open Stk in Units" : "opening_qty",
                                  "Total Out Units" : "out_qty",
                                  "Cl Stk Units" : "qty",
                                  "Closing Stock Value TUR * CL STK in Units" : "value"})
        df = df.groupby(["code","name"])[["opening_qty","out_qty","qty","value"]].sum().reset_index()
        df = df[ (df.opening_qty > 0) & (df.out_qty == 0) ] 
        df = df[["code","name","qty","value"]]
        dfs[company.pk] = df

    user_dir = os.path.join(settings.MEDIA_ROOT, "report", request.user.pk)
    os.makedirs(user_dir, exist_ok=True)
    STOCK_AGEING_REPORT_FILE = os.path.join(user_dir,"stock_ageing_report.xlsx")
    with pd.ExcelWriter(open(STOCK_AGEING_REPORT_FILE,"wb+"), engine='xlsxwriter') as writer:
        for company_id, df in dfs.items() :
            df.to_excel(writer,sheet_name=company_id,index=False)
            
    return JsonResponse({"status":"success", "filepath": get_media_url(STOCK_AGEING_REPORT_FILE)})

@api_view(["POST"])
def pending_sheet(request) :
    date = request.data.get("date")
    date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    company_id = request.data.get("company") 
    beat_ids = request.data.get("beat_ids")
    beat_names = BeatReport.objects.filter(beat_id__in = beat_ids,company_id = company_id).values("beat_id","name")
    beat_name_to_id = {d["name"]:d["beat_id"] for d in beat_names}

    ikea = Ikea(company_id)
    company = Company.objects.get(name = company_id)
    OutstandingReport.update_db(ikea, company, EmptyArgs())

    qs = OutstandingReport.objects.filter(company_id = company_id,beat__in = list(beat_name_to_id.keys()))
    df = pd.DataFrame(qs.values("party_name","bill_date","salesman","inum","bill_amt","balance","beat"))
    df["days"] = df["bill_date"].apply(lambda x : (date - x).days)
    df["bill_date"] = pd.to_datetime(df.bill_date)
    df["coll_amt"] = (df["bill_amt"] - df["balance"]).round()
    df = df[df["days"] > 0] #Filter Today Bills
    pdfs = [] 
    for beat_name , rows in df.groupby("beat") : 
        rows = rows.sort_values(by = ["party_name","days"],ascending=[True,False])
        salesman = rows.iloc[0]["salesman"]
        beat_id = beat_name_to_id[beat_name]
        sheet_no = "PS" + date.strftime("%d%m%y") + str(beat_id)
        bytesio = pending_sheet_pdf(rows , sheet_no ,  salesman , beat_name , date)
        pdfs.append(bytesio)
    
    writer = PdfWriter()
    for pdf in pdfs :
        reader = PdfReader(pdf)
        for page in reader.pages:
            writer.add_page(page)
        if len(reader.pages) % 2 != 0:
            writer.add_blank_page()
    
    company_dir = os.path.join(settings.MEDIA_ROOT, "report", company_id)
    os.makedirs(company_dir, exist_ok=True)
    PENDING_SHEET_FILE = os.path.join(company_dir,"pending_sheet.pdf")
    writer.write(PENDING_SHEET_FILE)
    return JsonResponse({"status":"success", "filepath": get_media_url(PENDING_SHEET_FILE)})

@api_view(["GET"])
def mail_reports(request):
    today = datetime.date.today()
    company_id = request.query_params.get("company")
    company = Company.objects.get(name=company_id)
    msg = EmailMessage()
    msg.subject = f"Daily Report for {company.name.replace('_',' ').upper()} ({today.strftime('%d-%m-%Y')})"
    msg.to = [company.email]
    #Only bills > 28 days
    retail = outstanding_report(company.pk,today,"retail")[1]
    wholesale = outstanding_report(company.pk,today,"wholesale")[1]
    #Summary of 28 days bills
    summary = retail.reset_index().groupby("salesman").agg(
                        { "bill":"count" , "balance":"sum" , "days" : "max"})[["bill","balance","days"]].reset_index()
    summary = summary.sort_values("bill",ascending=False)
    summary.columns = ["Salesman", "Bill Count", "Total Balance", "Max Days"]
    
    html_table = summary.to_html(index=False, classes="table table-striped", border=1, justify="center")
    html_table = html_table.replace('border="1"', 'style="border-collapse: collapse; width: 100%;"')
    html_table = html_table.replace('<th>', '<th style="border: 1px solid black; padding: 8px; background-color: #eee;">')
    html_table = html_table.replace('<td>', '<td style="border: 1px solid black; padding: 8px;">')
    
    msg.body = f"""
    <html>
    <body>
        <h3>Outstanding Summary</h3>
        {html_table}
    </body>
    </html>
    """
    msg.content_subtype = "html"
    
    bytesio = BytesIO()
    with pd.ExcelWriter(bytesio, engine='xlsxwriter') as writer:
        retail.to_excel(writer,sheet_name="Retail")
        wholesale.to_excel(writer,sheet_name="Wholesale")
    msg.attach("28_days.xlsx", bytesio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    msg.send()
    return JsonResponse({"status":"success"})
