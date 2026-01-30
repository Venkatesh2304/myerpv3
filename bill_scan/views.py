from dateutil.utils import today
from core.models import Company
from django.http.response import JsonResponse
from django.db.models import Max
from django.db.models import Min
from collections import defaultdict
from core.utils import get_media_url
from django.conf import settings
import datetime
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from bill.models import Vehicle, Bill
from .serializers import VehicleSerializer
from bill_scan.pdf_helper import generate_bill_list_pdf
import os
from custom.classes import Ikea, Einvoice
from bill_scan.eway import eway_df_to_json
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import pandas as pd

@api_view(['POST'])
def scan_bill(request):
    vehicle_id = request.data.get('vehicle')
    bill = request.data.get('bill')
    notes = request.data.get('notes','')
    scan_type = request.data.get('type') #load or delivery
    vehicle = Vehicle.objects.get(id=vehicle_id)
    current_time = datetime.datetime.now()
    qs = Bill.objects.filter(company = vehicle.company)
    if bill.startswith("SM"):
        qs = qs.filter(loading_sheet_id=bill)
    else:
        qs = qs.filter(bill_id=bill)
    
    bills = list(qs.all())
    if len(bills) == 0 : 
        return Response({'status': 'error', 'message': 'Bill not found'})

    bill = bills[0]
    loaded_vehicle = ""
    if scan_type == "delivery" : 
        if bill.loading_time is None:
            return Response({'status': 'error', 'message': 'Bill not loaded in any vehicle'})
        loaded_vehicle = bill.vehicle.name

    update_fields = {}
    
    if scan_type == "load" : 
        update_fields["vehicle_id"] = vehicle_id
        if (bill.loading_time is None) or (bill.vehicle_id != vehicle_id) or (bill.loading_time.date() != current_time.date()) : 
            update_fields["loading_time"] = current_time
    if scan_type == "delivery" : 
        update_fields["delivery_time"] = current_time
    
    qs.update(**update_fields)
    if notes != "" : 
        for bill in qs.all() :
            bill.add_notes(notes)
            bill.save()
             
    bills = qs.values_list("bill_id", flat=True)
    return Response({'status': 'success', 'bills': list(bills) , 'loaded_vehicle': loaded_vehicle})

@api_view(["POST"])
def download_scan_pdf(request):
    vehicle_id = request.data.get('vehicle')
    scan_type = request.data.get('type') #load or delivery
    vehicle = Vehicle.objects.get(id=vehicle_id)
    company = vehicle.company
    today = datetime.date.today()
    qs = Bill.objects.filter(company = company)
    if scan_type == "load" : 
        qs = qs.filter(vehicle = vehicle, loading_time__date=today)
    if scan_type == "delivery" : 
        qs = qs.filter(vehicle = vehicle, delivery_time__date=today)
    bills = qs.values_list("bill_id", flat=True)
    pdf_buffer = generate_bill_list_pdf(bills, vehicle.name, today, columns=6)
    company_dir = os.path.join(settings.MEDIA_ROOT, "bill_scan", company.pk)
    os.makedirs(company_dir, exist_ok=True)
    BILL_SCAN_FILE = os.path.join(company_dir,f"{vehicle.name}_{scan_type}_{today.strftime('%d_%m_%y')}.pdf")
    with open(BILL_SCAN_FILE, "wb+") as f:
        f.write(pdf_buffer.getvalue())
    return Response({'status': 'success',  'filepath': get_media_url(BILL_SCAN_FILE), 'scan_bills': len(bills)})

@api_view(["POST"])
def delivery_applicable(request):
    bill_id = request.data.get('bill')
    company = request.data.get('company')
    notes = request.data.get('notes')
    delivery_applicable = request.data.get('delivery_applicable')
    bill = Bill.objects.get(bill_id=bill_id,company_id=company)
    bill.delivery_applicable = delivery_applicable
    if notes != "" : 
        bill.add_notes(notes)
    bill.save()
    return Response({'status': 'success'})

