from django.db import models
from core.models import CompanyModel

class Ledger(CompanyModel):
    date = models.DateField()
    doc_no = models.CharField(max_length=100,null=True,blank=True)
    type = models.CharField(max_length=100)
    ref = models.CharField(max_length=100,null=True,blank=True)
    moc = models.CharField(max_length=100, null=True, blank=True)
    amt = models.FloatField()
    notes = models.JSONField(null=True,blank=True,default=list)