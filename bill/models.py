from report.models import BeatReport
from report.models import SalesRegisterReport
from report.models import PartyReport
from collections import defaultdict
import datetime
from django.db import models
import report.models as report
from core.models import CompanyModel

## Billing Models
class Billing(CompanyModel) : 
    company = models.ForeignKey("core.Company",on_delete=models.CASCADE)
    process = models.CharField(max_length=20,choices=(("getorder","Get Order"),("postorder","Post Order")))
    stop = models.BooleanField(default=False)
    ongoing = models.BooleanField(default=False)
    time = models.DateTimeField(auto_now=True)
    date = models.DateField(default=datetime.date.today)
    order_date = models.DateField(null=True,blank=True)
    order_hash = models.CharField(max_length=32,null=True,blank=True)
    market_order_data = models.JSONField(null=True,blank=True)
    last_bills = models.JSONField(default=list,blank=True)
    order_values = models.JSONField(default=dict,blank=True)
    user = models.CharField(max_length=100,null=True,blank=True)

    class Meta:
        unique_together = ('company', 'date')

    def __str__(self) -> str:
        return f"{self.company} - {self.date} - {self.process}"
     

## Bill/Print Models 
class SalesmanLoadingSheet(CompanyModel) : 
     inum = models.CharField(max_length=30)
     salesman = models.TextField(max_length=30)
     party = models.TextField(max_length=30,null=True,blank=True)
     beat = models.TextField(max_length=30)
     time = models.DateTimeField(auto_now_add=True)
     pk = models.CompositePrimaryKey("company","inum")
     
     @property
     def date(self) :
          return self.time.date()

class Vehicle(CompanyModel) : 
     name = models.CharField(max_length=30)
     vehicle_no = models.CharField(max_length=30)
     name_on_impact = models.CharField(max_length=30,null=True)
     pk = models.CompositePrimaryKey("company","name")

     def __str__(self):
          return self.name 

class Bill(CompanyModel) : 
    
    bill_id = models.TextField(max_length=40,null=False,blank=False)
    bill_date = models.DateField(null=True,blank=True)
    bill_amt = models.FloatField(null=True,blank=True)
    party_name = models.TextField(max_length=30,null=True,blank=True)
    party_id = models.TextField(max_length=30,null=True,blank=True)
    beat = models.TextField(max_length=30,null=True,blank=True)
    ctin = models.TextField(max_length=30,null=True,blank=True)
    
    print_time = models.DateTimeField(null=True,blank=True)
    print_type = models.TextField(max_length=20,choices=(("first_copy","First Copy"),("loading_sheet","Loading Sheet")),null=True,blank=True)
    is_reloaded = models.BooleanField(default=False,db_default=False)
    reason = models.TextField(max_length=100,null=True,blank=True)
    loading_sheet_id = models.TextField(max_length=30,null=True,blank=True)
    vehicle_id = models.TextField(max_length=30,null=True,blank=True)
    loading_time = models.DateTimeField(null=True,blank=True)
    delivered_time = models.DateTimeField(null=True,blank=True)
    irn = models.TextField(null=True,blank=True)
    delivered = models.BooleanField(null=True,blank=True)
    delivery_reason = models.TextField(choices=(("scanned","Scanned"),
                                                ("bill_with_shop","Bill With Shop"),
                                                ("cash_bill_success","Cash Bill (Collected Money)"),
                                                ("bill_return","Bill Return"),
                                                ("qrcode_not_found","QR Code Not Found"),
                                                ("others","Other Reason")),null=True,blank=True)
    plain_loading_sheet = models.BooleanField(db_default=False,default=False)
    cash_bill = models.BooleanField(default=False,db_default=False)

    class Meta :
        unique_together = ('company','bill_id')
    
    @property
    def salesman(self) :
        beat = BeatReport.objects.filter(name = self.beat, company_id = self.company_id).first()
        return beat.salesman_name if beat else None

    @classmethod
    def sync_with_salesregister(cls,company,fromd,tod) : 
        invs = SalesRegisterReport.objects.filter(company_id=company.pk,date__gte=fromd,date__lte=tod,type="sales").values("inum","date","party_id","beat","party_name","amt","ctin")
        cls.objects.bulk_create(
            [ cls(company_id=company.pk,bill_id=inv["inum"],bill_date=inv["date"],party_id = inv["party_id"],
                                beat = inv["beat"],party_name = inv["party_name"],bill_amt = inv["amt"], ctin = inv["ctin"]) for inv in invs ],
            ignore_conflicts=True
        )

class PartyCredit(CompanyModel):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE)
    party_id = models.CharField(max_length=30)
    bills = models.IntegerField(default=1)
    days = models.IntegerField(default=0)
    value = models.IntegerField(default=0)

    class Meta:
        unique_together = ('company', 'party_id')