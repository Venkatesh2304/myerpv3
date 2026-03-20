from rest_framework import serializers
from .models import SalesScan, Barcode
from collections import defaultdict
import json
import os
from django.conf import settings
from django.db import connection

CBU_DATA = None
def get_cbu_data():
    global CBU_DATA
    if CBU_DATA is None:
        try:
            with open(os.path.join(settings.BASE_DIR, 'cbu.json'), 'r') as f:
                CBU_DATA = json.load(f)
        except Exception as e:
            print(f"Error loading cbu.json: {e}")

    query = """
        SELECT 
            jsonb_object_agg(sku_key, latest_value)
        FROM (
            SELECT DISTINCT ON (kv.key)
                kv.key AS sku_key, 
                kv.value AS latest_value
            FROM 
                load_truckload t,
                jsonb_each(t.sku_map) AS kv
            ORDER BY 
                kv.key, 
                t.id DESC
        ) AS latest_rows;
    """
    row = {}
    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()[0]
        if isinstance(row,str) :
            row = json.loads(row) 
    
    if CBU_DATA is None:
        return row
    return CBU_DATA | row

class SalesScanSummarySerializer(serializers.ModelSerializer):
    box_count = serializers.SerializerMethodField()

    class Meta:
        model = SalesScan
        fields = ['id', 'status', 'bill_date', 'scanned_time', 'bill_no', 'party_name', 'is_posted', 'box_count', 'mismatches']

    def get_box_count(self, obj):
        box_count = len(obj.scanned_products)
        if box_count == 0 or len(obj.scanned_products[-1]) > 0:
            obj.scanned_products = obj.scanned_products + [{}]
            obj.save()  
            box_count += 1
        return box_count

class SalesScanDetailSerializer(SalesScanSummarySerializer):
    barcode_map = serializers.SerializerMethodField()
    cbu_map = serializers.SerializerMethodField()

    class Meta:
        model = SalesScan
        fields = [
            'id', 'status', 'bill_date', 'scanned_time', 'bill_no', 'party_name', 'is_posted', 
            'bill_qty_map', 'case_config', 'box_count', 'logs',
            'barcode_map', 'cbu_map', 'sku_name_map', 'mismatches' 
        ]

    def get_barcode_map(self, obj):
        # Extract all basepacks from the bill
        basepacks = set()
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                if data.get('basepack'):
                    basepacks.add(str(data.get('basepack')))
        
        # Query Barcode model for these basepacks
        barcodes_qs = Barcode.objects.filter(basepack__in=basepacks)
        
        # Create a map: basepack -> list of barcodes
        bp_to_bc = defaultdict(list)
        for b in barcodes_qs:
            bp_to_bc[str(b.basepack)].append(b.barcode)

        barcode_map = defaultdict(list)
        
        for sku, mrp_data in obj.bill_products.items():
            for mrp, data in mrp_data.items():
                basepack = str(data.get('basepack'))
                barcodes = bp_to_bc.get(basepack, [])
                for bc in barcodes:
                    if sku not in barcode_map[bc]:
                        barcode_map[bc].append(sku)
        return barcode_map

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
