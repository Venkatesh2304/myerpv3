from report.models import OutstandingReport
from dateutil.relativedelta import relativedelta
from report.models import BillAgeingReport
from custom.classes import Ikea
from report.models import PartyReport
from report.models import EmptyArgs
from report.models import BeatReport
from report.models import SalesRegisterReport
from report.models import DateRangeArgs
from core.models import Company
from report.models import CollectionReport
from datetime import datetime
import datetime
from bill.models import Bill
# today = datetime.now().date()
#TODO: make it parameterized
for company in Company.objects.all() :
    print("Running sync for " + company.name)
    i = Ikea(company.pk)
    today = datetime.date.today() 
    SalesRegisterReport.update_db(i,company,DateRangeArgs(fromd=today-relativedelta(days=1),tod=today))
    Bill.sync_with_salesregister(company,fromd=today-relativedelta(days=1),tod=today)
    # CollectionReport.update_db(i,company,DateRangeArgs(fromd=today-relativedelta(months=3),tod=today))
    # # SalesRegisterReport.update_db(i,company,DateRangeArgs(fromd=today-relativedelta(months=7),tod=today))
    # OutstandingReport.update_db(i,company,EmptyArgs())
    # BeatReport.update_db(i,company,EmptyArgs())
    # BillAgeingReport.update_db(i,company,EmptyArgs())
    # PartyReport.update_db(i,company,EmptyArgs())

# CollectionReport.update_db(i,company,DateRangeArgs(fromd=today,tod=today))
# SalesRegisterReport.update_db(i,company,DateRangeArgs(fromd=today,tod=today))
exit(0)