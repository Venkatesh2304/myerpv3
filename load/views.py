from rest_framework.decorators import api_view
from django.http import JsonResponse
from collections import defaultdict
from django.template.defaultfilters import default
from load.models import TruckLoad
from django.shortcuts import render

@api_view(["GET"])
def load(request):
    id = 1
    load = TruckLoad.objects.first() #get(id = id)
    purchase = defaultdict(lambda : defaultdict(int))
    for purchase_no , cbu_data in load.purchase.items():
        for cbu , mrp_data in cbu_data.items():
            for mrp , count in mrp_data.items():
                purchase[cbu][mrp] += count
    box_count = len(load.scanned)
    if box_count == 0 or len(load.scanned[-1]) > 0:
        load.scanned = [{}]
        load.save()
        box_count += 1 
    return JsonResponse({"purchase" : purchase , "box_count" : box_count},safe=False)
    
@api_view(["GET","POST"])
def box(request):
    id = 1 
    load = TruckLoad.objects.first() #get(id = id)
    if request.method == "POST":
        box_no = int(request.data.get("box_no")) - 1
        load.scanned[box_no] = request.data.get("scanned")
        if len(load.scanned[-1]) >  0:
            load.scanned.append({})
        box_no = len(load.scanned)
        load.save()
        return JsonResponse({"box_no" : box_no})
    
    if request.method == "GET":
        box_no = int(request.query_params.get("box_no")) - 1
        current_scanned = defaultdict(lambda : defaultdict(int))
        others_scanned = defaultdict(lambda : defaultdict(int))
        for current_box_no,box_data in enumerate(load.scanned):
            for cbu,cbu_data in box_data.items():
                for mrp,mrp_data in cbu_data.items():
                    if box_no != current_box_no:
                        others_scanned[cbu][mrp] += mrp_data
                    else:
                        current_scanned[cbu][mrp] += mrp_data
        return JsonResponse({"current_scanned" : current_scanned , "others_scanned" : others_scanned},safe=False)
                
        

    