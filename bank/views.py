
from django.db.models.aggregates import Count
import datetime
from urllib.parse import urljoin
from django.db.models.aggregates import Sum
from report.models import EmptyArgs
from report.models import SalesRegisterReport
from collections import defaultdict
from report.models import DateRangeArgs
from report.models import CollectionReport
from django.conf import settings
from io import BytesIO
import pandas as pd
from bill.models import Billing
from bank.models import BankCollection
from core.models import Company
from itertools import combinations
from report.models import OutstandingReport
from report.models import PartyReport
from custom.classes import Ikea
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
from django.db.models.query_utils import Q
import os
from bank.parsers import KVBParser
from bank.parsers import SBIParser
import datetime
from django.http.response import HttpResponse
from bank.models import ChequeDeposit
from rest_framework.decorators import api_view
import pandas as pd
from rest_framework.response import Response
from django.http import JsonResponse
from bank.models import Bank, BankStatement
import re
import numpy as np
import joblib
from gst.gst import addtable
from core.utils import get_media_url

def clean_text(text):
    text = text.upper()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def find_cheque_match(bank_entry,company_ids,allowed_diff=10):
    qs = ChequeDeposit.objects.filter(deposit_date__isnull=False,company_id__in = company_ids).filter(
                    amt__gte=bank_entry.amt - allowed_diff,
                    amt__lte=bank_entry.amt + allowed_diff
                ).filter( Q(bank_entry__isnull=True) | Q(bank_entry = bank_entry) )
    return qs

def find_party_match(model,vectorizer,desc):
    description = clean_text(desc)
    vec = vectorizer.transform([description])
    probs = model.predict_proba(vec)[0]
    classes = model.classes_
    ranked = sorted(
        zip(classes, probs),
        key=lambda x: x[1],
        reverse=True
    )
    best_label, best_prob = ranked[0]
    company = best_label.split("/")[0]
    party_id = best_label.split("/")[1]
    # print(best_label,best_prob)
    return company,party_id,best_prob

def get_match(outstandings,amt,prob) :
    def calculate_coherence_score(invoices):
        ages  = [ i["age"] for i in invoices ]
        std_dev = np.std(ages)    
        score = np.min(ages) / (std_dev + 1)
        return score

    outstandings = outstandings[:20]
    matched_invoices = []
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
                        matched_invoices.append( [{"inum": item[0], "balance": item[1], "age" : item[2]} for item in combo]  )

    matched_invoices = sorted(matched_invoices,key=lambda x : len(x))

    if len(outstandings) > 10 and len(matched_invoices) > 0 : 
       scores = []
       for i in matched_invoices :
           scores.append(calculate_coherence_score(i))
       #sort by scores
       matched_invoices = sorted(matched_invoices,key=lambda x : scores[matched_invoices.index(x)],reverse=True)
       matched_invoices = [matched_invoices[0]]

    return matched_invoices if prob > 0.05 else []

def find_neft_match(bankstatement_obj,company_id,party_id,prob):
    allowed_diff = 0.5
    amt = bankstatement_obj.amt
    outstandings = list(OutstandingReport.objects.filter(
        party_id = party_id,
        company_id = company_id,
        balance__gte =  1,
        balance__lte = amt + allowed_diff,
        bill_date__gte = datetime.date.today() - datetime.timedelta(days=90)
    ).values_list("inum","balance","bill_date").order_by("bill_date"))
    today = datetime.date.today()
    pending_outstandings = []
    for inum,balance,bill_date in outstandings :
        pending_collection = 0 
        for coll in BankCollection.objects.filter(bill = inum).exclude(bank_entry = bankstatement_obj) :
            if coll.company != company_id : continue 

            pushed = True
            if coll.bank_entry : 
               pushed = (coll.bank_entry.pushed_status == "pushed")
            
            if coll.cheque_entry : 
                bank_entry = getattr(coll.cheque_entry,"bank_entry",None)
                pushed = (bank_entry and bank_entry.pushed_status == "pushed")

            if pushed == False : 
                pending_collection += balance
        new_balance = round(balance - pending_collection)
        if new_balance > 0 :
            pending_outstandings.append((inum,new_balance,(today - bill_date).days))
    
    #Try all combination of outstandings whre each row has keys inum and balance.
    #allow if the difference is lesss than allowed_difference with amt
    matched_invoices = get_match(pending_outstandings,amt,prob)
    return matched_invoices

