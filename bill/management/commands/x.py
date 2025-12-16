from report.models import DateRangeArgs
from custom.classes import Ikea,Billing
import datetime
from report.models import SalesRegisterReport


i = Billing("devaki_hul")
# date = datetime.date(2025,12,7)
# x = i.einvoice_json(fromd=date,tod=date,bills=["AB63664"])
# with open("x.json","w+") as f:
#     f.write(x.getvalue().decode('utf-8'))

x = i.get_creditlock({ "partyCode" : "D-P25086","parCodeRef":"D-P25086","parHllCode":"HUL-41A392D-P25086","showPLG":"DETS+PP" })
print(x)



# company = Company.objects.get(name="lakme_rural")
# SalesRegisterReport.update_db(Ikea("lakme_rural"),company,DateRangeArgs(datetime.date(2025,12,12),datetime.date(2025,12,13)))