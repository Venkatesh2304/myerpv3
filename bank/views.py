
from report.models import SalesRegisterReport
from collections import defaultdict
from report.models import DateRangeArgs
from report.models import CollectionReport
from django.conf import settings
from io import BytesIO
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
import joblib

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
    print(best_label,best_prob)
    return company,party_id,best_prob

def find_neft_match(bankstatement_obj,company_id,party_id):
    allowed_diff = 0.5
    amt = bankstatement_obj.amt
    outstandings = list(OutstandingReport.objects.filter(
        party_id = party_id,
        company_id = company_id,
        balance__gte =  1,
        balance__lte = amt + allowed_diff,
        bill_date__gte = datetime.date.today() - datetime.timedelta(days=60)
    ).values_list("inum","balance").order_by("bill_date"))
    pending_outstandings = []
    for inum,balance in outstandings :
        pending_collection = 0 
        for coll in BankCollection.objects.filter(bill = inum) :
            if coll.company != company_id : continue 

            pushed = None
            if coll.bank_entry : 
                pushed = coll.bank_entry.pushed
            elif coll.cheque_entry : 
                bank_entry = getattr(coll.cheque_entry, "bank_entry", None)
                pushed = bank_entry.pushed if bank_entry else False
            else : 
                pass

            if pushed == False : 
                pending_collection += balance
        new_balance = round(balance - pending_collection)
        if new_balance > 0 :
            pending_outstandings.append((inum,new_balance))
    pending_outstandings = outstandings
    #Try all combination of outstandings whre each row has keys inum and balance.
    #allow if the difference is lesss than allowed_difference with amt

    # if len(outstandings) > 20 :
    #     return JsonResponse({ "error" : "Too many outstandings to match." },status=500)

    pending_outstandings = pending_outstandings[:20]
    matched_invoices = []
    for r in range(1, len(pending_outstandings) + 1):
        for combo in combinations(pending_outstandings, r):
            total_balance = sum(item[1] for item in combo)
            if abs(total_balance - amt) <= allowed_diff:
                print("Found match",combo,total_balance,amt)
                matched_invoices.append([{"inum": item[0], "balance": item[1]} for item in combo])
    return matched_invoices
    
