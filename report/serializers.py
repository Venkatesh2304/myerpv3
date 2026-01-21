from report.models import BeatReport
import datetime
from rest_framework import serializers
from report.models import OutstandingReport

class OutstandingReportSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    days = serializers.SerializerMethodField()
    bill = serializers.SlugField(source="inum", read_only=True)
    party = serializers.SlugField(source="party_name", read_only=True)
    class Meta:
        model = OutstandingReport
        fields = ["balance", "bill" , "days","party"]
    
    def get_balance(self, obj):
        return round(abs(-obj.balance))
    
    def get_days(self,obj) : 
        return (datetime.date.today() - obj.bill_date).days

class BeatReportSerializer(serializers.ModelSerializer):
    salesman = serializers.SlugField(source="salesman_name", read_only=True)
    class Meta:
        model = BeatReport
        fields = ["beat_id", "name","salesman", "days","plg"]