@api_view(['GET'])
def scan_summary(request):
    company_id = request.query_params.get('company')    
    today = datetime.date.today()
    # Last 3 days: yesterday, day before yesterday, day before before yesterday
    dates = [today - datetime.timedelta(days=i) for i in range(1, 5)]
    
    summary = defaultdict(list)
    company_qs = Bill.objects.filter(company_id=company_id)
    for date in dates : 
        qs = company_qs.filter(bill_date = date)
        total = qs.count()
        qs = qs.exclude(beat__contains="WHOLESALE").filter(loading_sheet_id__isnull=True,delivery_applicable=True)
        not_loaded = qs.filter(loading_time__isnull=True).count()
        loaded = qs.filter(loading_time__isnull=False).count()
        not_applicable = total - loaded - not_loaded
        summary["bill_date"].append({
            "date":date.strftime('%Y-%m-%d'),
            "not_loaded":not_loaded,
            "loaded":loaded,
            "not_applicable":not_applicable,
            "total":total,
        })
        
    for date in dates : 
        qs = company_qs.filter(loading_time__date = date)
        loaded = qs.count()
        delivered = qs.filter(delivery_time__isnull=False).count()
        not_delivered = loaded - delivered
        summary["loading_date"].append({
            "date":date.strftime('%Y-%m-%d'),
            "loaded":loaded,
            "not_delivered":not_delivered,
            "delivered":delivered,
        })

    return Response({'status': 'success', 'summary': summary})

@api_view(['POST'])
def push_impact(request):
    vehicle_id = request.data.get('vehicle')
    vehicle = Vehicle.objects.get(id=vehicle_id)
    company = vehicle.company
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    i = Ikea(company.pk)

    #Get beat_vehicle_counts  for yesterday bills
    qs = Bill.objects.filter(bill_date = yesterday)
    beat_vehicle_counts = defaultdict(lambda: defaultdict(int))
    beat_total_counts = defaultdict(int)
    for bill in qs.all() :
        #Skip bills with loading sheet for counts/stats
        if bill.loading_sheet_id is not None : continue
        if bill.vehicle :
            beat_vehicle_counts[bill.beat][bill.vehicle_id] += 1
        beat_total_counts[bill.beat] += 1
    
    vehicle_bills = defaultdict(list)
    current_vehicle_bills = Bill.objects.filter(vehicle = vehicle, loading_time__date=today).values_list('bill_id', flat=True)
    vehicle_bills[vehicle_id] = list(current_vehicle_bills)
    for bill in qs.all() :
        if (bill.vehicle is None) or (bill.vehicle.name_on_impact is None) :
            #Pick the vehicle with max count for that beat
            vehicle_counts = beat_vehicle_counts[bill.beat]
            if len(vehicle_counts) == 0 :
                continue
            max_vehicle_id = max(vehicle_counts, key=vehicle_counts.get) #type: ignore
            max_vehicle_count = vehicle_counts.get(max_vehicle_id,0)
            total_count = beat_total_counts[bill.beat]
            if (max_vehicle_count >= total_count * 0.4) or (len(vehicle_counts) > 1) or (max_vehicle_count >= 4):
                vehicle_bills[max_vehicle_id].append(bill.bill_id)
                print("Pushing bill", bill.bill_id, bill.beat, "to vehicle", max_vehicle_id)

    pending_bills = []
    bills_count = 0
    print("Current Vehicle count (All bill dates loading today):", len(current_vehicle_bills))
    for vehicle_id, bills in vehicle_bills.items() :
        bills_count += len(bills)
        vehicle = Vehicle.objects.get(id=vehicle_id)
        print("Pushing bills for vehicle", vehicle.name, "count", len(bills))
        df = i.push_impact(fromd=today - datetime.timedelta(days=3),tod=today,bills=bills,vehicle_name = vehicle.name_on_impact)
        if df is not None : 
            df = df[(~df["Beat Name"].str.contains("WHOLESALE")) & (df["Bill Date"] == yesterday.strftime('%Y-%m-%d'))]
            pending_bills = df["BillNo"].values.tolist()
        print("Pending bills", len(pending_bills))

    return Response({'status': 'success','pushed': bills_count , 'pending': len(pending_bills)})


class EinvoiceLoginException(Exception) :
    pass

