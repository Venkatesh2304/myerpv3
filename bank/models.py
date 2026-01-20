import datetime
from typing import Literal
from report.models import CollectionReport
from functools import cached_property
from report.models import OutstandingReport
from report.models import SalesRegisterReport
from report.models import PartyReport
from django.db.models.query_utils import Q
from django.db import models

class ChequeDeposit(models.Model) :
    RETAILER_BANK_CHOICES = ["KVB 650","SBI","CANARA","BARODA","UNION BANK","AXIS","HDFC","CENTRAL BANK","INDIAN BANK","IOB","ICICI","CUB","KOTAK","SYNDICATE","TMB","UNITED BANK","TCB","PGB"]
    company = models.ForeignKey("core.Company",on_delete=models.DO_NOTHING)
    party_id = models.CharField(max_length=15)
    bank = models.CharField(max_length=100, choices=zip(RETAILER_BANK_CHOICES,RETAILER_BANK_CHOICES))
    cheque_no = models.CharField(max_length=20)
    amt = models.FloatField()
    cheque_date = models.DateField()
    deposit_date = models.DateField(null=True,blank=True)
    entry_date = models.DateField(auto_now_add=True)
    party = models.ForeignObject(
            PartyReport,
            null=True,
            on_delete=models.DO_NOTHING,
            from_fields=("company_id", "party_id"),
            to_fields=("company_id", "code"),
    )
    
    def __str__(self) -> str:
         return f"CHQ: {self.cheque_no} - AMT: {self.amt} - {self.party.name}"

class BankCollection(models.Model) : 
    bill = models.CharField(max_length=15)
    cheque_entry = models.ForeignKey("bank.ChequeDeposit",related_name="collection",db_index=False,db_constraint=False,on_delete=models.CASCADE,null=True,blank=True)
    bank_entry = models.ForeignKey("bank.BankStatement",related_name="collection",db_index=False,db_constraint=False,on_delete=models.CASCADE,null=True,blank=True)
    amt = models.IntegerField()
    class Meta:
        unique_together = ('bill','cheque_entry', 'bank_entry')
    
    @property
    def balance(self):
        return int(OutstandingReport.objects.get(company_id = self.company,inum = self.bill).balance)
    
    @cached_property
    def company(self):
        return self.bank_entry.company_id if self.bank_entry else self.cheque_entry.company_id
    
    @property
    def party(self):
        party = SalesRegisterReport.objects.filter(company_id = self.company,inum = self.bill).first()
        return party.party_name if party else None
    
class Bank(models.Model):
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=[('sbi', 'SBI'), ('kvb', 'KVB')], default='sbi')
    account_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    companies = models.ManyToManyField("core.Company")
    
class BankStatement(models.Model) : 
    statement_id = models.CharField(max_length=15,null=True,blank=True)
    company = models.ForeignKey("core.Company",on_delete=models.DO_NOTHING,null=True,blank=True)
    date = models.DateField()
    idx = models.IntegerField()
    ref = models.TextField(max_length=200)
    desc = models.TextField(max_length=200)
    amt = models.IntegerField()
    bank = models.ForeignKey("bank.Bank",on_delete=models.DO_NOTHING)
    type = models.TextField(max_length=15,choices=(("cheque","Cheque"),("neft","NEFT"),("upi","UPI (IKEA)"),("cash_deposit","Cash Deposit"),("self_transfer","Self Transfer"),("others","Others")),null=True)
    cheque_entry = models.OneToOneField("bank.ChequeDeposit", on_delete=models.DO_NOTHING, null=True, blank=True, related_name='bank_entry')
    cheque_status = models.TextField(choices=(("passed","Passed"),("bounced","Bounced")),default="passed",db_default="passed",null=True,blank=True)
    events = models.JSONField(default=list)
    class Meta : 
        unique_together = ('date','idx','bank')
        verbose_name_plural = 'Bank'

    def __init__(self, *args, **kwargs) :
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs) :
        if self.type != "cheque" : 
            self.cheque_entry_id = None
        if self.company_id is None :
            self.statement_id = None
        super().save(*args, **kwargs)

    def add_event(self,type,message = "",by = None):
        event = {"type" : type,"message" : message,"by" : by,"time" : datetime.datetime.now().strftime("%d/%m/%y %H:%M")}
        self.events.insert(0,event)

    @property
    def status(self) : 
        if self.type is None : return "not_saved"
        if self.type in ["cheque","neft"] :
            if self.cheque_status and (self.cheque_status == "bounced") : 
                return "pushed"
            return self.pushed_status
        else : 
            return "not_applicable"

    @property
    def pushed_status(self)-> Literal["not_pushed","partially_pushed","pushed"] :
        if self.statement_id is None :  return "not_pushed"
        amts = self.ikea_collection.values_list("amt",flat=True)
        if len(amts) == 0 : return "not_pushed"
        elif abs(sum(amts) - self.amt) > 100 : return "partially_pushed"
        else : 
            return "pushed"

    @property
    def all_collection(self) :
        if self.type == "cheque" : 
            return BankCollection.objects.filter(cheque_entry__bank_entry = self.id)
        elif self.type == "neft" : 
            return BankCollection.objects.filter(bank_entry_id = self.id)
        else :
            return BankCollection.objects.none()

    @property
    def ikea_collection(self) :
        return CollectionReport.objects.filter(bank_entry_id = self.statement_id,company_id = self.company_id)