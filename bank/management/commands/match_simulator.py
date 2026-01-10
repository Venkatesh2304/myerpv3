from datetime import datetime
from itertools import combinations
from collections import defaultdict
from django.template.defaultfilters import default
from report.models import PartyReport
from bank.views import find_party_match
import datetime
import pandas as pd
import os
from custom.classes import Ikea
from bank.models import BankStatement,BankCollection
import joblib
import numpy as np

company = "devaki_hul"
ikea = Ikea(company)
fromd = datetime.date(2025,12,1)
tod = datetime.date(2025,12,31)
bank_id = 1 
folder = os.path.join("simulator",company)
os.makedirs(folder,exist_ok=True)   
vectorizer = joblib.load(f"tfidf_vectorizer_{bank_id}.joblib")
model = joblib.load(f"party_classifier_{bank_id}.joblib")

def download_outstanding(fromd,tod) :
    for date in pd.date_range(fromd,tod) :
        df = None
        for retry in range(2) :
            try : 
                df = ikea.outstanding(date = date)
                break
            except Exception as e : 
                print(e)
                ikea.login()
        if df is None : continue
        df.to_pickle(os.path.join(folder,f"{date}.pkl"))
        print(date)

def load_outstanding(date):
    return pd.read_pickle(os.path.join(folder,f"{date}.pkl"))

def calculate_coherence_score(bill_list,outstandings):
    ages  = []
    for i in outstandings :
        if i[0] in bill_list :
            ages.append(i[2])
    age_range = max(ages) - min(ages)
    std_dev = np.std(ages)    
    score = np.min(ages) / (std_dev + 1)
    return score

def match(outstandings,amt,prob) :
    allowed_left_diff = 0.5
    allowed_right_diff = 0.5
    # if len(outstandings) > 15 : 
    #     return None
    outstandings = outstandings[:25]
    matched_invoices = []
    
    # for r in range(1, len(outstandings) + 1):
    #     for combo in combinations(outstandings, r):
    #         total_balance = sum(item[1] for item in combo)
    #         if (total_balance  >= amt - allowed_left_diff) and (total_balance <= amt + allowed_right_diff) :
    #             matched_invoices.append( ([{"inum": item[0], "balance": item[1]} for item in combo] , round(abs(total_balance - amt))) )
    
    window_size = 10
    seen_combinations = set()
    for i in range(len(outstandings)):
        sub_pool = outstandings[i : i + window_size]
        for r in range(1, len(sub_pool) + 1):
            for combo in combinations(sub_pool, r):
                total = sum(item[1] for item in combo)
                if abs(total - amt) <= 0.5:
                    inums = tuple(sorted([item[0] for item in combo]))
                    if inums not in seen_combinations:
                        seen_combinations.add(inums)
                        matched_invoices.append( ([{"inum": item[0], "balance": item[1]} for item in combo] , round(abs(total - amt))) )

    matched_invoices = sorted(matched_invoices,key=lambda x : (x[1],len(x[0])))

    if len(outstandings) > 10 and len(matched_invoices) > 0 : 
       scores = []
       for i in matched_invoices :
           scores.append(calculate_coherence_score([ j["inum"] for j in i[0] ],outstandings))
       print(amt,scores)
       #sort by scores
       matched_invoices = sorted(matched_invoices,key=lambda x : scores[matched_invoices.index(x)],reverse=True)
       matched_invoices = [matched_invoices[0]]
       print(matched_invoices)

    if len(matched_invoices) != 1 and (len(outstandings) < 4) and (len(outstandings) != 0) and prob > 0.2 and False : 
       inums = []
       bal = amt
       for i in outstandings : 
           if bal > i[1] : 
               inums.append(i[0])
               bal -= i[1]
           else : 
               inums.append(i[0])
               bal = 0
    #    matched_invoices = [ ( [{"inum" : i} for i in inums] , None) ]
       matched_invoices = [ ([{"inum" : i[0]}],None) for i in outstandings if i[1] >= amt ]

    return [ i["inum"] for i in matched_invoices[0][0] ] if len(matched_invoices) == 1  and prob > 0.05 else None

def simulate(date):
    qs = BankStatement.objects.filter(date = date,type = "neft",bank_id = bank_id)
    rows = []
    for obj in qs : 
        row = {}
        if not obj.ikea_collection.exists() : continue
        company_id,matched_party_id,prob = find_party_match(model,vectorizer,obj.desc)
        matched_party_name = PartyReport.objects.filter(code = matched_party_id,company_id = company_id).first().name
        actual_party_name = obj.ikea_collection.first().party_name
        is_party_match = matched_party_name == actual_party_name

        coll_date = obj.ikea_collection.first().date
        outstandings = date_outstandings[coll_date][matched_party_name]
        
        matched_bills = match(outstandings,obj.amt,prob)
        row["date"] = date
        row["coll_date"] = coll_date
        row["desc"] = obj.desc
        row["overall"] = "false"
        row["matched_party"] = matched_party_name
        row["actual_party"] = actual_party_name
        row["party_match"] = str(is_party_match).upper()
        row["bills_match"] = ""
        row["actual_bills"] = ""
        row["matched_bills"] = ""
        row["prob"] = prob
        row["amt"] = obj.amt
        row["outstanding"] = ",".join([f"{i[0]}/{i[1]}" for i in outstandings]) if len(outstandings) < 4 else ""
        if is_party_match or True : 
            actual_bills = list(obj.ikea_collection.values_list("inum",flat=True))
            row["actual_bills"] = ",".join(set(actual_bills))

            if matched_bills is None : 
                row["bills_match"] = "NONE"
                rows.append(row)
                continue
            else :
                is_bills_match = set(actual_bills) == set(matched_bills)
                row["bills_match"] = str(is_bills_match).upper()
                if not is_bills_match : 
                    row["matched_bills"] = ",".join(set(matched_bills))
                else : 
                    row["overall"] = "true"
                rows.append(row)
                continue
        rows.append(row)
    return rows


# download_outstanding(fromd-datetime.timedelta(days=1),tod)
# exit(0)

#This contains previous day outstanding
date_outstandings = {}
for date in pd.date_range(fromd,tod) :
    outstanding = defaultdict(list)
    df = load_outstanding(date - datetime.timedelta(days=1))
    df = df.sort_values("In Days",ascending=False)
    for _,row in df.iterrows() :
        outstanding[row["Party Name"]].append((row["Bill Number"],row["O/S Amount"],row["In Days"]))
    date_outstandings[date.date()] = outstanding

# date = datetime.date(2025,12,30)
# df = load_outstanding(date - datetime.timedelta(days=1))
# df = df.sort_values("In Days",ascending=False)
# outstanding = defaultdict(list)
# for _,row in df.iterrows() :
#         outstanding[row["Party Name"]].append((row["Bill Number"],row["O/S Amount"],row["In Days"]))
# match(outstanding["ASOKA TRADING -D-D"],73340,0.5)
# exit(0)


rows = []
for date in pd.date_range(fromd,tod) :
    date = date.date()
    rows += simulate(date)

df = pd.DataFrame(rows)
df.to_excel(os.path.join(folder,f"d.xlsx"))
print(df.pivot_table(values="amt",index=["party_match","bills_match"],aggfunc="count"))
    
# download_outstanding(datetime.date(2025,11,30),datetime.date(2025,11,30))