def upload_eway_bills(qs,company,default_vehicle_no = None) -> pd.DataFrame:
    einv = Einvoice(company.organization.pk)
    if einv.is_logged_in() == False  : 
        raise EinvoiceLoginException("E-way login failed")

    ikea = Ikea(company.pk)
    bill_ids = list(qs.values_list('bill_id', flat=True))
    
    if bill_ids : 
        # Download eway excel
        dates = qs.aggregate(fromd=Min('bill_date'),tod=Max('bill_date'))
        df_eway = ikea.eway_excel(dates['fromd'], dates['tod'], bill_ids)
        bill_to_vehicle_no = qs.values_list('bill_id', 'vehicle__vehicle_no')
        bill_to_vehicle_no = dict(bill_to_vehicle_no)
        # Convert to JSON
        json_output = eway_df_to_json(df_eway, lambda series : series.apply(lambda x : bill_to_vehicle_no.get(x) or default_vehicle_no), 
                                               lambda series: series.apply(lambda x: 3))
        # Upload to einvoice (eway upload)
        try:
            df = einv.upload_eway_bill(json_output)
            print(df)
        except Exception as e:
            print(f"E-way upload failed: {e}")
        
    df = einv.get_eway_bills()
    for _, row in df.iterrows():
        bill_no = str(row['Doc.No'])
        ewb_no = str(row['EWB No'])
        Bill.objects.filter(company=company, bill_id=bill_no).update(ewb_no=ewb_no)
    return df

@api_view(['POST'])
def upload_company_eway(request):
    company_id = request.data.get('company')
    bill_date = datetime.datetime.strptime(request.data.get('date'), '%Y-%m-%d').date()
    if bill_date >= datetime.date.today() : 
        return JsonResponse("Bill date cannot be today", status=400)
    company = Company.objects.get(pk=company_id)
    vehicle = Vehicle.objects.filter(company_id=company_id).first()
    if vehicle is None : 
        return JsonResponse("Vehicle not found", status=404)
    base_qs = Bill.objects.filter(company=company, bill_date = bill_date).exclude(beat__contains = "WHOLESALE")
    qs = base_qs.filter(ewb_no__isnull=True)
    if qs.count() > 0 : 
        try :
            df = upload_eway_bills(qs,company,vehicle.vehicle_no)
        except EinvoiceLoginException :
            return JsonResponse({"key": "einvoice"}, status=501)
    rows = list(base_qs.values('bill_date','bill_id','party_name','ewb_no'))
    df = pd.DataFrame(rows)
    company_dir = os.path.join(settings.MEDIA_ROOT, "company", company.pk)
    os.makedirs(company_dir, exist_ok=True)
    filepath = os.path.join(company_dir, f"eway_{bill_date.strftime('%d_%m_%y')}.xlsx")
    df.to_excel(filepath, index=False)
    return JsonResponse({"status": "success","filepath": get_media_url(filepath)})

@api_view(['POST'])
def upload_vehicle_eway(request):
    vehicle_id = request.data.get('vehicle')
    vehicle = Vehicle.objects.get(id=vehicle_id)
    company = vehicle.company
    today = datetime.date.today()
    
    base_qs = Bill.objects.filter(company=company, vehicle=vehicle, loading_time__date=today)
    qs = base_qs.filter(ewb_no__isnull=True)
    bill_ids = list(qs.values_list('bill_id', flat=True))

    try :
        df = upload_eway_bills(qs,company)
    except EinvoiceLoginException :
        return JsonResponse({"key": "einvoice"}, status=501)

    # Construct PDF for the table
    df = df[df['Doc.No'].isin(bill_ids)]
    pdf_df = df[["EWB No","EWB Date","Supply Type","Doc.No","Doc.Date"]]
    company_dir = os.path.join(settings.MEDIA_ROOT, "vehicle", company.pk)
    os.makedirs(company_dir, exist_ok=True)
    filepath = os.path.join(company_dir, f"{vehicle.name}_eway_{today.strftime('%d_%m_%y')}.pdf")
    
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    
    header_text = f"<b>Vehicle:</b> {vehicle.name} | <b>Vehicle No:</b> {vehicle.vehicle_no}"
    elements.append(Paragraph(header_text, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    data = [pdf_df.columns.tolist()] + pdf_df.values.tolist()
    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')
    ]))
    elements.append(table)
    doc.build(elements)
    
    # success count should include the previous eway filed bills count also
    total_success = base_qs.filter(ewb_no__isnull=False).count()
    total_failed = base_qs.filter(ewb_no__isnull=True).count()

    return Response({
        'status': 'success',
        'filepath': get_media_url(filepath),
        'filed': total_success,
        'not_filed': total_failed
    })