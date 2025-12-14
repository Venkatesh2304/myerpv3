from report.models import DateRangeArgs
from custom.classes import Ikea,Billing
import datetime
from report.models import SalesRegisterReport

i = Billing("devaki_hul")
x = i.get_creditlock({ "partyCode" : "P16154","parCodeRef":"P16154","parHllCode":"HUL-41A392P16154","showPLG":"FNB+HFD" })
print(x)



# company = Company.objects.get(name="lakme_rural")
# SalesRegisterReport.update_db(Ikea("lakme_rural"),company,DateRangeArgs(datetime.date(2025,12,12),datetime.date(2025,12,13)))