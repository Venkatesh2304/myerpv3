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

@api_view(["POST"])
def get_order(request):
    data = request.data
    company_id = data.get("company")
    order_date = data.get("order_date")
    lines = data.get("lines", 100)

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
            
            if not created:
                billing_obj.ongoing = True
                billing_obj.process = "getorder"
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
            CollectionReport.update_db(billing, company, DateRangeArgs(today, today))
            OutstandingReport.update_db(billing, company, EmptyArgs())

        with tracker.step("Order"):
            order_data:list = billing.get_market_order(order_date)
        
        
        from itertools import groupby
        from operator import itemgetter
        
        # Sort by 'on' (Order Number) to ensure groupby works correctly
        order_data.sort(key=itemgetter('on'))
        
        processed_orders = []
        for order_no, items in groupby(order_data, key=itemgetter('on')):
            items_list = list(items)
            first_item = items_list[0]
            
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
            os_val = "-"
            try:
                outstanding_bills = OutstandingReport.objects.filter(
                    company_id=company_id, 
                    party_id=first_item.get('pc'), 
                    beat=first_item.get('m')
                )
                os_list = [f"{round(bill.balance)}*{(today - bill.bill_date).days}" for bill in outstanding_bills]
                os_val = "/ ".join(os_list) or "-"
            except Exception:
                pass

            # Coll: CollectionReport
            coll_val = "-"
            try:
                collections = CollectionReport.objects.filter(
                    company_id=company_id, 
                    party_name=first_item.get('p'), 
                    date=today
                )
                coll_list = [f"{round(coll.amt or 0)}*{(today - coll.bill_date).days}" for coll in collections]
                coll_val = "/ ".join(coll_list) or "-"
            except Exception:
                pass

            processed_orders.append({
                "order_no": order_no,
                "party": first_item.get('p'),
                "lines": lines_count,
                "bill_value": round(bill_value, 2),
                "allocated_value": round(allocated_value, 2),
                "salesman": first_item.get('s'),
                "beat": first_item.get('m'),
                "type": first_item.get('ot'),
                "phone": phone,
                "OS": os_val,
                "coll": coll_val
            })

        # Populate order_values from processed_orders
        order_values = {order["order_no"]: order["bill_value"] for order in processed_orders}
        
        # Store state in DB (Short transaction for update)
        # Note: We can just save here as we are the only ones running due to ongoing flag
        billing_obj.market_order_data = order_data
        billing_obj.order_date = order_date
        billing_obj.order_values = order_values
        
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
             
        stored_data_json = json.dumps(stored_data, sort_keys=True)
        stored_hash = hashlib.md5(stored_data_json.encode('utf-8')).hexdigest()
        
        if stored_hash != client_hash:
             return JsonResponse({"error": "Data mismatch (Hash invalid). Please refresh orders."}, status=400)

        with tracker.step("Initialisation"):
            billing = Billing(company_id)
            
        with tracker.step("PrevBills"):
            billing.Prevbills()   
            
        with tracker.step("Order"):
            billing.post_market_order(stored_data, order_numbers)   
            
        with tracker.step("Delivery"):
            billing.Delivery()  
            
        with tracker.step("Report"):
             # Update Sales Register Report
             from report.models import SalesRegisterReport, DateRangeArgs
             today = datetime.date.today()
             company = Company.objects.get(pk=company_id)
             SalesRegisterReport.update_db(billing, company, DateRangeArgs(today, today))
             

        # Stats
        last_bills_count = len(billing.bills) if hasattr(billing, 'bills') else 0
        last_bills_text = ""
        if hasattr(billing, 'bills') and billing.bills:
            # Assuming bills are sorted strings, but let's sort them to be sure
            sorted_bills = sorted(billing.bills)
            last_bills_text = f"{sorted_bills[0]} - {sorted_bills[-1]}"
            
        return JsonResponse({
            "message": "Order posted successfully. Log saved.",
            "last_bills_count": last_bills_count,
            "last_bills": last_bills_text,
            "process": tracker.stats
        })
    except Exception as e:
        return JsonResponse({"error": str(e), "process": tracker.stats}, status=500)
    finally:
        # Release lock
        if 'billing_obj' in locals() and billing_obj.ongoing:
            billing_obj.ongoing = False
            billing_obj.save()


