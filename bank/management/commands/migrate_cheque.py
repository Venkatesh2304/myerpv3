from bank.models import Bank
from bank.models import BankCollection
from bank.models import BankStatement
import pandas as pd
from bank.models import ChequeDeposit

BankCollection.objects.all().delete()
BankStatement.objects.all().delete()
ChequeDeposit.objects.all().delete()

company = "devaki_hul"
cd = pd.read_csv("chequedeposit.csv")
bc = pd.read_csv("bankcollection.csv")
bs = pd.read_csv("bankstatement.csv")

bank_name_to_id = {}
for obj in Bank.objects.all() : 
    bank_name_to_id[obj.name] = obj.id

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
    obj = BankStatement.objects.create(
        company_id = company,
        date = row["date"],
        statement_id = str(row["id"]),
        idx = row["idx"],
        ref = row["ref"],
        desc = row["desc"],
        amt = row["amt"],
        bank_id = bank_name_to_id[row["bank"]],
        type = row["type"] or None,
        cheque_entry_id = cheque_id_remap[row["cheque_entry_id"]] if row["cheque_entry_id"] else None,
        cheque_status = row["cheque_status"],
    )
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
    

exit(0)