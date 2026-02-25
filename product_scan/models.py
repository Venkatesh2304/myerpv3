from core.models import CompanyModel
from django.db import models
import datetime

class SalesScan(CompanyModel):
    bill_no = models.CharField(max_length=255)
    bill_date = models.DateField(null=True, blank=True)
    party_name = models.CharField(max_length=255, null=True, blank=True)
    is_posted = models.BooleanField(default=False)
    
    # Stores the parsed bill data:
    # { sku_code : { mrp : { "qUnits": int, "qCases": int, "unitsCase": int, "name": str } } }
    bill_products = models.JSONField(default=dict)
    
    # Stores the scanned data as a list of boxes:
    # [ { sku_code : { mrp : qty } }, ... ]
    scanned_products = models.JSONField(default=list)
    
    # Stores logs for each box
    logs = models.JSONField(default=list)
    
    # Stores the time when scanned_products was last updated
    scanned_time = models.DateTimeField(null=True, blank=True)

    def update_from_bill_data(self, bill_data):
        from collections import defaultdict
        
        # Extract party name and posted status
        party_info = bill_data.get('partyInfoVO', {})
        self.party_name = party_info.get('partyName')
        
        bill_hd = bill_data.get('billHdVO', {})
        blh_status = bill_hd.get('blhStatus', 0)
        eInvBillEditMsg = bill_hd.get('eInvBillEditMsg', '')
        self.is_posted = (blh_status != 0) or (eInvBillEditMsg != "")

        # Extract bill date
        billDtStr = bill_hd.get("billDtStr")
        if billDtStr:
            try:
                self.bill_date = datetime.datetime.strptime(billDtStr, '%d/%m/%Y').date()
            except:
                pass

        # Update bill products
        products_list = bill_data.get('billingProductMasterVOList', [])
        bill_products = defaultdict(lambda: defaultdict(dict))
        for item in products_list:
            sku = item.get('prodCode')
            mrp = int(item.get('mrp', 0))
            if not sku: continue
            
            existing = bill_products[sku][mrp]
            bill_products[sku][mrp] = {
                'qUnits': int(item.get('qUnits', 0)) + int(existing.get('qUnits', 0)),
                'qCases': int(item.get('qCase', 0)) + int(existing.get('qCases', 0)),
                'unitsCase': int(item.get('unitsCase', 1)),
                'basepack': str(item.get('itemVarCode')),
                'name': item.get('prodName', '')
            }
        
        print(self.bill_no, "Bill Status : ", blh_status)
        # Convert defaultdict to regular dict for JSONField serialization
        if blh_status != 4:
            self.bill_products = {sku: dict(mrps) for sku, mrps in bill_products.items()}
        elif blh_status == 4:
            #Bill is cancelled
            self.bill_products = {}
            print(self.bill_no,self.scanned_qty_map)
            if len(self.scanned_qty_map) == 0 :
                print("Calling delete on SalesScan : ", self.id)
                self.delete()
                print("Done delete on SalesScan : ", self.id)
                return
        self.save()


    @property
    def bill_qty_map(self):
        # Return { sku: { mrp: total_qty } }
        from collections import defaultdict
        qty_map = defaultdict(lambda: defaultdict(int))
        for sku, mrp_data in self.bill_products.items():
            for mrp, data in mrp_data.items():
                total_qty = (data.get('qCases', 0) * data.get('unitsCase', 1)) + data.get('qUnits', 0)
                qty_map[sku][mrp] = total_qty
        return qty_map

    @property
    def case_config(self):
        # Return { sku: units_per_case }
        config = {}
        for sku, mrp_data in self.bill_products.items():
            for mrp, data in mrp_data.items():
                if sku not in config:
                    config[sku] = data.get('unitsCase', 1)
        return config

    @property
    def sku_name_map(self):
        sku_map = {}
        for sku, mrp_data in self.bill_products.items():
            for mrp, data in mrp_data.items():
                if sku not in sku_map or data.get('name'):
                    sku_map[sku] = data.get('name', sku)
        return sku_map

    @property
    def scanned_qty_map(self):
        from collections import defaultdict
        scanned_totals = defaultdict(lambda: defaultdict(int))
        for box_data in self.scanned_products:
            for sku, mrp_data in box_data.items():
                for mrp, qty in mrp_data.items():
                    scanned_totals[sku][mrp] += qty
        return scanned_totals

    @property
    def mismatches(self):
        scanned_totals = self.scanned_qty_map
        mismatches = []
        sku_name_map = self.sku_name_map
        
        all_pairs = set()
        for sku, mrp_data in self.bill_products.items():
            for mrp in mrp_data.keys():
                all_pairs.add((sku, mrp))
        for sku, mrp_data in scanned_totals.items():
            for mrp in mrp_data.keys():
                all_pairs.add((sku, mrp))
                
        bill_qty_map = self.bill_qty_map
        for sku, mrp in all_pairs:
            mrp_str = str(mrp)
            billed_qty = bill_qty_map.get(sku, {}).get(mrp_str, 0)
            scanned_qty = scanned_totals.get(sku, {}).get(mrp, 0)
            
            if billed_qty != scanned_qty:
                mismatches.append({
                    'sku': sku,
                    'name': sku_name_map.get(sku, sku),
                    'mrp': mrp,
                    'billed': billed_qty,
                    'scanned': scanned_qty
                })
        return mismatches
    
    status = models.BooleanField(default=False) # False: In Progress, True: Completed (Verified) or similar
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('bill_no', 'company_id')


class Barcode(models.Model):
    barcode = models.CharField(max_length=255, primary_key=True)
    basepack = models.CharField(max_length=255)
    manual = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.barcode} - {self.basepack}"
