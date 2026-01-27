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

    other_vehicle = ""
    if scan_type == "delivery" : 
        bill = bills[0]
        if bill.loading_time is None:
            return Response({'status': 'error', 'message': 'Bill not loaded in any vehicle'})
        if bill.vehicle != vehicle :
           other_vehicle = bill.vehicle.name

    if scan_type == "load" : 
        updated_count = qs.update(vehicle_id=vehicle_id, loading_time=current_time)
    if scan_type == "delivery" : 
        updated_count = qs.update(delivery_time=current_time)

    bills = qs.values_list("bill_id", flat=True)
    return Response({'status': 'success', 'bills': list(bills) , 'other_vehicle': other_vehicle})

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

@api_view(['GET'])
def scan_summary(request):
    company_id = request.query_params.get('company')    
    today = datetime.date.today()
    # Last 3 days: yesterday, day before yesterday, day before before yesterday
    dates = [today - datetime.timedelta(days=i) for i in range(1, 4)]
    
    summary = {}
    for filter_key,date_type in {"bill_date":"bill_date","loading_time__date":"loading_date"}.items():
        date_type_summary = []
        for date in dates:
            qs = Bill.objects.filter(company_id=company_id, **{filter_key:date}).exclude(beat__contains="WHOLESALE").filter(loading_sheet_id__isnull=True)
            not_loaded = qs.filter(loading_time__isnull=True).count()
            loaded = qs.filter(loading_time__isnull=False).count()
            delivered = qs.filter(delivery_time__isnull=False).count()
            not_delivered = qs.filter(loading_time__isnull=False,delivery_time__isnull=True).count()
            date_type_summary.append({
                'date': date.strftime('%Y-%m-%d'),
                'not_loaded': not_loaded,
                'loaded': loaded,
                'delivered': delivered,
                'not_delivered': not_delivered
            })
        summary[date_type] = date_type_summary

    return Response({'status': 'success', 'summary': summary})