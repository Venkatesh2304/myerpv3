from core.utils import get_media_url
from django.conf import settings
from django.http import FileResponse
from custom.classes import Ikea
from rest_framework.decorators import api_view
from django.http import JsonResponse
from collections import defaultdict
from django.template.defaultfilters import default
from load.models import TruckLoad
from django.shortcuts import render
from collections import Counter
import contextlib
import datetime
from io import BytesIO
import pprint
import os
import pdfplumber
import pandas as pd
import time

QtyMap = lambda : defaultdict(lambda : defaultdict(int))

def extract_product_quantities(bytesio):
    # 5 cm in points (1 inch = 72 points; 1 cm ≈ 28.35 points)
    width_limit_pts = 3.5 * 28.35  # ~141.75 pts
    qty_offset = 13.2 * 28.35
    codes = ""
    qtys = ""
    inum = None 
    with contextlib.redirect_stderr(None):  # Suppress all stdout
        with pdfplumber.open(bytesio) as pdf:
            for i, page in enumerate(pdf.pages):
                page = pdf.pages[i]
                if i == 0 :  
                    inum = page.extract_text().splitlines()[0].split(":")[-1].strip()
                cropped = page.within_bbox((0, 0, width_limit_pts, page.height))
                text = cropped.extract_text()
                codes += text + "\n"

                cropped = page.within_bbox(
                    (qty_offset, 0, qty_offset + width_limit_pts, page.height)
                )
                text = cropped.extract_text()
                qtys += text + "\n"

    codes = codes.split("SKU code")[-1].split("Net Payabl")[0].splitlines()[1:]
    cbu = codes[::2]
    sku = codes[1::2]
    qtys = qtys.split("Old MRP\n")[-1].splitlines()
    qtys = [qty.split("TAX")[0] for qty in qtys if qty]
    qtys = [qty for qty in qtys if qty]
    qtys = qtys[: int(len(codes)*3/2)]
    mrps = [int(mrp.split(".")[0]) for mrp in qtys[1::3]]
    qtys = [int(qty.split("/")[0].strip()) for qty in qtys[::3]]
    return inum , list(zip(cbu, sku, mrps,qtys))

@api_view(["POST"])
def upload_purchase_invoice(request) :
    time.sleep(19)
    load_id = request.data.get("load")
    file = request.FILES.get("file") 
    load = TruckLoad.objects.get(id=load_id)
    bytesio = BytesIO(file.read())
    inum , product_quantities = extract_product_quantities(bytesio)
    data = QtyMap()
    sku_map = load.sku_map
    for cbu , sku , mrp , qty in product_quantities :
        data[cbu][mrp] += qty
        sku_map[cbu] = sku
    load.purchase_products[inum] = data
    if inum not in load.purchase_inums:
        load.purchase_inums.append(inum)
    load.save()
    return JsonResponse({"status": "success"})

@api_view(["GET"])
def get_last_load(request):
    organization = request.user.organization
    load = TruckLoad.objects.filter(organization=organization,completed = False).order_by("-created_at").first()
    if not load:
        load = TruckLoad.objects.create(organization=organization)
        load.save()
    return JsonResponse({"load" : load.pk})

@api_view(["GET","POST"])
def box(request):
    if request.method == "POST":
        load_id = request.data.get("load")
        load = TruckLoad.objects.get(pk = load_id)
        box_no = int(request.data.get("box_no")) - 1
        load.scanned_products[box_no] = request.data.get("scanned")
        if len(load.scanned_products[-1]) >  0:
            load.scanned_products.append({})
        box_no = len(load.scanned_products)
        load.save()
        return JsonResponse({"box_no" : box_no})
    
    if request.method == "GET":
        load_id = request.query_params.get("load")
        load = TruckLoad.objects.get(pk = load_id)
        box_no = int(request.query_params.get("box_no")) - 1
        current_scanned = QtyMap()
        others_scanned = QtyMap()
        for current_box_no,box_data in enumerate(load.scanned_products):
            for cbu,cbu_data in box_data.items():
                for mrp,mrp_data in cbu_data.items():
                    if box_no != current_box_no:
                        others_scanned[cbu][mrp] += mrp_data
                    else:
                        current_scanned[cbu][mrp] += mrp_data
        return JsonResponse({"current_scanned" : current_scanned , "others_scanned" : others_scanned},safe=False)
                
