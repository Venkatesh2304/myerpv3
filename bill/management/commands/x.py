from custom.classes import Gst
from report.models import OutstandingReport
from report.models import BeatReport
from report.models import PartyReport
from custom.classes import Unilever
from custom.classes import IkeaBank
from printing.printers import PickingLoadingSheetPrinter,LoadingSheetPrinter
from collections import defaultdict
from custom.classes import Einvoice
from bill_scan.eway import eway_df_to_json
import time
from bill.models import Bill
from load.models import TruckLoad
from core.models import User
from custom.classes import Billing
from report.models import EmptyArgs
from report.models import StockReport
from report.models import CollectionReport
import os
import requests
import pandas
import numpy
from core.models import Company
from report.models import BillAgeingReport,CollectionReport
from report.models import DateRangeArgs
from custom.classes import Ikea
import datetime
from report.models import SalesRegisterReport
from dateutil.relativedelta import relativedelta
import json
from bank.models import ChequeDeposit
from bill.models import Vehicle
import pandas as pd
import datetime
from django.utils.dateparse import parse_datetime
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory
from custom.classes import get_curl


i = Ikea("murugan_hul")
print(i.is_logged_in())
exit(0)
# i.login()
# print(i.is_logged_in())
# exit(0)

# g = Gst("devaki")
# while not g.is_logged_in() :
#     with open("captcha.png","wb+") as f :
#         f.write(g.captcha())
#     captcha_input = input("Enter Captcha : ")
#     status = g.login(captcha_input)
#     print("Login status : ",status)
# print("Gst Logged in successfully")
# print(g.gstin_details("33ABFFR9478P1Z8"))
# exit(0)

i = Ikea("lakme_rural")
for bill in ["CB01099"]:
    with open(f"temp/{bill}.json","w+") as f : 
        f.write(json.dumps(i.retrive_bill(bill)))
exit(0)

# rows = []
# for bill in ["CB01028","CB01029","CB01030","CB01031","CB01035","CB01036"]:
#     data = json.load(open(f"temp/{bill}.json"))
#     products = data["billingProductMasterVOList"]
#     for product in products :
#         row = {"bill":bill,"Product":product["prodName"], "Quantity" : product["totalQtyUnits"] , "Basic Rate" : product["basicRate"],
#         "Gross Amount":product["productGrossAmt"] ,
#         "Scheme Discount":product["schDiscAmt"], "taxable": product["productGrossAmt"] - product["schDiscAmt"], 
#         "tax_rate" : round(product["cgstTaxPer"]*2),
#         "tax":product["prodTaxAmt"]}
#         rows.append(row)
# df = pd.DataFrame(rows)
# df.to_excel("bills.xlsx",index=False)


# exit(0)

# i = Ikea("lakme_rural")
# StockReport.update_db(i,Company.objects.get(name="lakme_rural"),EmptyArgs())
# BeatReport.update_db(i,Company.objects.get(name="devaki_hul"),EmptyArgs())
# PartyReport.update_db(i,Company.objects.get(name="devaki_hul"),EmptyArgs())
# OutstandingReport.update_db(i,Company.objects.get(name="devaki_hul"),EmptyArgs())
# exit(0)

# i = Billing("lakme_rural")
# order_products = i.get_market_order(None,"all",allow_partial_bills=True)
# basepack_order_products = defaultdict(int)
# for order_product in order_products : 
#     basepack_order_products[order_product["bc"]] += order_product["cq"]

# print(basepack_order_products)

# i.login()
# print(i.is_logged_in())
# exit(0)

# df = pd.read_excel("~/Documents/LeverEDGE_41B862_productwisesales_2026022805422242224222.xlsx",dtype={"BasePack Code":str})
# df = df[(df["Bill Date"].dt.date <= datetime.date(2026,2,20)) & (df["Bill Date"].dt.date >= datetime.date(2026,1,21))]
# df["Units"] = df["Units"] * 0.5
# basepack_to_units = df.groupby("BasePack Code")["Units"].sum().to_dict()
# basepack_to_name = df.groupby("BasePack Code")["Product Description"].first().to_dict()
# with open("a.json") as f : 
#     items = json.load(f)


