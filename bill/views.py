from django.db.models.aggregates import Count
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
import traceback
from django.template.defaultfilters import default
from bill.models import Bill
from report.models import DateRangeArgs
from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.decorators import api_view
from . import models
import datetime
from core.models import Company
from django.db import transaction
from custom.classes import Billing
from report.models import CollectionReport, OutstandingReport, EmptyArgs
import time
import contextlib
from bill.credit_logic import PartyCreditLogic
from bill.models import PartyCredit

class ProcessStats:
    def __init__(self):
        self.stats = {}

    @contextlib.contextmanager
    def step(self, name):
        start = time.time()
        try:
            yield
            self.stats[name] = round(time.time() - start, 2)
        except Exception:
            self.stats[name] = -1
            raise
            self.stats[name] = -1
            raise

@api_view(["POST"])
def get_order(request):
    data = request.data
    company_id = data.get("company")
    order_date = data.get("order_date")

    if not company_id:
        return JsonResponse({"error": "Company ID is required"}, status=400)
    
    if not order_date : 
        return JsonResponse({"error": "Order Date is required"}, status=400)
    else:
        order_date = datetime.datetime.strptime(order_date, "%Y-%m-%d").date()

    tracker = ProcessStats()
    
    # Short transaction to acquire lock
    try:
        with transaction.atomic():
            # Use today's date for uniqueness
            today = datetime.date.today()
            billing_obj, created = models.Billing.objects.select_for_update().get_or_create(
                company_id=company_id, 
                date=today,
                defaults={"ongoing": True, "process": "getorder"}
            )
            
            if not created and billing_obj.ongoing:
                return JsonResponse({"error": "Billing process is already ongoing"}, status=400)

            billing_obj.order_date = order_date
            billing_obj.ongoing = True
            billing_obj.process = "getorder"
            billing_obj.market_order_data = [] #For safety, to remove previous market values
            billing_obj.order_hash = "dummy"
            billing_obj.user = request.user.username
            billing_obj.last_bills = []
            billing_obj.save()
                
    except Exception as e:
        return JsonResponse({"error": f"Failed to acquire lock: {str(e)}"}, status=500)

    try:
        # Long running process (outside transaction)
        with tracker.step("Initialisation"):
            billing = Billing(user=company_id)
            
        with tracker.step("Sync"):
            billing.Sync()
            
        with tracker.step("Collection"):
            # Pass previous collections from DB
            billing.Collection(order_date, previous_collections=billing_obj.pushed_collections)
        
        # Update pushed_collections in DB
        billing_obj.pushed_collections = list(set(billing_obj.pushed_collections + billing.pushed_collection_party_ids))
        billing_obj.save()

        with tracker.step("Reports"):
            today = datetime.date.today()
            from report.models import DateRangeArgs
            from report.models import EmptyArgs
            from report.models import CollectionReport
            from report.models import OutstandingReport
            
            company = Company.objects.get(pk=company_id)
            # Update Reports
            #TODO
            try :
                CollectionReport.update_db(billing, company, DateRangeArgs(today, today))
            except :
                pass
            OutstandingReport.update_db(billing, company, EmptyArgs())

        with tracker.step("Order"):
            order_data:list = billing.get_market_order(order_date)
            party_ids = [item.get('pc') for item in order_data if item.get('pc')]
            credit_logic = PartyCreditLogic(company_id, party_ids)
        
        
        from itertools import groupby
        from operator import itemgetter
        
        # Sort by 'on' (Order Number) to ensure groupby works correctly
        order_data.sort(key=itemgetter('on'))
        
        processed_orders = []
        for order_no, items in groupby(order_data, key=itemgetter('on')):
            items_list = list(items)
            first_item = items_list[0]
            party_code = first_item.get('pc')
            
            #Skip wholesale beats
            if "WHOLE" in first_item.get('m', "") : 
                continue

            lines_count = len(items_list)
            bill_value = sum((item.get('cq') or 0) * (item.get('t') or 0) for item in items_list)
            allocated_value = sum((item.get('aq') or 0) * (item.get('t') or 0) for item in items_list)

            # Phone: Fetch from PartyReport
            phone = "-"
            try:
                from report.models import PartyReport
                party = PartyReport.objects.get(company_id=company_id, code=first_item.get('pc'))
                phone = party.phone or "-"
            except PartyReport.DoesNotExist:
                pass
            
            # OS: OutstandingReport
            os_list = []
            try:
                outstanding_bills = OutstandingReport.objects.filter(
                    company_id=company_id, 
                    party_id=party_code, 
                    beat=first_item.get('m')
                )
                os_list = [(round(bill.balance),(today - bill.bill_date).days) for bill in outstanding_bills]
            except Exception:
                pass

            os_val = "/ ".join([f"{bal}*{days}" for bal,days in os_list]) or "-"

            # Coll: CollectionReport
            coll_list = []
            try:
                collections = CollectionReport.objects.filter(
                    company_id=company_id, 
                    party_name=first_item.get('p'), 
                    date=today
                )
                coll_list = [(round(coll.amt or 0), (today - coll.bill_date).days) for coll in collections]
            except Exception:
                pass

            coll_val = "/ ".join([f"{amt}*{days}" for amt,days in coll_list]) or "-"
            
            allow_order,warning = credit_logic.allow_order(party_code, os_list, coll_list, allocated_value)
            warning = "\n".join(warning)

            partial_order = (billing_obj.order_values.get(order_no, 0) - bill_value) > 200

            class OrderType :
                Partial = "partial"
                LessThanConfig = "less_than_config"
                Normal = "normal"
                
            if allocated_value < 200 :
                order_category = OrderType.LessThanConfig
            elif partial_order :
                order_category = OrderType.Partial
            else :
                order_category = OrderType.Normal

            if order_category != OrderType.Normal : 
                allow_order = False

            processed_orders.append({
                "order_no": order_no,
                "party": first_item.get('p'),
                "party_id": party_code,
                "lines": lines_count,
                "bill_value": round(bill_value, 2),
                "allocated_value": round(allocated_value, 2),
                "salesman": first_item.get('s'),
                "beat": first_item.get('m'),
                "type": first_item.get('ot'),
                "phone": phone,
                "OS": os_val,
                "coll": coll_val,
                "allow_order": allow_order,
                "warning" : warning,
                "order_category": order_category
            })

        processed_orders.sort(key=lambda x: (x["allow_order"],x["party"]))
        # Populate order_values from processed_orders
        order_values = {order["order_no"]: order["bill_value"] for order in processed_orders} 
        
        # Store state in DB (Short transaction for update)
        # Note: We can just save here as we are the only ones running due to ongoing flag
        billing_obj.market_order_data = order_data
        billing_obj.order_values = order_values | billing_obj.order_values
        
        import hashlib
        import json
        raw_data_json = json.dumps(order_data, sort_keys=True)
        data_hash = hashlib.md5(raw_data_json.encode('utf-8')).hexdigest()
        billing_obj.order_hash = data_hash
        billing_obj.save()

        return JsonResponse({"orders": processed_orders, "hash": data_hash, "process": tracker.stats})
    except Exception as e:
        return JsonResponse({"error": str(e), "process": tracker.stats}, status=500)
    finally:
        # Release lock
        if 'billing_obj' in locals() and billing_obj.ongoing: # Ensure billing_obj exists and was set to ongoing
            billing_obj.ongoing = False
            billing_obj.save()

