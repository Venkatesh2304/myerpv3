from django.template.defaultfilters import default
from django.db import models

class TruckLoad(models.Model):
    purchase = models.JSONField(default=dict)
    scanned = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)