# min_order_qtys = defaultdict(list)
# available_qtys = defaultdict(list)
# confirmed_qtys = defaultdict(list)
# stock_qtys = defaultdict(list)
# basepack_to_uom = {}
# for item in items : 
#     min_order_qtys[item["BasePackCode"]].append(int(item["Lrange"]))
#     available_qtys[item["BasePackCode"]].append(int(item["Urange"]))
#     confirmed_qtys[item["BasePackCode"]].append(int(float(item["ConQty"])))
#     stock_qtys[item["BasePackCode"]].append(int(float(item["Stock"])))
#     basepack_to_uom[item["BasePackCode"]] = int(item["Caseconfig"])

# for basepack,qtys in min_order_qtys.items() : 
#     lrange = sum(min_order_qtys[basepack])
#     urange = sum(available_qtys[basepack])
#     confirmed_qty = sum(confirmed_qtys[basepack])
#     stock_qty = sum(stock_qtys[basepack])
#     if basepack not in basepack_to_units : 
#         continue
#     suggested_qty = basepack_to_units[basepack] if basepack in basepack_to_units else 0
#     suggested_qty = round(suggested_qty / basepack_to_uom[basepack])
#     real_suggested_qty = suggested_qty
#     suggested_qty = max(suggested_qty - stock_qty,0)
#     if suggested_qty < lrange : 
#         suggested_qty = lrange
#     elif suggested_qty > urange : 
#         suggested_qty = urange
#     if suggested_qty != confirmed_qty : 
#         print(basepack,basepack_to_name.get(basepack,"No Name"))
#         print("Suggested: ",suggested_qty,", Confirmed: ",confirmed_qty , " Real Suggested: ",real_suggested_qty, " stock:",stock_qty, " uom: ",basepack_to_uom[basepack])
#     # basepack_to_units[basepack] = suggested_qty

# exit(0)

i = Unilever("lakme_urban")
x = i.get("/sap/opu/odata/sap/YNGW_GET_ORDERS_PNTR_SRV/OrderTableSet?$filter=ImPrestine%20eq%20%27%27%20and%20PdpOrders%20eq%20%27X%27%20and%20Direct%20eq%20%27%27&sap-client=100&$format=json")
items = x.json()["d"]["results"]

with open("a.json","w+") as f : 
    f.write(json.dumps(items))

exit(0)

target_keys = [
    "Vkorg", "Vtweg", "Spart", "Werks", "Matkl", "Sno", "Matnr", "Maktx",
    "Wgbez", "Norm", "Meins", "Meinh", "Umrez", "Umren", "Stock", "Vbeln",
    "Posnr", "Netpr", "Kwmeng", "Caseconfig", "OpnQty", "CalQty", "Cal1Qty",
    "ConQty", "ConRange", "Units", "Uprice", "Value", "Area", "Qlockllimit",
    "Qlockulimit", "Mseht", "Cs", "DocDate", "ReqDate", "NormStock",
    "StockVal", "SugStock", "TotWeight", "Lrange", "Urange", "NormVal",
    "Matwa", "Chqstab", "Chqsfm", "Lifsk", "Yygroup", "Yysmatn3", "Yypsdsp",
    "ConQtyClds", "MatdescChange", "SourceMatnr", "Yyumvknum", "Yyumvkden",
    "MtposMara", "Yysrccluster", "Ytypeserv", "MatnrLdz", "BasePackCode",
    "BasePackText", "Color", "CBUClassif", "MarketOrder", "BaseNorms"
]

filtered_items = []
for item in items:
    filtered_item = {k: item.get(k) for k in target_keys if k in item}
    # Modify ConQty for specific item in the first request
    if filtered_item.get("Matnr") == "EMQQ100":
        filtered_item["ConQty"] = "1"
    filtered_items.append(filtered_item)

with open("filtered_items.json", "w+") as f:
    f.write(json.dumps(filtered_items))

# First Request
print("Sending first post request...")
res1 = i.post_orders(filtered_items)

