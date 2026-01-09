from django.db import transaction
from bank.models import Bank
from bank.models import BankCollection
from bank.models import BankStatement
import pandas as pd
from bank.models import ChequeDeposit

company = "lakme_rural"
# BankCollection.objects.all().delete()
# BankStatement.objects.filter(bank__name = "SBI LAKME",type__isnull = True).all().delete()
# ChequeDeposit.objects.filter(company_id = company).all().delete()

cd = pd.read_csv("chequedeposit_rural.csv")
bc = pd.read_csv("bankcollection_rural.csv")
bs = pd.read_csv("bankstatement_rural.csv")

bank_name_to_id = {}
for obj in Bank.objects.all() : 
    bank_name_to_id[obj.name] = obj.id

with transaction.atomic() :
    cheque_id_remap = {}
    cd["deposit_date"] = cd["deposit_date"].fillna("")
    for _,row in cd.iterrows() : 
        obj = ChequeDeposit.objects.create(
            company_id = company,
            party_id = row["party_id"],
            bank = row["bank"],
            cheque_no = row["cheque_no"],
            amt = row["amt"],
            cheque_date = row["cheque_date"],
            deposit_date = row["deposit_date"] or None,
            entry_date = row["entry_date"],
        )
        cheque_id_remap[row["id"]] = obj.id

    bs_id_remap = {}
    bs["cheque_entry_id"] = bs["cheque_entry_id"].fillna("")
    bs["cheque_status"] = bs["cheque_status"].fillna("passed")
    bs["type"] = bs["type"].fillna("")
    for _,row in bs.iterrows() : 
        # if not row["type"]  : continue 
        obj,created = BankStatement.objects.update_or_create(
            bank_id = bank_name_to_id[row["bank"]],
            date = row["date"],
            idx = row["idx"],
            defaults = {
                "company_id" : company if row["type"] else None,
                "statement_id" : str(row["id"]),
                "ref" : row["ref"],
                "desc" : row["desc"],
                "amt" : row["amt"],
                "type" : row["type"] or None,
                "cheque_entry_id" : cheque_id_remap[row["cheque_entry_id"]] if row["cheque_entry_id"] else None,
                "cheque_status" : row["cheque_status"],
            }
        )
        print(obj.date,obj.idx,obj.amt,obj.type,row["type"],created)
        bs_id_remap[row["id"]] = obj.id

    bc["cheque_entry_id"] = bc["cheque_entry_id"].fillna("")
    bc["bank_entry_id"] = bc["bank_entry_id"].fillna("")
    for _,row in bc.iterrows() : 
        obj = BankCollection.objects.create(
            bill = row["bill_id"],
            cheque_entry_id = cheque_id_remap[row["cheque_entry_id"]] if row["cheque_entry_id"] else None,
            bank_entry_id = bs_id_remap[row["bank_entry_id"]] if row["bank_entry_id"] else None,
            amt = row["amt"],
        )   
    
    # raise Exception("hello")

exit(0)