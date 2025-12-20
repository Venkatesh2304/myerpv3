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
today = datetime.now().date()
for company in Company.objects.all() :
    print("Running sync for " + company.name)
    i = Ikea(company.pk)
    BeatReport.update_db(i,company,EmptyArgs())
    BillAgeingReport.update_db(i,company,EmptyArgs())
    PartyReport.update_db(i,company,EmptyArgs())
    SalesRegisterReport.update_db(i,company,DateRangeArgs(fromd=today-relativedelta(months=3),tod=today))

# CollectionReport.update_db(i,company,DateRangeArgs(fromd=today,tod=today))
# SalesRegisterReport.update_db(i,company,DateRangeArgs(fromd=today,tod=today))
exit(0)