def smart_match(queryset):
    bank_objs_map:dict[int,list[BankStatement]] = defaultdict(list)
    for obj in queryset :
        bank_objs_map[obj.bank_id].append(obj)
    for bank_id, objs in bank_objs_map.items() :
        company_ids = Bank.objects.get(id = bank_id).companies.all().values_list("name",flat=True)
        vectorizer = joblib.load(f"tfidf_vectorizer_{bank_id}.joblib")
        model = joblib.load(f"party_classifier_{bank_id}.joblib")
        for obj in objs :
            chq_matches = list(find_cheque_match(obj,company_ids, allowed_diff=0))
            if len(chq_matches) > 1 : 
                chq_matches = [ chq_obj for chq_obj in chq_matches if str(chq_obj.cheque_no) in obj.desc ]

            if len(chq_matches) == 0 : 
                #Try neft
                company_id,party_id,prob = find_party_match(model,vectorizer,obj.desc)
                matched_invoices = find_neft_match(obj,company_id,party_id,prob)
                if len(matched_invoices) == 1 : 
                    obj.type = "neft"
                    obj.company_id = company_id
                    BankCollection.objects.filter(bank_entry_id = obj.pk).delete()
                    obj.add_event("smart_matched")
                    obj.save()
                    for inv in matched_invoices[0] : 
                        BankCollection.objects.create(bank_entry = obj, bill = inv["inum"],
                                                                            amt = inv["balance"]).save()
            elif len(chq_matches) == 1 : 
                obj.type = "cheque"
                obj.cheque_entry = chq_matches[0]
                obj.cheque_status = "passed"
                obj.company_id = chq_matches[0].company_id
                obj.add_event("smart_matched")
                obj.save()
            else : 
                continue 
    
@api_view(["POST"])
def smart_match_view(request):
    ids = request.data.get("ids")
    queryset = BankStatement.objects.filter(id__in = ids)
    smart_match(queryset)
    return JsonResponse({"success":True})

@api_view(["POST"]) 
def bank_collection(request) :
    bankstatement_id = int(request.data.get("bank_id"))
    bankstatement_obj = BankStatement.objects.get(id = bankstatement_id)
    colls = bankstatement_obj.all_collection
    pushed_bills = CollectionReport.objects.filter(bank_entry_id = bankstatement_obj.statement_id,
                                                   company_id = bankstatement_obj.company_id).values_list("inum",flat=True)
    bills = [ { "bill" : coll.bill, "amt" : coll.amt, "pushed" : coll.bill in pushed_bills } for coll in colls ]
    return JsonResponse(bills,safe=False)
    
@api_view(["POST"])
def generate_deposit_slip(request) :
    data = request.data
    ids = data.get("ids")
    queryset = ChequeDeposit.objects.filter(id__in = ids)
    cheques = list(queryset)
    if not cheques : 
        return Response({"error":"No data found"},status=400)
    
    data = [
            {'S.NO': idx + 1, 'NAME': cheque.party.name, 'BANK': cheque.bank, 'CHEQUE NO': cheque.cheque_no, 'AMOUNT': cheque.amt , 
             'BILLS' : ','.join(cheque.collection.all().values_list("bill",flat=True) ) }
            for idx, cheque in enumerate(cheques)
        ]

    # Create a new Excel file in memory
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=deposit_slip.xlsx'
    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        df = pd.DataFrame(data)
        workbook = writer.book
        worksheet = workbook.add_worksheet('DEPOSIT SLIP')
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 14,
            'border': 1
        })
        worksheet.merge_range('A1:E1', 'DEPOSIT SLIP', header_format)
        worksheet.merge_range('A2:E2', 'DEVAKI ENTERPRISES', header_format)
        worksheet.merge_range('A3:E3', 'A/C NO: 1889223000000030', header_format)
        worksheet.merge_range('A4:E4', 'PAN NO: AAPFD1365C', header_format)
        worksheet.merge_range('A5:E5', f'DATE: {datetime.date.today().strftime("%d %b %Y")}', header_format)
        df_start_row = 5
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(df_start_row, col_num, value,header_format)
        for row_num, row_data in enumerate(df.values):
            for col_num, cell_value in enumerate(row_data):
                worksheet.write(df_start_row + row_num + 1, col_num, cell_value)
        writer.sheets['DEPOSIT SLIP'] = worksheet

    queryset.update(deposit_date=datetime.date.today()) 
    return response