with open("post_response_1.json", "w+") as f:
    f.write(json.dumps(res1))

# Extract NpTonnageVolume from the first response
# Response is a list of parsed JSON parts. We need to find the one with NpTonnageVolume.
tonnage_volume = []
for part in res1:
    if "d" in part and "NpTonnageVolume" in part["d"]:
        tonnage_volume = part["d"]["NpTonnageVolume"].get("results", [])
        break

# Second Request
print("Sending second post request with extracted tonnage volume...")
res2 = i.post_orders(filtered_items, tonnage_volume=tonnage_volume)

with open("post_response_2.json", "w+") as f:
    f.write(json.dumps(res2))

print(f"Double post completed. Responses saved to post_response_1.json and post_response_2.json")
exit(0)

# "Lrange": "0",
# "Urange": "5",




# PickingLoadingSheetPrinter("").generate(["CA02506","CA02507","CA02508","CA02499","CA02501"],{},i)
# exit(0)

# SalesRegisterReport.update_db(i,Company.objects.get(name="lakme_urban"),
#                                 DateRangeArgs(datetime.date(2026,2,1),datetime.date.today()))
# x,y=i.loading_sheet(["CA02506"])
# x.to_excel("a.xlsx")
# exit(0)

with open("b.json","w+") as f:
    f.write(json.dumps(i.retrive_bill("CB01060")))
exit(0)

df = pd.read_excel("~/Documents/LeverEDGE_41B862_CurrentStock_2026021310205520552055.xlsx")

# df = pd.read_excel("~/Documents/LeverEDGE_41B864_CurrentStock_2026021706515051505150.xlsx")
# barcode_to_basepack = json.load(open("barcodes.json"))
# basepack_to_barcode = defaultdict(list)
# for barcode,basepack in barcode_to_basepack.items() : 
#     basepack_to_barcode[basepack].append(barcode)

# Using Barcode model
from product_scan.models import Barcode
basepack_to_barcode = defaultdict(list)
# Loading all might be okay for a script, or iterate
for b in Barcode.objects.all():
    basepack_to_barcode[str(b.basepack)].append(b.barcode)

df["BarCode"] = df["Basepack Code"].apply(lambda x : ",".join(basepack_to_barcode[str(x).split(".")[0]]))
df.to_excel("b.xlsx")
exit(0)
# i = Billing("lakme_rural")
# i.stock_master()
# i.beat_export()
# exit(0)

# factory = APIRequestFactory()
# user = User.objects.get(username='sathish')
# request = factory.post('/mail_bills/', {"month": 1, "year": 2026, "company": "devaki_hul"}, format='json')
# force_authenticate(request, user=user)
# response = mail_bills(request)
# print(response.json())
# exit(0)


durl = i.get_bill_durl("CB00919","CB00920","pdf")
bytesio = i.fetch_durl_content(durl)
with open("a.pdf","wb+") as f:
    f.write(bytesio.getvalue())
exit(0)



today = datetime.date.today()
df = i.push_impact(fromd=today - datetime.timedelta(days=3),tod=today,bills=["AB78074"],vehicle_name="ANAND")
exit(0)

df = i.eway_excel(datetime.date.today() - datetime.timedelta(days=1),datetime.date.today(),["AB77846"])
df.to_excel("eway.xlsx")
json_output = eway_df_to_json(df,lambda x : "TN81J5107",lambda x : 3)
with open("eway.json","w+") as f:
    f.write(json_output)
sdf
print(1)
e = Einvoice("devaki")
print(2)
while not e.is_logged_in() : 
    captcha = e.captcha()
    with open("captcha.png","wb+") as f : 
        f.write(captcha)
    e.login(input("Enter captcha : "))

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

def df_to_pdf(df, pdf_path):
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    data = [df.columns.tolist()] + df.values.tolist()

    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')
    ]))

    doc.build([table])

df = e.get_eway_bills()
df = df[["EWB No","EWB Date","Supply Type","Doc.No","Doc.Date"]]
print(len(df.index))
df_to_pdf(df,"eway.pdf")
exit(0)

