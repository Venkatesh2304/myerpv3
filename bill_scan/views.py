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

    if scan_type == "delivery" : 
        bill = bills[0]
        if bill.loading_time is None:
            return Response({'status': 'error', 'message': 'Bill not loaded in any vehicle'})
        if bill.vehicle != vehicle :
            return Response({'status': 'error', 'message': f'Bill loaded in {bill.vehicle.name}'})
        qs = qs.filter(vehicle = vehicle, loading_time__isnull=False)

    if scan_type == "load" : 
        updated_count = qs.update(vehicle_id=vehicle_id, loading_time=current_time)
    if scan_type == "delivery" : 
        updated_count = qs.update(vehicle_id=vehicle_id, delivery_time=current_time)

    bills = qs.values_list("bill_id", flat=True)
    return Response({'status': 'success', 'bills': list(bills)})

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