@api_view(["POST"])
def bank_statement_upload(request):
    try:
        bank_type = request.data.get("bank_type")
        excel_file = request.FILES['excel_file']
        parsers = { "sbi" : SBIParser(), "kvb" : KVBParser() }
        parser = parsers.get(bank_type)

        if not parser:
            return JsonResponse({"error": "Could not identify bank format or account number"}, status=500)
            
        df, acc_no = parser.parse(excel_file)
        
        if not acc_no:
             return JsonResponse({"error": "Could not find account number in the uploaded file"}, status=500)
             
        # Find Bank object
        try:
            bank = Bank.objects.get(account_number=acc_no)
        except Bank.DoesNotExist:
            return JsonResponse({"error": f"Bank account number {acc_no} not found in system. Please add it to a Bank record."}, status=500)

        # Common processing
        df["idx"] = df.groupby(df["date"].dt.date).cumcount() + 1 
        df['"desc"'] = df["desc"].copy()
        df = df[["date","ref",'"desc"',"amt","idx"]]
        df["bank"] = bank.id # Use bank ID from the found bank object
        df["date"] = df["date"].dt.date
        df = df[df.amt != ""][df.amt.notna()]
        
        # Clean amount
        # df.amt is already numeric from read_csv usually, but let's ensure
        df["amt"] = df["amt"].astype(str).str.replace(",","")
        df["amt"] = pd.to_numeric(df["amt"], errors='coerce').fillna(0)
        df["amt"] = df["amt"].round()
        df = df[df.amt != 0]
        
        bank_statements = []
        for _, row in df.iterrows():
            obj = BankStatement(
                date=row['date'],
                idx=row['idx'],
                ref=row['ref'],
                desc=row['"desc"'],
                amt=row['amt'],
                bank_id=row['bank'],
            )
            obj.add_event("uploaded_from_statement",by = request.user.pk)
            bank_statements.append(obj)
        
        bank_statements = BankStatement.objects.bulk_create(bank_statements, ignore_conflicts=True)
        bank_statement_ids = [ BankStatement.objects.get(bank=obj.bank,idx=obj.idx,date=obj.date).pk 
                                        for obj in bank_statements ]
        bank_qs = BankStatement.objects.filter(id__in = bank_statement_ids)
        for company in bank.companies.all() :
            try:
                auto_match_upi(company.pk,bank_qs)
            except Exception as e :
                print(f"Failed to auto match UPI for company {company.pk}: {e}")

        smart_match(bank_qs.filter(type__isnull=True))
        stats = list(bank_qs.values("type").annotate(count=Count("amt"), total=Sum("amt")).order_by("-count"))
        return JsonResponse({"status" : "success" , "stats" : stats})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def auto_match_upi(company_id,bank_qs):
    qs = bank_qs.filter(Q(type__isnull=True)|Q(type="upi"))
    # TODO: Is the below safe ?
    qs.filter(Q(desc__icontains="cash") & Q(desc__icontains="deposit")).update(type="cash_deposit")
    if not qs.exists() :
        return JsonResponse({"error" : "No UPI transactions to match"},status=500)
    fromd = qs.aggregate(Min("date"))["date__min"]
    tod = qs.aggregate(Max("date"))["date__max"]
    try :
        upi_statement:pd.DataFrame = Ikea(company_id).upi_statement(fromd - datetime.timedelta(days = 3),tod)
    except Exception as e :
        raise Exception("Failed to fetch UPI statement")
    upi_statement["FOUND"] = "No"
    upi_statement["PAYMENT ID"] = upi_statement["PAYMENT ID"].astype(str).str.split(".").str[0]
    for bank_obj in qs.all() : 
        for _,row in upi_statement.iterrows() : 
            if (row["FOUND"] == "No") and (row["PAYMENT ID"] in bank_obj.desc) : 
                bank_obj.type = "upi"
                bank_obj.add_event("upi_auto_matched")
                bank_obj.save()
                upi_statement.loc[_,"FOUND"] = "Yes"
                
    upi_during_period = upi_statement[(upi_statement["COLLECTED DATE"].dt.date >= fromd)] 
    upi_before_period = upi_statement[(upi_statement["COLLECTED DATE"].dt.date < fromd)]         
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=UPI Matching.xlsx'
    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        upi_during_period[upi_during_period["FOUND"] == "No"].to_excel(writer,sheet_name="Un-Matched UPI (Current)",index=False)
        upi_during_period[upi_during_period["FOUND"] == "Yes"].to_excel(writer,sheet_name="Matched UPI (Current)",index=False)
        upi_before_period[upi_before_period["FOUND"] == "Yes"].to_excel(writer,sheet_name=f"Matched UPI (Before)",index=False)
    
    return response