input("going to upload:")
e.upload_eway_bill(json_output)





with open("eway.json","w+") as f:
    f.write(json_output)


exit(0)

# i1 = Ikea("devaki_hul")
# i2 = Ikea("devaki_hul")
# if i1.cookies.get_dict() == i2.cookies.get_dict() : 
#     print("Same")
# else : 
#     print(i1.cookies.get_dict())
#     print(i2.cookies.get_dict())

# for i in range(10) : 
#     print(i1.is_logged_in())
#     print(i2.is_logged_in())
# exit(0)

# company_id = "devaki_hul"
# vehicles = [("DEVAKI","TN45AP3219"),
# ("KAMACHI","TN48V1218"),
# ("ASHOK","TN49AF5764"),
# ("BOLERO","TN81J5107"),
# ("TATA ACE NEW","TN52S5801")]
# for name,vehicle_no in vehicles:
#     Vehicle.objects.create(
#         name=name,
#         vehicle_no=vehicle_no,
#         company_id=company_id
#     ).save()
# exit(0)


# i = Ikea("devaki_hul")
# i.sync_impact(datetime.date(2026,1,24),datetime.date.today(),[],"xx")
# exit(0)



# r = Object()
# r.user = User.objects.get(username="sathish")
# mail_reports(r)
# exit(0)

# b = Billing.objects.get(company_id="devaki_hul",date=datetime.date(2025,12,19))
# b = [ i for i in b.market_order_data["mol"] if i["on"] == "20SMN00014P1581920251218"]
# with open("x.json","w+") as f:
#     f.write(json.dumps(b))
i = Billing("devaki_hul")
i.download_manual_collection().to_excel("a.xlsx")
# i.stock_movement_report(datetime.date(2025,12,10),datetime.date.today()).to_excel("a.xlsx")
# durl = i.get_bill_durl("AB00001","AB00999","pdf")
# bytesio = i.fetch_durl_content(durl)
# with open("a.pdf","wb+") as f:
#     f.write(bytesio.getvalue())

# StockReport.update_db(i,Company.objects.get(name="lakme_urban"),EmptyArgs())
# i.current_stock(datetime.date.today()).to_excel("a.xlsx")
exit(0)

# i.collection(datetime.date(2026,1,1),datetime.date(2026,1,7)).to_excel("a.xlsx")
# CollectionReport.update_db(i,Company.objects.get(name="devaki_hul"),DateRangeArgs(datetime.date.today(),datetime.date.today()))
exit(0)


# i.upi_statement(datetime.date(2026,1,1),datetime.date(2026,8,1)).to_excel("a.xlsx")
# i.get_user()
sadf


tod = datetime.date.today()
fromd = tod - datetime.timedelta(days=15)
i.product_wise_purchase(fromd,tod).to_excel("a.xlsx")

dsf
x = i.get_market_order(datetime.date(2025,12,21))
with open("x.json","w+") as f:
    f.write(json.dumps(x))
exit(0)


company = Company.objects.get(name="devaki_hul") 
df = Ikea.bill_ageing(i, datetime.date.today() - relativedelta(months=6),  #type: ignore
                                                       datetime.date.today())
print(df["Bill Date"].min())
exit(0)



i = Billing("devaki_hul")
bytesio = i.fetch_bill_txts(["AB66985","AB66986"])
with open("x.txt","w+") as f:
    f.write(bytesio.getvalue().decode('utf-8'))

# date = datetime.date.today() #(2025,12,7)
# x = i.einvoice_json(fromd=date,tod=date,bills=["AB66985"])
# with open("x.json","w+") as f:
    # f.write(x.getvalue().decode('utf-8'))

# x = i.get_creditlock({ "partyCode" : "D-P25086","parCodeRef":"D-P25086","parHllCode":"HUL-41A392D-P25086","showPLG":"DETS+PP" })
# print(x)



# company = Company.objects.get(name="lakme_rural")
# SalesRegisterReport.update_db(Ikea("lakme_rural"),company,DateRangeArgs(datetime.date(2025,12,12),datetime.date(2025,12,13)))