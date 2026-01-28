from bill.models import Bill
from load.models import TruckLoad
from core.models import User
from report.views import mail_reports
from custom.classes import Billing
from report.models import EmptyArgs
from report.models import StockReport
from report.models import CollectionReport
import os
import psutil
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
company = Company.objects.get(name="devaki_hul")
today = datetime.date(2026,1,28)
SalesRegisterReport.update_db(Ikea("devaki_hul"),company,DateRangeArgs(today - relativedelta(days=1),today))
Bill.sync_with_salesregister(company,fromd = today - relativedelta(days=1),tod = today)
df= pd.read_csv("print_bills_28.csv")
for index,row in df.iterrows():
    bill = row["bill_id"]
    print_time = parse_datetime(row["print_time"])
    print_type = row["print_type"]
    loading_sheet_id = row["loading_sheet_id"]
    if Bill.objects.filter(bill_id=bill,company_id="devaki_hul").count() == 0 : 
        print(bill)
    Bill.objects.filter(bill_id=bill,company_id="devaki_hul").update(print_time=print_time,print_type=print_type,loading_sheet_id=loading_sheet_id)
exit(0)
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