@api_view(["POST"])
def auto_match_upi_view(request):
    company_id = request.data.get("company")
    tod = datetime.date.today()
    fromd = tod - datetime.timedelta(days = 15)
    banks = Bank.objects.filter(companies__name = company_id)
    bank_qs = BankStatement.objects.filter(date__gte = fromd,date__lte = tod,bank__in = banks)
    response = auto_match_upi(company_id,bank_qs)
    return response

@api_view(["POST"])
def auto_match_neft(request) : 
    bankstatement_id = request.data.get("bankstatement_id")
    party_id = request.data.get("party_id")
    company_id = request.data.get("company")
    bankstatement_obj = BankStatement.objects.get(id = bankstatement_id)
    party_name = PartyReport.objects.get(code = party_id,company_id = company_id).name
    matched_invoices = find_neft_match(bankstatement_obj,company_id,party_id,1)

    if len(matched_invoices) == 0 :
        return JsonResponse({"error" : "No matching invoices found."},status=500)
    if len(matched_invoices) == 1 :
        matched_invoices = matched_invoices[0]
        return JsonResponse({"status": "success", "matched_outstanding": 
                                [{"bill" : inv["inum"],  "party" : party_name, "balance" : inv["balance"], 
                                "amt" : round(inv["balance"]) } for inv in matched_invoices]})
    else : 
        return JsonResponse({"error" : "Multiple matches found."},status=500)

@api_view(["POST"])
def cheque_match(request) : 
    bank_id = request.data.get("bank_id")
    company_id = request.data.get("company")
    bank_entry = BankStatement.objects.get(id = bank_id)
    matches = find_cheque_match(bank_entry,[company_id])
    chqs = [ { "label" : str(chq) , "value" : chq.id } for chq in matches.all() ]
    return JsonResponse(chqs,safe=False)

def bounce_cheques(ikea,cheque_numbers):
    fromd = datetime.date.today() - datetime.timedelta(days = 7)
    tod = datetime.date.today()
    settle_coll:pd.DataFrame = ikea.download_settle_cheque(fromd = fromd, tod = tod) # type: ignore
    if "CHEQUE NO" not in settle_coll.columns : 
        return
    settle_coll = settle_coll[ settle_coll.apply(lambda row : (str(row["CHEQUE NO"]) in cheque_numbers) and (row["STATUS"] == "PENDING") ,axis=1) ]
    settle_coll["STATUS"] = "CANCELLED"
    settle_coll.to_csv("cancel_pending_cheques.csv",index=False)
    if len(settle_coll) == 0 : 
        return 
    with BytesIO() as f : 
        settle_coll.to_excel(f,index=False)
        f.seek(0)
        res = ikea.upload_settle_cheque(f)

