from django.template.defaultfilters import default
from bill.models import Bill
from rest_framework import serializers
from bill.models import Vehicle

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['id', 'name', 'vehicle_no']

class BillScanSerializer(serializers.ModelSerializer):
    vehicle = serializers.CharField(source='vehicle.name',allow_null=True,default=None)
    party = serializers.CharField(source='party_name')
    bill = serializers.CharField(source='bill_id')
    amt = serializers.CharField(source='bill_amt')
    loading_sheet = serializers.CharField(source='loading_sheet_id')
    class Meta: 
        model = Bill
        fields = ['bill', 'vehicle', 'vehicle_id', 'party','loading_time', 'delivery_time', 'loading_sheet','bill_date','amt','notes']