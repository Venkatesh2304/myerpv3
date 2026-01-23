from django.template.defaultfilters import default
from django.db import models
from core.models import Organization

class TruckLoad(models.Model):
    purchase_products = models.JSONField(default=dict)
    scanned_products = models.JSONField(default=list)
    purchase_inums = models.JSONField(default=list)
    sku_map = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    organization = models.ForeignKey(Organization,on_delete=models.CASCADE)