def create_cheques(ikea,bankstatement_objs: list[BankStatement],files_dir) -> tuple[pd.DataFrame, dict[str,dict[str,str]]]:
    coll:pd.DataFrame = ikea.download_manual_collection() # type: ignore
    errors = defaultdict(dict)
    manual_rows = []
    for bank_obj in bankstatement_objs:
        temp_rows = []
        cheque_number = bank_obj.statement_id
        if cheque_number is None : 
            raise Exception("There is no cheque number (statement_id) assigned for BankStatement {}".format(bank_obj.pk))
        for coll_obj in bank_obj.all_collection:
            bill_no  = coll_obj.bill
            row = coll[coll["Bill No"] == bill_no].copy()
            if len(row) == 0 : 
                errors[cheque_number][bill_no] = "Bill not found in manual collection"
                continue

            # row = row.iloc[0]
            if row.iloc[0]["Collection Code"].lower() == "unassigned" : 
                errors[cheque_number][bill_no] = "Unassigned collection code"
                continue

            if row.iloc[0]["O/S Amount"] + 0.5 < coll_obj.amt : 
                errors[cheque_number][bill_no] = f"O/S Amount Rs.{row['O/S Amount']} < Collection Amount Rs.{coll_obj.amt}"
                continue

            row["Mode"] = "Cheque/DD"
            row["Retailer Bank Name"] = "KVB 650"
            row["Chq/DD Date"]  = bank_obj.date.strftime("%d/%m/%Y")
            chq_no = bank_obj.statement_id
            row["Chq/DD No"] = chq_no
            row["Amount"] = coll_obj.amt
            temp_rows.append(row)

        if len(errors[cheque_number]) == 0 : 
            manual_rows += temp_rows

    if len(manual_rows) == 0 : 
        return pd.DataFrame(), errors 

    #Remove all manual collection entry if a single collection or bill has an error for that bank statement obj
    manual_coll = pd.concat(manual_rows) #type: ignore
    manual_coll["Collection Date"] = datetime.date.today()
    manual_coll.to_excel(f"{files_dir}/manual_collection.xlsx")
    
    f = BytesIO()
    manual_coll.to_excel(f,index=False)
    f.seek(0)
    res = ikea.upload_manual_collection(f)
    cheque_upload_status = pd.read_excel(ikea.fetch_durl_content(res["ul"]))
    cheque_upload_status.to_excel(f"{files_dir}/cheque_upload_status.xlsx")
    error_coll = cheque_upload_status[cheque_upload_status["Status"] != "Success"]
    for _,row in error_coll.iterrows() : 
        errors[ str(row["Chq/DD No"]).split('.')[0] ][row["BillNumber"]] = row["Error Description"]
    return cheque_upload_status,errors

def settle_cheques(ikea,cheque_numbers,files_dir) -> tuple[pd.DataFrame, list[str] ,dict[str,str]] : 
    """Settle Cheques and returns list of cheque numbers that were successfully settled and errors"""
    settle_coll:pd.DataFrame = ikea.download_settle_cheque() # type: ignore
    if "CHEQUE NO" not in settle_coll.columns : 
        return pd.DataFrame() , [] , {}
    settle_coll = settle_coll[ settle_coll.apply(lambda row : str(row["CHEQUE NO"]) in cheque_numbers ,axis=1) ]
    settle_coll["STATUS"] = "SETTLED"
    print(settle_coll)
    if len(settle_coll) == 0 :
        return pd.DataFrame() , [] , {}
         
    f = BytesIO()
    settle_coll.to_excel(f,index=False)
    f.seek(0)
    res = ikea.upload_settle_cheque(f)
    print(res)
    bytes_io = ikea.fetch_durl_content(res["ul"])
    cheque_settlement = pd.read_excel(bytes_io)
    cheque_settlement.to_excel(f"{files_dir}/cheque_settlement.xlsx")

    settled = cheque_settlement[cheque_settlement["STATUS"] == "SETTLED"]
    not_settled = cheque_settlement[cheque_settlement["STATUS"] != "SETTLED"]
    errors:dict[str,str] = {}
    for _,row in not_settled.iterrows() : 
        errors[str(row["Cheque No"]).split('.')[0]] = row["Error Description"]
    settled_cheque_numbers = [ str(i).split('.')[0] for i in set(settled["Cheque No"].values) ]
    return cheque_settlement, settled_cheque_numbers ,errors 

