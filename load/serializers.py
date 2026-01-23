from collections import defaultdict
from load.models import TruckLoad
from rest_framework import serializers

QtyMap = lambda : defaultdict(lambda : defaultdict(int))

class LoadSummarySerializer(serializers.ModelSerializer):
    purchase_stats = serializers.SerializerMethodField(method_name="get_purchase_stats")
    scanned_stats = serializers.SerializerMethodField(method_name="get_scanned_stats")
    def get_purchase_stats(self, obj):
        data = {}
        for purchase_no in obj.purchase_inums : 
            lines = 0
            cases = 0
            cbu_data = obj.purchase_products[purchase_no]
            for cbu , mrp_data in cbu_data.items():
                for mrp , count in mrp_data.items():
                    cases += count
                    lines += 1
            data[purchase_no] = {"lines" : lines , "cases" : cases}
        return data

    def get_scanned_stats(self, obj):
        box_count = 0 
        case_count = 0 
        for box_no,cbu_data in enumerate(obj.scanned_products): 
            if len(cbu_data) == 0 :
                continue
            box_count += 1
            for cbu , mrp_data in cbu_data.items():
                for mrp , count in mrp_data.items():
                    case_count += count
        return {"box_count" : box_count , "case_count" : case_count}

    class Meta:
        model = TruckLoad
        fields = ["id","purchase_inums","completed","purchase_stats","created_at","scanned_stats"]

class LoadDetailSerializer(serializers.ModelSerializer):
    purchase_qty_map = serializers.SerializerMethodField(method_name="get_purchase_qty_map")
    box_count = serializers.SerializerMethodField(method_name="get_box_count")

    def get_purchase_qty_map(self, obj):
        purchase = QtyMap()
        for purchase_no in obj.purchase_inums : 
            cbu_data = obj.purchase_products[purchase_no]
            for cbu , mrp_data in cbu_data.items():
                for mrp , count in mrp_data.items():
                    purchase[cbu][mrp] += count
        return purchase

    def get_box_count(self, obj):
        box_count = len(obj.scanned_products)
        if box_count == 0 or len(obj.scanned_products[-1]) > 0:
            obj.scanned_products = [{}]
            obj.save()
            box_count += 1
        return box_count

    class Meta:
        model = TruckLoad
        fields = ["purchase_qty_map","box_count"]