from rest_framework import serializers
from .models import SalesScan
from collections import defaultdict
import json
import os
from django.conf import settings

# Cache barcodes data
BARCODES_DATA = None
CBU_DATA = None
def get_barcodes_data():
    global BARCODES_DATA
    if BARCODES_DATA is None:
        try:
            with open(os.path.join(settings.BASE_DIR, 'barcodes.json'), 'r') as f:
                BARCODES_DATA = json.load(f)
        except Exception as e:
            print(f"Error loading barcodes.json: {e}")
            return {}
    return BARCODES_DATA

def get_cbu_data():
    global CBU_DATA
    if CBU_DATA is None:
        try:
            with open(os.path.join(settings.BASE_DIR, 'cbu.json'), 'r') as f:
                CBU_DATA = json.load(f)
        except Exception as e:
            print(f"Error loading cbu.json: {e}")
            return {}
    return CBU_DATA

def get_basepack_to_barcodes(barcodes_data):
    # Invert the map: Basepack -> list of Barcodes
    bp_to_bc = defaultdict(list)
    for barcode, basepack in barcodes_data.items():
        bp_to_bc[str(basepack)].append(barcode)
    return bp_to_bc

class SalesScanSerializer(serializers.ModelSerializer):
    bill_qty_map = serializers.SerializerMethodField()
    case_config = serializers.SerializerMethodField()
    barcode_map = serializers.SerializerMethodField()
    sku_list = serializers.SerializerMethodField()
    box_count = serializers.SerializerMethodField()
    cbu_map = serializers.SerializerMethodField()
    sku_name_map = serializers.SerializerMethodField()

    class Meta:
        model = SalesScan
        fields = ['id', 'status', 'bill_qty_map', 'case_config', 'box_count', 'barcode_map', 'sku_list', 'cbu_map', 'sku_name_map']
        # Removed 'scanned_products', 'bill_products', 'scanned_stats', 'diff_stats' 

    def get_bill_qty_map(self, obj):
        # Return { sku: { mrp: total_qty } }
        bill_qty_map = defaultdict(lambda: defaultdict(int))
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                # Total units = cases * units_per_case + loose_units
                total_qty = (data.get('qCases', 0) * data.get('unitsCase', 1)) + data.get('qUnits', 0)
                bill_qty_map[sku][mrp] = total_qty
        return bill_qty_map

    def get_case_config(self, obj):
        # Return { sku: units_per_case }
        case_config = {}
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                if sku not in case_config:
                    case_config[sku] = data.get('unitsCase', 1)
        return case_config

    def get_box_count(self, obj):
        box_count = len(obj.scanned_products)
        if box_count == 0 or len(obj.scanned_products[-1]) > 0:
            obj.scanned_products = [{}]
            obj.save()  
            box_count += 1
        return box_count

    def get_barcode_map(self, obj):
        barcodes_data = get_barcodes_data()
        bp_to_bc = get_basepack_to_barcodes(barcodes_data)
        barcode_map = defaultdict(list)
        
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                basepack = data.get('basepack')
                barcodes = bp_to_bc.get(basepack, [])
                for bc in barcodes:
                    if sku not in barcode_map[bc]:
                        barcode_map[bc].append(sku)
        return barcode_map

    def get_sku_list(self, obj):
        sku_list = []
        name_map = obj.get_sku_name_map()
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                sku_list.append({
                    'sku': sku,
                    'mrp': mrp,
                    'name': name_map.get(sku, sku)
                })
        return sku_list

    def get_cbu_map(self, obj):
        cbu_to_partial_sku = get_cbu_data()
        cbu_map = defaultdict(list)
        
        # Optimize by grouping bill SKUs by prefix (length 5)
        bill_sku_prefixes = defaultdict(list)
        for sku in obj.bill_products.keys():
            if len(sku) >= 5:
                prefix = sku[:5]
                bill_sku_prefixes[prefix].append(sku)
        
        for cbu, partial_sku in cbu_to_partial_sku.items():
            # partial_sku from json is the prefix
            if partial_sku in bill_sku_prefixes:
                # Add all matching full SKUs to this CBU
                cbu_map[cbu].extend(bill_sku_prefixes[partial_sku])
                
        return cbu_map

    def get_sku_name_map(self, obj):
        return obj.get_sku_name_map()