@api_view(["POST"])
def push_collection(request) :
    data = request.data
    company_id = data.get("company")
    company = Company.objects.get(name = company_id)
    user = request.user.pk
    ids = list(data.get("ids"))

    bank_entries = [ obj for obj in BankStatement.objects.filter(
                              id__in = ids, type__in = ["cheque","neft"], company_id = company_id
                            ).exclude(cheque_status = "bounced") if obj.pushed_status == "not_pushed"] #Dont allow partial

    #Get free ids and assigning map
    already_assigned_ids = BankStatement.objects.filter(company_id = company_id).values_list("statement_id",flat=True).distinct()
    free_ids = list(set(range(100000,999999)) - set([int(i) for i in already_assigned_ids if i]))
    unassigned_bank_entries = [ obj for obj in bank_entries if not obj.statement_id ]
    assign_ids = { obj.pk : str(free_id) for obj,free_id in zip(unassigned_bank_entries,free_ids) }

    for obj in bank_entries : 
        if obj.pk in assign_ids : 
            obj.statement_id = assign_ids[obj.pk]
            obj.save()

    ikea = Ikea(company_id)
    files_dir = os.path.join(settings.MEDIA_ROOT, "bank", company_id)
    os.makedirs(files_dir, exist_ok=True)

    cheque_numbers =  [ obj.statement_id for obj in bank_entries if obj.statement_id]
    print(cheque_numbers)

    #Bounce cheque if already in pending state 
    # bounce_cheques(ikea,cheque_numbers)

    #Create cheques using manual collection upload
    cheque_upload_status, cheque_creation_errors = create_cheques(ikea,bank_entries,files_dir)

    print(cheque_creation_errors,cheque_upload_status)

    #We also push the pending cheque if the statement id is in the bank queryset which user selected
    #Note : cheque_settlement_errors is the errors after uplaoding settlement ,
    #so if the cheque number is not present in the settlement it will not be in the errors
    cheque_settlement, settled_cheque_numbers ,cheque_settlement_errors = settle_cheques(ikea,cheque_numbers,files_dir)

    #Write down the event with success or errors 
    some_failure = False
    for cheque_number in cheque_numbers : 
        obj = BankStatement.objects.get(statement_id = cheque_number,company_id = company_id)
        if cheque_number in settled_cheque_numbers : 
            obj.add_event("pushed",by = user)
        else :
            some_failure = True
            if cheque_number in cheque_settlement_errors : 
                obj.add_event("cheque_settlement_failed",message = f"Cheque not settled : {cheque_settlement_errors[cheque_number]}",by = user)
            elif len(cheque_creation_errors[cheque_number]) > 0  : 
                message = "\n".join([ f"{bill_no} : {error}" for bill_no, error in cheque_creation_errors[cheque_number].items() ])
                obj.add_event("cheque_creation_failed",message = f"Cheque not created :\n {message}",by = user)
            else : 
                obj.add_event("pushed_failed",message = "UnKnown Reason",by = user)
        obj.save()
        
    #TODO: Do we need this ?
    # for _,row in sucessfull_coll.iterrows() : 
    #     chq_no = row["Chq/DD No"]
    #     bill_no = row["BillNumber"]
    #     bank_entry = BankStatement.objects.get(statement_id = chq_no,company_id = company_id)
    #     BankCollection.objects.filter(Q(bank_entry = bank_entry) | Q(cheque_entry__bank_entry = bank_entry)).filter(
    #                                             bill = bill_no).update(pushed = True)

    CollectionReport.update_db(ikea,company,DateRangeArgs(fromd = datetime.date.today() , tod = datetime.date.today()))
    OutstandingReport.update_db(ikea,company,EmptyArgs())

    PUSH_CHEQUE_FILE = os.path.join(files_dir,"push_cheque_ikea.xlsx")
    with pd.ExcelWriter(open(PUSH_CHEQUE_FILE,"wb+"), engine='xlsxwriter') as writer:
        cheque_upload_status.to_excel(writer,sheet_name="Manual Collection")
        cheque_settlement.to_excel(writer,sheet_name="Cheque Settlement")

    return JsonResponse({ "status": "success" if not some_failure else "partial_success" , 
                            "errors" : [cheque_creation_errors,cheque_settlement_errors],
                          "filepath" : get_media_url(PUSH_CHEQUE_FILE) })