@api_view(["POST"])
def post_order(request):
    data = request.data
    company_id = data.get("company")
    client_hash = data.get("hash")
    order_date = data.get("order_date")
    order_numbers = data.get("order_numbers")
    delete_orders = data.get("delete_orders")
    
    if not company_id:
        return JsonResponse({"error": "Company ID is required"}, status=400)
    
    if not client_hash:
         return JsonResponse({"error": "Hash is required"}, status=400)
         
    if not order_date:
         return JsonResponse({"error": "Order Date is required"}, status=400)
    else:
        order_date = datetime.datetime.strptime(order_date, "%Y-%m-%d").date()

    
    tracker = ProcessStats()

    # Short transaction to acquire lock
    try:
        with transaction.atomic():
            # Use today's date for uniqueness
            today = datetime.date.today()
            # We expect the billing object to exist for today (created by get_order)
            billing_obj = models.Billing.objects.select_for_update().get(company_id=company_id, date=today)
            
            if billing_obj.ongoing:
                return JsonResponse({"error": "Billing process is already ongoing"}, status=400)
            
            billing_obj.ongoing = True
            billing_obj.process = "postorder"
            billing_obj.user = request.user.username
            billing_obj.save()
    except models.Billing.DoesNotExist:
         return JsonResponse({"error": "Billing record not found. Please fetch orders first."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Failed to acquire lock: {str(e)}"}, status=500)

    try:
        # Validate Order Date
        if billing_obj.order_date != order_date:
            return JsonResponse({"error": "Order Date mismatch. Please refresh orders."}, status=400)
            
        # Validate Hash
        import hashlib
        import json
        stored_data = billing_obj.market_order_data
        if not stored_data:
             return JsonResponse({"error": "No market order data found. Please fetch orders first."}, status=400)
             
        
        if billing_obj.order_hash != client_hash:
             return JsonResponse({"error": "Data mismatch (Hash invalid). Please refresh orders."}, status=400)

        with tracker.step("Initialisation"):
            billing = Billing(company_id)
            
        with tracker.step("PrevBills"):
            billing.Prevbills()   
            
        with tracker.step("Order"):
            billing.post_market_order(stored_data, order_numbers, delete_orders)   
            
        with tracker.step("Delivery"):
            billing.Delivery()  
            
        with tracker.step("Report"):
             # Update Sales Register Report
             from report.models import SalesRegisterReport, DateRangeArgs
             today = datetime.date.today()
             company = Company.objects.get(pk=company_id)
             SalesRegisterReport.update_db(billing, company, DateRangeArgs(today, today))
             Bill.sync_with_salesregister(company,fromd = today,tod = today)


        # Stats
        
        # Override last_bills from local billing instance if available
        if hasattr(billing, 'bills') and billing.bills:
            billing_obj.last_bills = billing.bills
            billing_obj.save()

        return JsonResponse({
            "message": "Order posted successfully. Log saved.",
            "process": tracker.stats
        })
    except Exception as e:
        return JsonResponse({"error": str(e) + traceback.format_exc(), "process": tracker.stats}, status=500)
    finally:
        # Release lock
        if 'billing_obj' in locals() and billing_obj.ongoing:
            billing_obj.ongoing = False
            billing_obj.save()

@api_view(["GET", "POST"])
def manage_order(request):
    import hashlib
    import json
    
    data = request.data if request.method == "POST" else request.GET
    company_id = data.get("company")
    order_number = data.get("order")

    if not company_id:
        return JsonResponse({"error": "Company ID is required"}, status=400)
    
    if not order_number:
        return JsonResponse({"error": "Order Number is required"}, status=400)

    today = datetime.date.today()

    def generate_row_id(row):
        # Use MD5 of sorted JSON string for stable ID
        row_str = json.dumps(row, sort_keys=True)
        return hashlib.md5(row_str.encode('utf-8')).hexdigest()

    if request.method == "GET":
        try:
            billing_obj = models.Billing.objects.get(company_id=company_id, date=today)
            market_order_data = billing_obj.market_order_data or []
            
            # Filter rows for the given order number
            order_rows = [row for row in market_order_data if row.get('on') == order_number]
            
            response_data = []
            for row in order_rows:
                response_data.append({
                    "id": generate_row_id(row),
                    "p": row.get('p'),
                    "t": row.get('t'),
                    "cq": row.get('cq'),
                    "aq": row.get('aq'),
                    "qp": row.get('qp'),
                    "ar": row.get('ar'),
                    "bd": row.get('bd')
                })
            
            return JsonResponse(response_data, safe=False)
            
        except models.Billing.DoesNotExist:
            return JsonResponse({"error": "Billing record not found for today"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    if request.method == "POST":
        updates = data.get("items")
        if not updates or not isinstance(updates, dict):
             return JsonResponse({"error": "Items dictionary is required"}, status=400)

        try:
            with transaction.atomic():
                billing_obj = models.Billing.objects.select_for_update().get(company_id=company_id, date=today)
                
                if billing_obj.ongoing:
                    return JsonResponse({"error": "Billing process is ongoing. Please wait."}, status=400)

                billing_obj.ongoing = True
                billing_obj.process = "editing"
                billing_obj.save()

                market_order_data = billing_obj.market_order_data or []
                
                # Create a map of ID -> Row for O(1) lookup
                row_map = {
                    generate_row_id(row): row 
                    for row in market_order_data 
                    if row.get('on') == order_number
                }
                
                errors = []
                updated_count = 0

                for row_id, new_qp in updates.items():
                    row = row_map.get(row_id)
                    if not row:
                        errors.append(f"Row ID {row_id} not found")
                        continue

                    try:
                        new_qp = int(new_qp)
                    except (ValueError, TypeError):
                        errors.append(f"Invalid QP value for ID {row_id}")
                        continue

                    aq = row.get('aq', 0) or 0
                    if new_qp > aq:
                        errors.append(f"To order QTY ({new_qp}) > Allocated QTY ({aq}) for ID {row_id}")
                        continue
                    
                    row['qp'] = new_qp
                    updated_count += 1

                if errors:
                    transaction.set_rollback(True)
                    return JsonResponse({"error": "Validation failed : " + str(errors), "details": errors}, status=400)
                
                billing_obj.market_order_data = market_order_data
                billing_obj.ongoing = False
                billing_obj.save()
                
                return JsonResponse({"success": True, "message": f"Updated {updated_count} rows successfully"})

        except models.Billing.DoesNotExist:
            return JsonResponse({"error": "Billing record not found for today"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@api_view(["GET", "POST"])
def party_credit(request):
    data = request.data if request.method == "POST" else request.GET
    company_id = data.get("company")
    party_id = data.get("party_id")
    
    if not company_id:
        return JsonResponse({"error": "Company ID is required"}, status=400)

    if not party_id:
        return JsonResponse({"error": "Party ID is required"}, status=400)
    
    if request.method == "GET":
        try:
            credit,_ = PartyCredit.objects.get_or_create(company_id=company_id, party_id=party_id)
            response_data = {
                    "party_id": party_id,
                    "bills": credit.bills,
                    "days": credit.days,
                    "value": credit.value
            }
            return JsonResponse(response_data)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    if request.method == "POST":
        bills = data.get("bills")
        days = data.get("days")
        value = data.get("value")
        
        try:
            obj, created = PartyCredit.objects.update_or_create(
                company_id=company_id,
                party_id=party_id,
                defaults={
                    "bills": bills,
                    "days": days,
                    "value": value
                }
            )
            return JsonResponse({"success": True, "message": "Party credit updated successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            return JsonResponse({"error": str(e)}, status=500)

@api_view(["GET"])
def get_billing_stats(request):
    company_id = request.GET.get("company")
    if not company_id:
        return JsonResponse({"error": "Company ID is required"}, status=400)
    
    from report.models import SalesRegisterReport
    from bill.models import Bill
    
    today = datetime.date.today()
    billing_obj, _ = models.Billing.objects.get_or_create(company_id=company_id, date=today)

    # Last Bills Stats
    last_bills_count = 0
    last_bills_text = ""
    last_time = ""
    user = billing_obj.user
    
    if billing_obj:
        sorted_bills = sorted(billing_obj.last_bills)
        last_bills_count = len(sorted_bills) 
        last_bills_text = f"{sorted_bills[0]} - {sorted_bills[-1]}" if last_bills_count else "-"
        last_time = billing_obj.time.strftime("%H:%M") 

    # Today's Bills Stats
    today_bills = SalesRegisterReport.objects.filter(date=today, type="sales", company_id=company_id).exclude(beat__contains="WHOLE").aggregate(
            bill_count=Count("inum"),
            start_bill_no=Min("inum"),
            end_bill_no=Max("inum"),
    )
    today_bills_count = today_bills["bill_count"] or 0
    today_bills_text = f'{today_bills["start_bill_no"]} - {today_bills["end_bill_no"]}' if today_bills_count else "-"

    # Unprinted Bills Stats
    unprinted_bills_count = Bill.objects.filter(company_id=company_id, bill_date=today, print_time__isnull=True).exclude(beat__contains="WHOLE").count()

    stats = {
        "last_bills_count": last_bills_count, 
        "last_bills": last_bills_text,      
        "last_time": last_time,
        "today_bills": today_bills_text,
        "today_bills_count": today_bills_count,
        "unprinted_bills_count": unprinted_bills_count,
        "user": user
    }
    return JsonResponse(stats)
