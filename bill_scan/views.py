import datetime
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from bill.models import Vehicle, Bill
from .serializers import VehicleSerializer
import datetime
from django.utils import timezone

@api_view(['GET', 'POST'])
def vehicle_bills(request):
    if request.method == 'GET':
        vehicle_id = int(request.query_params.get('vehicle'))
        date_str = request.query_params.get('date')        
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()            
        bills = Bill.objects.filter(vehicle_id=vehicle_id, loading_time__date=date)
        bills = bills.values('bill_id', 'loading_sheet_id')
        inums = [ bill["loading_sheet_id"] or bill["bill_id"] for bill in bills ]
        return Response(list(inums))

    elif request.method == 'POST':
        vehicle_id = request.data.get('vehicle')
        bill = request.data.get('bill')
        vehicle = Vehicle.objects.get(id=vehicle_id)
        current_time = datetime.datetime.now()
        qs = Bill.objects.filter(company = vehicle.company) 
        if bill.startswith("SM"):
            qs = qs.filter(loading_sheet_id=bill)
        else:
            qs = qs.filter(bill_id=bill)
        updated_count = qs.update(vehicle_id=vehicle_id, loading_time=current_time)
        return Response({'status': 'success', 'updated': updated_count})
