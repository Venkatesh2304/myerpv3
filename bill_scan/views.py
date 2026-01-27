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

    loaded_vehicle = ""
    if scan_type == "delivery" : 
        bill = bills[0]
        if bill.loading_time is None:
            return Response({'status': 'error', 'message': 'Bill not loaded in any vehicle'})
        loaded_vehicle = bill.vehicle.name

    update_fields = {}
    
    if scan_type == "load" : 
        update_fields["vehicle_id"] = vehicle_id
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
    print(qs.count())
    bills = qs.values_list("bill_id", flat=True)
    pdf_buffer = generate_bill_list_pdf(bills, vehicle.name, today, columns=6)
    company_dir = os.path.join(settings.MEDIA_ROOT, "bill_scan", company.pk)
    os.makedirs(company_dir, exist_ok=True)
    BILL_SCAN_FILE = os.path.join(company_dir,"bill_scan.pdf")
    with open(BILL_SCAN_FILE, "wb+") as f:
        f.write(pdf_buffer.getvalue())
    return Response({'status': 'success',  'filepath': get_media_url(BILL_SCAN_FILE)})

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
    dates = [today - datetime.timedelta(days=i) for i in range(1, 4)]
    
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