@api_view(["POST"])
def smart_match(request):
    ids = request.data.get("ids")
    queryset = BankStatement.objects.filter(id__in = ids)
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
                matched_invoices = find_neft_match(obj,company_id,party_id)
                if len(matched_invoices) == 1 : 
                    obj.type = "neft"
                    obj.company_id = company_id
                    BankCollection.objects.filter(bank_entry_id = obj.pk).delete()
                    obj.save()
                    for inv in matched_invoices[0] : 
                        BankCollection.objects.create(bank_entry = obj, bill = inv["inum"],
                                                                            amt = inv["balance"]).save()
            elif len(chq_matches) == 1 : 
                obj.type = "cheque"
                obj.cheque_entry = chq_matches[0]
                obj.cheque_status = "passed"
                obj.company_id = chq_matches[0].company_id
                obj.save()
            else : 
                continue 
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
            bank_statements.append(BankStatement(
                date=row['date'],
                idx=row['idx'],
                ref=row['ref'],
                desc=row['"desc"'],
                amt=row['amt'],
                bank_id=row['bank'],
            ))
        
        BankStatement.objects.bulk_create(bank_statements, ignore_conflicts=True)
        return JsonResponse({"status" : "success"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@api_view(["POST"])
def auto_match_upi(request):
    company_id = request.data.get("company")
    banks = Bank.objects.filter(companies__name = company_id)
    qs = BankStatement.objects.filter(date__gte = datetime.date.today() - datetime.timedelta(days=15),bank__in = banks) 
    qs.filter(Q(desc__icontains="cash") & Q(desc__icontains="deposit")).update(type="cash_deposit")
    qs = qs.filter(Q(type__isnull=True)|Q(type="upi"))
    fromd = qs.aggregate(Min("date"))["date__min"]
    tod = qs.aggregate(Max("date"))["date__max"]
    upi_statement:pd.DataFrame = Ikea(company_id).upi_statement(fromd - datetime.timedelta(days = 3),tod)
    upi_statement["FOUND"] = "No"
    upi_statement["PAYMENT ID"] = upi_statement["PAYMENT ID"].astype(str).str.split(".").str[0]
    for bank_obj in qs.all() : 
        for _,row in upi_statement.iterrows() : 
            if (row["FOUND"] == "No") and (row["PAYMENT ID"] in bank_obj.desc) : 
                bank_obj.type = "upi"
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
def auto_match_neft(request) : 
    bankstatement_id = request.data.get("bankstatement_id")
    party_id = request.data.get("party_id")
    company_id = request.data.get("company")
    bankstatement_obj = BankStatement.objects.get(id = bankstatement_id)
    party_name = PartyReport.objects.get(code = party_id,company_id = company_id).name
    matched_invoices = find_neft_match(bankstatement_obj,company_id,party_id)

    if len(matched_invoices) == 0 :
        return JsonResponse({"error" : "No matching invoices found."},status=500)
    if len(matched_invoices) == 1 :
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

@api_view(["POST"])
def push_collection(request) :
    data = request.data
    company_id = data.get("company")
    company = Company.objects.get(name = company_id)
    ids = list(data.get("ids"))

    bank_entries = [ obj for obj in BankStatement.objects.filter(
                              id__in = ids, type__in = ["cheque","neft"], company_id = company_id
                            ).exclude(cheque_status = "bounced") if not obj.pushed ]
    unassigned_bank_entries = [ obj for obj in bank_entries if not obj.statement_id ]

    already_assigned_ids = BankStatement.objects.filter(company_id = company_id).values_list("statement_id",flat=True).distinct()
    free_ids = list(set(range(100000,999999)) - set([int(i) for i in already_assigned_ids if i]))
    for bank_entry,free_id in zip(unassigned_bank_entries,free_ids) : 
        bank_entry.statement_id = str(free_id)
        bank_entry.save()

    bank_entry_ids = [ obj.id for obj in bank_entries ]
    cheque_entry_ids = BankStatement.objects.filter(id__in = bank_entry_ids).values_list("cheque_entry_id",flat=True)
    queryset = BankCollection.objects.filter(Q(bank_entry_id__in = bank_entry_ids) | Q(cheque_entry_id__in = cheque_entry_ids))

    ikea = Ikea(company_id)
    coll:pd.DataFrame = ikea.download_manual_collection() # type: ignore
    manual_coll = []
    bill_chq_pairs = []
    for coll_obj in queryset.all():
        if coll_obj.bank_entry is None and coll_obj.cheque_entry is None : 
            raise Exception("No bank entry or cheque entry found for collection object.")
        bank_obj = coll_obj.bank_entry or coll_obj.cheque_entry.bank_entry
        bill_no  = coll_obj.bill
        row = coll[coll["Bill No"] == bill_no].copy()
        row["Mode"] = "Cheque/DD"
        row["Retailer Bank Name"] =  coll_obj.cheque_entry.bank.upper() if coll_obj.cheque_entry else "KVB 650"
        row["Chq/DD Date"]  = bank_obj.date.strftime("%d/%m/%Y")
        chq_no = bank_obj.statement_id
        row["Chq/DD No"] = chq_no
        row["Amount"] = coll_obj.amt
        manual_coll.append(row)
        bill_chq_pairs.append((chq_no,bill_no))

    manual_coll = pd.concat(manual_coll)
    manual_coll["Collection Date"] = datetime.date.today()
    f = BytesIO()
    manual_coll.to_excel(f,index=False)
    f.seek(0)
    files_dir = os.path.join(settings.MEDIA_ROOT, "bank", company_id)
    os.makedirs(files_dir, exist_ok=True)
    manual_coll.to_excel(f"{files_dir}/manual_collection.xlsx")
    res = ikea.upload_manual_collection(f)
    cheque_upload_status = pd.read_excel(ikea.fetch_durl_content(res["ul"]))
    cheque_upload_status.to_excel(f"{files_dir}/cheque_upload_status.xlsx")
    sucessfull_coll = cheque_upload_status[cheque_upload_status["Status"] == "Success"]

    settle_coll:pd.DataFrame = ikea.download_settle_cheque() # type: ignore
    SETTLE_CHEQUE_FILE = os.path.join(files_dir,"settle_cheque.xlsx")
    settle_coll.to_excel(SETTLE_CHEQUE_FILE)
    if "CHEQUE NO" not in settle_coll.columns : 
        return JsonResponse({"error" : "No Cheques to Settle", "filepath" :SETTLE_CHEQUE_FILE},status=500)
    settle_coll = settle_coll[ settle_coll.apply(lambda row : (str(row["CHEQUE NO"]),row["BILL NO"]) in bill_chq_pairs ,axis=1) ]
    settle_coll["STATUS"] = "SETTLED"
    f = BytesIO()
    settle_coll.to_excel(f,index=False)
    f.seek(0)
    res = ikea.upload_settle_cheque(f)
    bytes_io = ikea.fetch_durl_content(res["ul"])
    cheque_settlement = pd.read_excel(bytes_io)
    cheque_settlement.to_excel(f"{files_dir}/cheque_settlement.xlsx")

    #TODO: Do we need this ?
    # for _,row in sucessfull_coll.iterrows() : 
    #     chq_no = row["Chq/DD No"]
    #     bill_no = row["BillNumber"]
    #     bank_entry = BankStatement.objects.get(statement_id = chq_no,company_id = company_id)
    #     BankCollection.objects.filter(Q(bank_entry = bank_entry) | Q(cheque_entry__bank_entry = bank_entry)).filter(
    #                                             bill = bill_no).update(pushed = True)

    CollectionReport.update_db(ikea,company,DateRangeArgs(
        fromd = datetime.date.today() - datetime.timedelta(days=1),
        tod = datetime.date.today()))

    PUSH_CHEQUE_FILE = os.path.join(files_dir,"push_cheque_ikea.xlsx")
    with pd.ExcelWriter(open(PUSH_CHEQUE_FILE,"wb+"), engine='xlsxwriter') as writer:
        cheque_upload_status.to_excel(writer,sheet_name="Manual Collection")
        cheque_settlement.to_excel(writer,sheet_name="Cheque Settlement")
    return JsonResponse({ "filepath" : PUSH_CHEQUE_FILE })


@api_view(["POST"])
def refresh_bank(request) : 
    company_id = request.data.get("company")
    company = Company.objects.get(name = company_id)
    ikea = Ikea(company_id)
    CollectionReport.update_db(ikea,company,DateRangeArgs(
        fromd = datetime.date.today() - datetime.timedelta(days=1),
        tod = datetime.date.today()))
    return JsonResponse({"status" : "success"})
