from report.models import BeatReport
from django.db import close_old_connections,connections
from report.models import SalesRegisterReport
from report.models import EmptyArgs
import datetime
import os
from collections import defaultdict
import threading
import time
import traceback 
from PyPDF2 import PdfMerger
from django.http import JsonResponse
import pandas as pd
from enum import Enum, IntEnum

from custom.classes import Billing, Einvoice
from django.db.models import F,F
from rest_framework.decorators import api_view
import hashlib
from django.http import JsonResponse
from . import models
import report.models as report_models
import erp.models as erp_models

#TODO : ENUMS   
class BillingStatus(IntEnum) :
    NotStarted = 0
    Success = 1
    Started = 2
    Failed = 3

billing_process_names = ("SYNC" , "PREVBILLS" , "RELEASELOCK" , "COLLECTION", "ORDER" , "DELIVERY", "REPORTS")

def run_billing_process_thread_safe(billing_log_id,data) :
    close_old_connections()
    try :
        run_billing_process(billing_log_id,data)
    finally : 
        connections.close_all()

def run_billing_process(billing_log_id,data) :
    billing_log = models.Billing.objects.get(id=billing_log_id)
    company = billing_log.company
    ##Calculate the neccesary values for the billing
    today = datetime.date.today()
    max_lines = data.get("max_lines")    
    order_date =  datetime.datetime.strptime(data.get("order_date"),"%Y-%m-%d").date()

    prev_order_total_values = { order.order_no : order.bill_value for order in models.Orders.objects.filter(company=company,date = order_date) }
    
    delete_order_nos = [ order_no for order_no, selected in data.get("delete").items() if selected ]
    forced_order_nos = [ order_no for order_no, selected in data.get("force_place").items() if selected ]
    
    old_billing_id = data.get("billing_id")
    if old_billing_id :
        old_billing = models.Billing.objects.get(id = old_billing_id,company=company)
        last_billing_orders = models.Orders.objects.filter(billing = old_billing,company=company)
        creditrelease = list(last_billing_orders.filter(creditlock=True,order_no__in = forced_order_nos))
        beat_name_to_plg = {}
        if len(creditrelease) > 0 : 
            beat_name_to_plg = dict(BeatReport.objects.filter(company_id = company.pk).values_list("name","plg"))
        creditrelease = pd.DataFrame([[ order.party_id , order.party_id , order.party_hul_code , beat_name_to_plg.get(order.beat) ,
                                         order.bill_value ] for order in creditrelease ] , # type: ignore
                                    columns=["partyCode","parCodeRef","parHllCode","showPLG","bill_value"])
        creditrelease = creditrelease.groupby(["partyCode","parCodeRef","parHllCode","showPLG"], as_index=False).agg(
            increase_value = ("bill_value","sum"),
            increase_count = ("bill_value","count")
        )
        creditrelease = creditrelease.to_dict(orient="records")
    else : 
        creditrelease = []
     
    def filter_orders_fn(order: pd.Series) : 
        return (((today == order_date) or (order.iloc[0].ot == "SH")) and all([
              order.on.count() <= max_lines ,
              (order.on.iloc[0] not in prev_order_total_values) or abs((order.t * order.cq).sum() - prev_order_total_values[order.on.iloc[0]]) <= 1 , 
              "WHOLE" not in order.m.iloc[0] ,
              (order.t * order.cq).sum() >= 200
            ])) or (order.on.iloc[0] in forced_order_nos)

    ##Intiate the Ikea Billing Session
    order_objects:list[models.Orders] = []
    try :  
        billing = Billing(user=company.pk,order_date = order_date,filter_orders_fn = filter_orders_fn)
    except Exception as e: 
        print("Billing Session Failed\n" , traceback.format_exc() )
        billing_log.error = str(traceback.format_exc())
        billing_log.status = BillingStatus.Failed
        billing_log.save()
        sync_process_obj = models.BillingProcessStatus.objects.get(billing=billing_log,process="SYNC")
        sync_process_obj.status = BillingStatus.Failed
        sync_process_obj.save()
        return
    
    ##Functions combing Ikea Session + Database 
    def PrevDeliveryProcess() : 
        billing.Prevbills()

    def CollectionProcess() : 
        billing.Collection()
        models.PushedCollection.objects.bulk_create([ models.PushedCollection(
                   billing = billing_log, party_code = pc) for pc in billing.pushed_collection_party_ids ])
        
    def OrderProcess() : 
        billing.Order(delete_order_nos)
        last_billing_orders = billing.all_orders    
        if len(last_billing_orders.index) == 0 : return 
        filtered_orders = billing.filtered_orders.on.values
        ## Warning add and condition 
        order_objects.extend( models.Orders.objects.bulk_create([ 
            models.Orders( order_no = row.on, party_id = row.pc, party_hul_code = row.ph, salesman = row.s, 
                creditlock = ("Credit Exceeded" in row.ar) , place_order = (row.on in filtered_orders) , 
                beat = row.m , billing = billing_log , date = datetime.datetime.now().date() , type = row.ot ,
                company = company, party_name = row.p )
            for _,row in last_billing_orders.drop_duplicates(subset="on").iterrows() ],
         update_conflicts=True,
         unique_fields=['order_no'],
         update_fields=["billing_id","type","creditlock","place_order","party_hul_code"]) )
        
        models.OrderProducts.objects.filter(order__in = order_objects,allocated = 0).update(allocated = F("quantity"),reason = "Guessed allocation")
        models.OrderProducts.objects.bulk_create([ models.OrderProducts(
            order_id=row.on,product=row.bd,batch=row.bc,quantity=row.cq,allocated = row.aq,rate = row.t,reason = row.ar) for _,row in last_billing_orders.iterrows() ] , 
         update_conflicts=True,
         unique_fields=['order','product','batch'],
         update_fields=['quantity','rate','allocated','reason'])

    def ReportProcess() :
        today = datetime.date.today()
        args = report_models.DateRangeArgs(fromd=today, tod=today)
        report_models.OutstandingReport.update_db(billing, company, EmptyArgs())
        report_models.SalesRegisterReport.update_db(billing, company, args)
        models.Bill.sync_with_salesregister(company,fromd = args.fromd,tod = args.tod)
        report_models.CollectionReport.update_db(billing, company, args)
        models.Bill.objects.filter(company=company,bill_id__in = billing.prevbills).update(delivered = False)
                      
    def DeliveryProcess() : 
        billing.Delivery()
        if len(billing.bills) == 0 : return 
        billing_log.start_bill_no = billing.bills[0]
        billing_log.end_bill_no = billing.bills[-1]
        billing_log.bill_count = len(billing.bills)
        billing_log.save()
    ##Start the proccess
    billing_process_functions = [billing.Sync , PrevDeliveryProcess ,  (lambda : billing.release_creditlocks(creditrelease)) , 
                                  CollectionProcess ,  OrderProcess ,  DeliveryProcess , ReportProcess  ]
    billing_process =  dict(zip(billing_process_names,billing_process_functions)) 
    billing_failed = False 
    for process_name,process in billing_process.items() : 
        process_obj = models.BillingProcessStatus.objects.get(billing=billing_log,process=process_name)
        process_obj.status = BillingStatus.Started
        process_obj.save()    
        start_time = time.time()
        try : 
            process()          
        except Exception as e :
            traceback.print_exc()
            billing_log.error = str(traceback.format_exc())
            billing_failed = True 

        process_obj.status = (BillingStatus.Failed if billing_failed else  BillingStatus.Success)
        end_time = time.time()
        process_obj.time = round(end_time - start_time,2)
        process_obj.save()
        if billing_failed :  break 
        
    billing_log.end_time = datetime.datetime.now() 
    billing_log.end_time = datetime.datetime.now()
    billing_log.status = BillingStatus.Success
    billing_log.save()
