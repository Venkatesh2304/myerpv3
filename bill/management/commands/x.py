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


i = Billing("lakme_rural")
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