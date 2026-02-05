import datetime
import calendar
import os
import subprocess
from io import BytesIO
import pandas as pd
from django.http import JsonResponse
from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework.decorators import api_view

from core.models import Company
from core.utils import get_media_url
from custom.classes import Ikea, Billing
from erp.erp_import import GstFilingImport
import erp.models as erp_models
from report.models import *
from report.views import outstanding_report

@api_view(["GET"])
def mail_reports(request):
    today = datetime.date.today()
    company_id = request.query_params.get("company")
    if not company_id:
        return JsonResponse({"error": "Company is required"}, status=400)
        
    company = Company.objects.get(name=company_id)
    msg = EmailMessage()
    msg.subject = f"Daily Report for {company.name.replace('_',' ').upper()} ({today.strftime('%d-%m-%Y')})"
    msg.to = company.emails
    
    # Only bills > 28 days
    retail = outstanding_report(company.pk, today, "retail")[1]
    wholesale = outstanding_report(company.pk, today, "wholesale")[1]
    
    # Summary of 28 days bills
    summary = retail.reset_index().groupby("salesman").agg(
                        { "bill":"count" , "balance":"sum" , "days" : "max"})[["bill","balance","days"]].reset_index()
    summary = summary.sort_values("bill", ascending=False)
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
        retail.to_excel(writer, sheet_name="Retail")
        wholesale.to_excel(writer, sheet_name="Wholesale")
    msg.attach("28_days.xlsx", bytesio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    msg.send()
    return JsonResponse({"status":"success"})

@api_view(["POST"])
def mail_bills(request):
    month = request.data.get("month")
    year = request.data.get("year")
    company_id = request.data.get("company")
    force_download = request.data.get("force_download", False)

    if not month or not year:
        return JsonResponse({"error": "month and year are required"}, status=400)
    
    if not company_id:
        return JsonResponse({"error": "Company is required"}, status=400)

    try:
        month = int(month)
        year = int(year)
        _, last_day = calendar.monthrange(year, month)
        fromd = datetime.date(year, month, 1)
        tod = datetime.date(year, month, last_day)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid month or year"}, status=400)
    
    # Base directory for the company
    base_dir = os.path.join(settings.MEDIA_ROOT, "bills", company_id, "month_wise")
    month_str = f"{month:02d}"
    year_str = str(year)
    
    date_dir = os.path.join(base_dir, year_str, month_str)
    os.makedirs(date_dir, exist_ok=True)
    
    dates = []
    curr = fromd
    while curr <= tod:
        dates.append(curr)
        curr += datetime.timedelta(days=1)
    
    results = {}
    i = Billing(company_id)

    for date in dates: 
        day_str = date.strftime("%Y-%m-%d")
        file_path = os.path.join(date_dir, f"{day_str}.pdf")
        
        if os.path.exists(file_path) and not force_download:
            results[day_str] = f"{date}: Skipped (Already exists)"
            continue
        try:
            reports = SalesRegisterReport.objects.filter(date=date, company_id=company_id, type="sales").order_by("inum")
            if not reports.exists():
                results[day_str] = f"{date}: No bills found"
                continue
            
            first_report = reports.first()
            last_report = reports.last()
            
            if not first_report or not last_report: continue

            min_bill = first_report.inum
            max_bill = last_report.inum
            
            durl = ""
            for attempt in range(3):
                try:
                    durl = i.get_bill_durl(min_bill, max_bill, "pdf", timeout=300)
                    if durl: break
                except Exception as e:
                    print(f"Attempt {attempt+1} failed for {date}: {e}")
            
            if not durl:
                results[day_str] = f"{date}: Failed - Empty Durl or Timeout"
                continue

            bytesio = i.fetch_durl_content(durl)
            
            with open(file_path, "wb+") as f:
                f.write(bytesio.getvalue())
                
            results[day_str] = f"{date}: Success ({min_bill} to {max_bill})"
        except Exception as e:
            print(e)
            results[day_str] = f"{date}: Failed - {str(e)}"
    
    company_name = company_id.replace('_',' ').upper()
    month_name = calendar.month_name[month]
    
    zip_filename = f"bills_{company_id}_{year}_{month_str}.7z"
    zip_dir = os.path.join(base_dir, "archives")
    os.makedirs(zip_dir, exist_ok=True)
    zip_filepath = os.path.join(zip_dir, zip_filename)
    
    if os.path.exists(zip_filepath):
        os.remove(zip_filepath)

    if not os.listdir(date_dir):
         results["zip_error"] = "Target directory for zip is empty (no bills downloaded?)"
         return JsonResponse(results)

    cmd = [
        "7z", "a", "-t7z", "-m0=lzma2", "-mx=9", "-md=16m", "-mmt=1", "-ms=on",
        zip_filepath, date_dir
    ]
    
    try:
        subprocess.run(cmd, check=True)
        company = Company.objects.get(name=company_id)
        msg = EmailMessage()
        msg.subject = f"Bills for {company_name} : {month_name}, {year}"
        msg.to = company.emails

        zip_url = f"http://65.1.147.8:5000/{get_media_url(zip_filepath).lstrip('/')}"
        
        html_content = f"""
        <html>
        <body>
            <p><strong>Company:</strong> {company_name}</p>
            <p><strong>Month:</strong> {month_name}, {year}</p>
            <p><strong>Link:</strong>{zip_url}</p>
        </body>
        </html>
        """
        
        msg.body = html_content
        msg.content_subtype = "html"
        msg.send()
        results["email"] = "Sent successfully"
        
    except Exception as e:
        results["zip_email_error"] = str(e)

    print(results)
    return JsonResponse(results)

@api_view(["POST"])
def monthly_gst_import(request):
    month = request.data.get("month")
    year = request.data.get("year")
    company_id = request.data.get("company")
    force = request.data.get("force", False)

    
    try:
        month = int(month)
        year = int(year)
        fromd = datetime.date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        tod = datetime.date(year, month, last_day)
        period = fromd.strftime("%m%Y")
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid month or year"}, status=400)
        
    GST_PERIOD_FILTER = {
        "devaki_urban" : lambda qs : qs.exclude(type = "damage", party_id  = "P150") 
    }

    company = Company.objects.get(name=company_id)
    if not force : 
        if erp_models.Sales.objects.filter(company_id=company_id,gst_period=period).exists() : 
            return JsonResponse({"status" : "success", "message" : "GST already imported for this period"})

    status = None
    message = None
    
    args_dict = {
        DateRangeArgs: DateRangeArgs(fromd=fromd, tod=tod),
        EmptyArgs: EmptyArgs(),
    }

    try:
        print(f"Processing GST for Company: {company.name} for Period: {period}")
        GstFilingImport.run(company=company, args_dict=args_dict)
        qs = erp_models.Sales.objects.filter(type__in=company.gst_types, date__gte=fromd, date__lte=tod)
        if company.name in GST_PERIOD_FILTER:
            qs = GST_PERIOD_FILTER[company.name](qs)
        qs.update(gst_period=period)
        status = "success"
        message = "GST imported successfully"
    except Exception as e:
        status = "error"
        message = str(e)
        print(f"Error processing {company.name}: {e}")

    #Send email to company
    try:
        msg = EmailMessage()
        msg.subject = f"GST - Ikea Import  for {company.name} : {period}"
        msg.to = company.emails
        html_content = f"""
        <html>
        <body>
            <p><strong>Status:</strong> {status}</p>
            <p><strong>Message:</strong> {message}</p>
            <p>Website: http://65.1.147.8:8000</p>
        </body>
        </html>
        """
        msg.body = html_content
        msg.content_subtype = "html"
        msg.send()
    except Exception as e:
        print(f"Error sending email: {e}")

    return JsonResponse({"status": status, "message": message})

@api_view(["POST"])
def beat_export(request):
    company_id = request.data.get("company")
    if not company_id:
        return JsonResponse({"error": "Company is required"}, status=400)

    try:
        ikea = Ikea(company_id)
        fromd = datetime.date.today()
        if 14 <= fromd.day <= 20: 
             tod = fromd.replace(day=20)
        else:
             tod = fromd + datetime.timedelta(days=6)
             
        ikea.beat_export(fromd, tod)
        return JsonResponse({"status": "Success", "fromd": fromd, "tod": tod})
    except Exception as e:
        print(e)
        return JsonResponse({"error": str(e)}, status=500)
