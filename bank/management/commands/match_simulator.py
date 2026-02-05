import json
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
fromd = datetime.date(2025,8,1)
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

def categorize_bills(outstandings):
    amounts = [item[3] for item in outstandings]
    mean_val = np.mean(amounts)
    std_val = np.std(amounts)

    # if mean_val < 1000 : 
    #     return outstandings

    real_bills = []
    dummy_bills = []
    
    for bill in outstandings:
        # If a bill is significantly lower than the average, it's 'dummy'
        # You can tune this threshold (e.g., -0.5)
        z_score = (bill[3] - mean_val) / std_val
        
        if z_score < -0.5 and bill[3] < 300: 
            dummy_bills.append(bill)
        else:
            real_bills.append(bill)
    
    if len(dummy_bills) > 0 : 
        print("dummy bills")
        print(dummy_bills)
        print(real_bills)
    return real_bills

def match(outstandings,amt,prob) :
    allowed_left_diff = 0.5
    allowed_right_diff = 0.5
    # if len(outstandings) > 15 : 
    #     return None
    

    outstandings = outstandings[:20]
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
       #sort by scores
       matched_invoices = sorted(matched_invoices,key=lambda x : scores[matched_invoices.index(x)],reverse=True)
       matched_invoices = [matched_invoices[0]]

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
    history = []

    for obj in qs.filter(desc__contains = "SANGHV") : 
        row = {}
        if not obj.ikea_collection.exists() : continue
        actual_party_name = obj.ikea_collection.first().party_name
        coll_date = obj.ikea_collection.first().date
        if coll_date not in date_outstandings : 
            print(obj.desc,obj.amt,actual_party_name)
            continue
        
        outstandings = date_outstandings[coll_date][actual_party_name]
        amt = obj.amt
        if "SANGAVI" in actual_party_name : 
            actual_combo = [{ "age" : (i.date - i.bill_date).days - 1, "amt" : float(i.amt) } for i in obj.ikea_collection.all()]
            window_size = 15
            outstandings = outstandings[:25]
            seen_combinations = set()
            matched_invoices = []
            for i in range(len(outstandings)):
                sub_pool = outstandings[i : i + window_size]
                for r in range(1, len(sub_pool) + 1):
                    for combo in combinations(sub_pool, r):
                        total = sum(item[1] for item in combo)
                        if abs(total - amt) <= 0.5:
                            inums = tuple(sorted([item[0] for item in combo]))
                            if inums not in seen_combinations:
                                seen_combinations.add(inums)
                                matched_invoices.append([{"age": item[2], "amt": float(item[1])} for item in combo])
            history.append({"correct_match" : actual_combo,"all_combinations" : matched_invoices,"total" : float(obj.amt)})
        continue
        company_id,matched_party_id,prob = find_party_match(model,vectorizer,obj.desc)
        matched_party_name = PartyReport.objects.filter(code = matched_party_id,company_id = company_id).first().name
        is_party_match = matched_party_name == actual_party_name
        
        actual_bills = list(obj.ikea_collection.values_list("inum",flat=True))

        if len(outstandings) < 10 : 
            outstandings1 = categorize_bills(outstandings)
            matched_bills1 = match(outstandings,obj.amt,prob)
            is_matched1 = matched_bills1 and (set(matched_bills1) == set(actual_bills))
            matched_bills2 = match(outstandings1,obj.amt,prob)
            is_matched2 = matched_bills2 and (set(matched_bills2) == set(actual_bills))
            if is_matched1 and  (not is_matched2) : 
                print("Mismatch",obj.desc,obj.amt,matched_party_name)
                print(outstandings)
                print(actual_bills)
                print(matched_bills1)
                print(matched_bills2)
            outstandings = categorize_bills(outstandings)
                



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
    return history
    # return rows


# download_outstanding(fromd-datetime.timedelta(days=1),tod)
# exit(0)

#This contains previous day outstanding
date_outstandings = {}
for date in pd.date_range(fromd,tod) :
    outstanding = defaultdict(list)
    df = load_outstanding(date - datetime.timedelta(days=1))
    df = df.sort_values("In Days",ascending=False)
    for _,row in df.iterrows() :
        outstanding[row["Party Name"]].append((row["Bill Number"],row["O/S Amount"],row["In Days"],row["Net Amount"]))
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
history = []
for date in pd.date_range(fromd,tod) :
    date = date.date()
    # rows += simulate(date)
    history += simulate(date)
json.dump(history,open("history.json","w+"))

# df = pd.DataFrame(rows)
# df.to_excel(os.path.join(folder,f"d.xlsx"))
# print(df.pivot_table(values="amt",index=["party_match","bills_match"],aggfunc="count"))
    
# download_outstanding(datetime.date(2025,11,30),datetime.date(2025,11,30))