@api_view(["POST"])
def unpush_collection(request) : 
    bankstatement_id = request.data.get("bankstatement_id")
    obj = BankStatement.objects.get(id = bankstatement_id)
    if obj.statement_id is None : return JsonResponse({"error" : "Bank Statement is not pushed & has null statement_id field"}, status = 500)
    if obj.company is None : return JsonResponse({"error" : "Bank Statement is not associated with any company"}, status = 500)
    ikea = Ikea(obj.company.pk)
    qs = obj.all_collection
    if qs.count() : 
        bill_chq_pairs = [ (obj.statement_id,bank_coll.bill) for bank_coll in qs.all() ]
        dates = obj.ikea_collection.aggregate(fromd = Min("date"), tod = Max("date"))
        fromd,tod = dates["fromd"],dates["tod"]
        if fromd is None or tod is None : return JsonResponse({"error" : "No Ikea Collection Found for the statement id"}, status = 500)

        settle_coll:pd.DataFrame = ikea.download_settle_cheque("ALL",fromd,tod) # type: ignore
        settle_coll = settle_coll[ settle_coll.apply(lambda row : (str(row["CHEQUE NO"]),row["BILL NO"]) in bill_chq_pairs ,axis=1) ]
        settle_coll["STATUS"] = "BOUNCED"
        with BytesIO() as f : 
            settle_coll.to_excel(f,index=False)
            f.seek(0)
            res = ikea.upload_settle_cheque(f)
            obj.add_event("unpushed",by = request.user.pk)
            obj.save()
        CollectionReport.update_db(ikea,obj.company,DateRangeArgs(fromd = fromd ,tod = tod))
        OutstandingReport.update_db(ikea,obj.company,EmptyArgs())
    return JsonResponse({"status" : "success"})

@api_view(["POST"])
def refresh_bank(request):
    companies = request.user.companies.all()
    for company in companies : 
        ikea = Ikea(company.pk)
        CollectionReport.update_db(ikea,company,DateRangeArgs(
            fromd = datetime.date.today() - datetime.timedelta(days=7),
            tod = datetime.date.today()))
        OutstandingReport.update_db(ikea,company,EmptyArgs())
    return JsonResponse({"status" : "success"})


