from report.models import SalesRegisterReport
from bank.models import Bank
import json
import datetime
from bank.models import BankStatement
data = {}
for bank_id in Bank.objects.all().values_list("id",flat=True) :
    data[bank_id] = []
    for obj in BankStatement.objects.filter(bank_id = bank_id,type__in = ["neft"],
                                            date__gte = datetime.date(2025,6,1)) :
        parties = set()
        for coll in obj.all_collection :
            bill = SalesRegisterReport.objects.filter(company_id = coll.company,inum = coll.bill).first()
            if bill : 
                parties.add((coll.company,bill.party_id))
        parties = list(parties)
        if len(parties) == 1  : 
            data[bank_id].append((obj.desc,parties[0][0],parties[0][1]))
        if len(data[bank_id]) % 100 == 0 : 
            print(len(data[bank_id]))

json.dump(data,open("data.json","w+"))        

