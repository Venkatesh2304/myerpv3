from core.models import CompanyModel
from django.db import models

class SalesScan(CompanyModel):
    bill_no = models.CharField(max_length=255)
    bill_date = models.DateField(null=True, blank=True)
    
    # Stores the parsed bill data:
    # { sku_code : { mrp : { "qUnits": int, "qCases": int, "unitsCase": int, "name": str } } }
    bill_products = models.JSONField(default=dict)
    
    # Stores the scanned data as a list of boxes:
    # [ { sku_code : { mrp : qty } }, ... ]
    scanned_products = models.JSONField(default=list)

    def get_sku_name_map(self):
        sku_map = {}
        for sku, mrp_data in self.bill_products.items():
            for mrp, data in mrp_data.items():
                if sku not in sku_map or data.get('name'):
                    sku_map[sku] = data.get('name', sku)
        return sku_map
    
    status = models.BooleanField(default=False) # False: In Progress, True: Completed (Verified) or similar
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('bill_no', 'company_id')


class Barcode(models.Model):
    barcode = models.CharField(max_length=255, primary_key=True)
    basepack = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.barcode} - {self.basepack}"