@api_view(["GET"])
def download_load_summary(request) : 
    load_id = request.query_params.get("load")
    tod = datetime.date.today()
    fromd = tod - datetime.timedelta(days=15)
    dfs:list[pd.DataFrame] = []
    for company in request.user.organization.companies.all():
        df = Ikea(company.pk).product_wise_purchase(fromd,tod)
        df["sku"] = df["Item Code"].str.slice(0,5)
        df["desc"] = df["Item Name"]
        dfs.append(df[["sku","desc"]])
    product_master:pd.DataFrame = pd.concat(dfs,ignore_index=True)
    product_master = product_master.drop_duplicates(subset = ["sku"])

    load = TruckLoad.objects.get(id=load_id)
    #Purchase Products
    purchase_rows = []
    for inum in load.purchase_inums :
        cbu_data = load.purchase_products[inum].items() 
        for cbu , mrp_data in cbu_data :
            for mrp , qty in mrp_data.items() :
                purchase_rows.append([inum,cbu,mrp,qty])
    purchase_products = pd.DataFrame(purchase_rows,columns=["inum","cbu","mrp","purchase_qty"])
    purchase_products_grouped = purchase_products.groupby(["cbu","mrp"]).aggregate({"purchase_qty" : "sum"}).reset_index()
    
    #Load Products
    scanned_rows = []
    for box,box_data in enumerate(load.scanned_products):
        for cbu,cbu_data in box_data.items():
            for mrp,mrp_data in cbu_data.items():
                scanned_rows.append([cbu,mrp,mrp_data,box + 1])
    scanned_products = pd.DataFrame(scanned_rows,columns=["cbu","mrp","load_qty","box"])
    box_summary = scanned_products.groupby(["box"])[["load_qty"]].sum().reset_index()
    load_products_grouped = scanned_products.groupby(["cbu","mrp"]).aggregate({"load_qty" : "sum"}).reset_index()

    df = pd.merge(purchase_products_grouped, load_products_grouped, on=["cbu","mrp"], how="outer").fillna(0)
    df["sku"] = df["cbu"].replace(load.sku_map)
    df["diff"] = df["load_qty"] - df["purchase_qty"]
    df = pd.merge(df, product_master[["sku","desc"]] , on="sku", how="left") 
    df = df[["cbu","sku","desc","mrp","purchase_qty","load_qty","diff"]]
    mismatch = df[df["diff"] != 0]

    mismatch["diff_value"] = mismatch.apply(lambda row : int(row["diff"]) * int(row["mrp"]), axis=1)
    cbu_diff_qty_map = mismatch.groupby("cbu")["diff"].sum().to_dict()
    cbu_diff_value_map = mismatch.groupby("cbu")["diff_value"].sum().to_dict()
    
    mismatch["cbu_diff_qty"] = mismatch["cbu"].replace(cbu_diff_qty_map)
    mismatch["cbu_diff_value"] = mismatch["cbu"].replace(cbu_diff_value_map)
    mismatch_higher_mrp = mismatch[(mismatch["cbu_diff_value"] > 0) & (mismatch["cbu_diff_qty"] == 0)]
    mismatch_lower_mrp = mismatch[(mismatch["cbu_diff_value"] < 0) & (mismatch["cbu_diff_qty"] == 0)]
    mismatch_cbu = mismatch[mismatch["cbu_diff_qty"] != 0]
    del mismatch["diff_value"] , mismatch["cbu_diff_value"] , mismatch["cbu_diff_qty"]

    correct = df[df["diff"] == 0]
    user_dir = os.path.join(settings.MEDIA_ROOT, "load", request.user.pk)
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"load_summary_{load.id}.xlsx")
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        mismatch_cbu.to_excel(writer, index=False, sheet_name='Mismatch (CBU)')
        mismatch_higher_mrp.to_excel(writer, index=False, sheet_name='Mismatch (Higher MRP)')
        mismatch_lower_mrp.to_excel(writer, index=False, sheet_name='Mismatch (Lower MRP)')
        mismatch.to_excel(writer, index=False, sheet_name='Mismatch')
        correct.to_excel(writer, index=False, sheet_name='Correct')
        box_summary.to_excel(writer, index=False, sheet_name='Box')
        df.to_excel(writer, index=False, sheet_name='Summary')
        scanned_products.to_excel(writer, index=False, sheet_name='Detailed')
    return JsonResponse({"file_path": get_media_url(file_path)})