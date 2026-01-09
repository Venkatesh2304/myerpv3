import os
import psutil
import requests
import pandas
import numpy
from core.models import Company
from report.models import BillAgeingReport
from report.models import DateRangeArgs
from custom.classes import Ikea,Billing
import datetime
from report.models import SalesRegisterReport
from dateutil.relativedelta import relativedelta
import json
from bank.models import ChequeDeposit


# b = Billing.objects.get(company_id="devaki_hul",date=datetime.date(2025,12,19))
# b = [ i for i in b.market_order_data["mol"] if i["on"] == "20SMN00014P1581920251218"]
# with open("x.json","w+") as f:
#     f.write(json.dumps(b))
i = Billing("lakme_urban")
i.upi_statement(datetime.date(2026,1,1),datetime.date(2026,8,1)).to_excel("a.xlsx")
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