@api_view(["POST"])
def bank_summary(request):
    fromd = datetime.datetime.strptime(request.data.get("fromd"),"%Y-%m-%d").date()
    tod = datetime.datetime.strptime(request.data.get("tod"),"%Y-%m-%d").date()
    should_download_collection = request.data.get("download_collection")

    companies = request.user.companies.all()
    banks = Bank.objects.filter(companies__in=companies).distinct()

    bank_totals = {}
    bank_dfs = {}
    bank_qs = BankStatement.objects.filter(bank__in = banks,date__gte = fromd,date__lte = tod)
    coll_qs = CollectionReport.objects.filter(date__gte = fromd,date__lte = tod,company__in = companies)

    company_wise_bank_chq_numbers = defaultdict(list)
    for bank in banks : 
        bank_total = defaultdict(int)
        df = []
        def create_row(obj,notes = "",party_name="",bills = "",coll_date = "") : 
            df.append([obj.date,obj.desc,obj.amt,obj.type,notes,party_name,coll_date,bills])
        for obj in bank_qs.filter(bank = bank) : 
            if obj.type in ["cheque","neft"] : 
                ikea_coll_amt = 0
                q = coll_qs.filter(bank_entry_id = obj.statement_id,company_id = obj.company.pk)
                ikea_collections = list(q)
                bill_collections = list(obj.all_collection)
                party_name = bill_collections[0].party
                bills = ",".join([bill.bill for bill in bill_collections])
                if "queen" in party_name.lower() : 
                    print(party_name,obj.statement_id,obj.company.pk,[ikea_coll.amt for ikea_coll in ikea_collections])
                    print(q.query.__str__())

                if obj.statement_id and obj.company : 
                   company_wise_bank_chq_numbers[obj.company.pk].append(obj.statement_id)
                   ikea_coll_amt =  sum([ikea_coll.amt for ikea_coll in ikea_collections])
                if ikea_coll_amt == 0 : 
                   bank_total["not_pushed"] += int(obj.amt)
                   create_row(obj,f"not_pushed",party_name,bills)
                else :
                    pending_amt = obj.amt - ikea_coll_amt
                    bank_total["cheque"] += int(ikea_coll_amt)
                    notes = ""
                    if pending_amt > 0 : 
                        bank_total["cheque_diff"] += int(pending_amt)
                        notes = f"pushed : {ikea_coll_amt} , diff : {pending_amt}"
                    coll_date = ikea_collections[0].date
                    create_row(obj,notes,party_name,bills,coll_date)

            elif obj.type is not None : 
                bank_total[obj.type] += int(obj.amt)
                create_row(obj)
            else : 
                bank_total["not_saved"] += int(obj.amt)
                create_row(obj,"not_saved")
        bank_totals[bank.name] = bank_total
        bank_dfs[bank.name] = pd.DataFrame(df,columns = ["Date","Description","Amount","Type","Notes","Party","Coll Date","Bills",])

    ikea_totals = {}
    ikea_cheque_coll_dfs = {}
    for company in companies : 
        ikea = Ikea(company.pk)
        if should_download_collection :
            CollectionReport.update_db(ikea,company,DateRangeArgs(fromd = fromd,tod = tod))
        qs = coll_qs.filter(company = company)
        #Type Totals
        totals = list(qs.values("mode").annotate(amt = Sum("amt")).values("mode","amt"))
        ikea_totals[company.pk] = {total["mode"] : int(total["amt"]) for total in totals if total["mode"] not in ["cheque","neft"]}
        
        #Cheque subtype totals
        cheque_qs = qs.filter(mode__in = ["cheque","neft"])
        df = pd.DataFrame(cheque_qs.values("date","inum","party_name","amt","bank_entry_id").order_by("date","party_name"))
        auto_chq_nos = company_wise_bank_chq_numbers[company.pk]
        df["type"] = df["bank_entry_id"].apply(lambda x : "auto" if x and (x in auto_chq_nos) else "manual")
        ikea_cheque_coll_dfs[company.pk] = df
        df["amt"] = df["amt"].astype(int)
        auto_chq_total = df[df["type"] == "auto"]["amt"].sum()
        manual_chq_total = df[df["type"] == "manual"]["amt"].sum()
        ikea_totals[company.pk]["auto_chq"] = auto_chq_total
        ikea_totals[company.pk]["manual_chq"] = manual_chq_total


    totals_to_df = lambda totals : pd.DataFrame([ [entity,type,amt] for entity,subtotals in totals.items() for type,amt in subtotals.items()] , columns = ["Entity","Type","Amount"])
    df_group_entity = lambda df : df.pivot_table(index = "Entity",columns = "Type",values = "Amount",aggfunc = "sum",margins=True,margins_name='Total').reset_index()
    reorder_columns = lambda df, order: df.reindex(
        columns=[col for col in order if col in df.columns] + 
                [col for col in df.columns if col not in order]
    )

    ikea_totals = reorder_columns(df_group_entity(totals_to_df(ikea_totals)),["Entity","auto_chq","upi","cash","manual_chq"])
    bank_totals = reorder_columns(df_group_entity(totals_to_df(bank_totals)),["Entity","cheque","upi","cash_deposit"])
    #TODO: total_comparison = {}

    files_dir = os.path.join(settings.MEDIA_ROOT, "bank", request.user.pk)
    os.makedirs(files_dir, exist_ok=True)
    fpath = os.path.join(files_dir,"summary.xlsx")

    with pd.ExcelWriter(fpath, engine='xlsxwriter') as writer : 
        addtable(writer = writer , sheet = "Summary" , name = ["IKEA","BANK"]  ,  data = [ikea_totals,bank_totals])  
        for bank_name,df in bank_dfs.items() : 
            df.to_excel(writer, sheet_name=bank_name,index=False)
        for company,df in ikea_cheque_coll_dfs.items() : 
            df.to_excel(writer, sheet_name=company,index=False)

    return JsonResponse({"status" : "success", "filepath" : get_media_url(fpath)})
