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
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True,blank=True)
    status = models.IntegerField()
    error = models.TextField(max_length=100000,null=True,blank=True)
    start_bill_no = models.TextField(max_length=10,null=True,blank=True)
    end_bill_no = models.TextField(max_length=10,null=True,blank=True)
    bill_count = models.IntegerField(null=True,blank=True,default=0)
    date = models.DateField()
    automatic = models.BooleanField(default=False,db_default=False)

    def __str__(self) -> str:
        print("x",self.start_time)
        return str(self.start_time.strftime("%d/%m/%y %H:%M:%S"))
     
class PushedCollection(models.Model) : 
    billing = models.ForeignKey(Billing,on_delete=models.CASCADE,related_name="collection")
    party_code = models.TextField(max_length=30)

class Orders(CompanyModel) : 
    billing = models.ForeignKey(Billing,on_delete=models.CASCADE,related_name="orders",null=True,blank=True)
    order_no = models.TextField(max_length=60,primary_key=True)
    salesman = models.TextField(max_length=30)
    date = 	models.DateField()
    type = models.TextField(max_length=15,choices=(("SH","Shikhar"),("SE","Salesman")),blank=True,null=True)
    
    party_id = models.TextField(max_length=30)
    party_hul_code = models.TextField(max_length=40)
    party_name = models.TextField(max_length=100)
    party = models.ForeignObject(
            report.PartyReport,
            on_delete=models.DO_NOTHING,
            null=True,
            from_fields=("company", "party_id"),
            to_fields=("company", "code"),
    )

    beat = models.TextField(max_length=30)
    place_order = models.BooleanField(default=False,db_default=False)
    force_order = models.BooleanField(default=False,db_default=False)
    creditlock = models.BooleanField(default=False,db_default=False)
    release = models.BooleanField(default=False,db_default=False)
    delete_order = models.BooleanField(default=False,db_default=False)

    ##Expressions 
    @property
    def bill_value(self) : 
        return round( sum([ p.quantity * p.rate for p in self.products.all() ])   , 2 )

    @property
    def allocated_value(self) : 
        return round( sum([ p.allocated * p.rate for p in self.products.all() ]) or 0  , 2 )

    @property
    def partial(self) : 
        return bool( (self.products.filter(allocated = 0).count() and self.products.filter(allocated__gt = 0).count()) )  

    @property
    def pending_value(self) : 
        return round(self.bill_value() - self.allocated_value(),2)
    
    @property
    def OS(self) :
        today = datetime.date.today()
        bills = [  f"{round(bill.balance)}*{(today - bill.bill_date).days}"
                     for bill in report.OutstandingReport.objects.filter(company = self.company,party_id = self.party_id,beat = self.beat).all() ]
        return "/ ".join(bills) or "-"
    
    @property
    def coll(self) : 
        today = datetime.date.today() 
        coll = [  f"{round(coll.amt or 0)}*{(today - coll.bill_date).days}"
                 for coll in report.CollectionReport.objects.filter(company = self.company,party_name = self.party_name,date = today).all() ]
        return "/ ".join(coll) or "-"
    
    @property
    def phone(self) : 
        phone = "-"
        try: 
            phone = self.party.phone or "-"
        except PartyReport.DoesNotExist :
            pass 
        return phone

    @property
    def lines(self) : 
        return len([ product for product in self.products.all() if product.allocated != product.quantity])
    
    @property
    def partial(self) :
        return self.partial()

    class Meta : 
        verbose_name = 'Orders'
        verbose_name_plural = 'Billing'

class OrderProducts(models.Model) : 
    order = models.ForeignKey(Orders,on_delete=models.CASCADE,related_name="products")
    product = models.TextField(max_length=100)
    batch = models.TextField(max_length=10,default="00000",db_default="00000")
    quantity =  models.IntegerField()
    allocated =  models.IntegerField()
    rate = models.FloatField()
    reason = models.TextField(max_length=50)
    
    def __str__(self) -> str:
         return self.product
    
    class Meta:
        unique_together = ('order', 'product','batch')

class BillStatistics(CompanyModel) : 
    type = models.TextField(max_length=30)	
    count = models.TextField(max_length=30) 

class BillingProcessStatus(models.Model) : 
    billing = models.ForeignKey(Billing,on_delete=models.CASCADE,related_name="process_status",null=True,db_constraint=False)
    status = models.IntegerField(default=0)
    process = models.TextField(max_length=30)	
    time = models.FloatField(null=True,blank=True) 

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