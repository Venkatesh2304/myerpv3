from bill.billing import run_billing_process_thread_safe,BillingStatus, billing_process_names
from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.decorators import api_view
from . import models
import datetime
import threading
from core.models import Company
from django.db import transaction, connection
import zlib
import time
from enum import Enum

class StartBillingMessage(str,Enum):
    Success = "Billing Process Started"
    Locked = "The pg for the company is locked"
    AlreadyRunning = "Someone is already running the billing process"
    OldBilling = "This Billing is Old, Try Again"
    MissingCompany = "Company ID is required"

@api_view(["GET","POST"])
def start_billing(request) :
    data = request.data if request.method == "POST" else request.query_params
    company = data.get("company")
    if not company : 
        return JsonResponse({"error" : StartBillingMessage.MissingCompany})
    
    order_date = data.get("order_date") or datetime.date.today()
    cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=90)
    billing_id = data.get("billing_id")    

    if request.method == "GET" :
        last_billing = models.Billing.objects.filter(company_id=company,
                                                    start_time__gte = cutoff_time
                                                ).order_by("id").last()
        last_billing_id = last_billing.id if last_billing else None
        return JsonResponse({"billing_id" : last_billing_id })
    
    with transaction.atomic():
        with connection.cursor() as cursor:            
            lock_id = zlib.crc32(company.encode('utf-8'))
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_id])
            locked = cursor.fetchone()[0]

            last_billing = models.Billing.objects.filter(
                company_id=company,
                start_time__gte=cutoff_time,
            ).order_by("id").last()
            last_billing_id = last_billing.id if last_billing else None

            if not locked:
                return JsonResponse({ "billing_id" : last_billing_id  , "error" : StartBillingMessage.Locked })

            if (last_billing is not None) and (
                            last_billing.status in [BillingStatus.NotStarted , BillingStatus.Started]) :
                return JsonResponse({ "billing_id" : last_billing_id ,
                                       "message" : StartBillingMessage.AlreadyRunning })
            
            if (last_billing is not None) and (billing_id != last_billing_id) : 
                return JsonResponse({ "billing_id" : last_billing_id , "error" : StartBillingMessage.OldBilling , "refresh" : True})

            #Create Billing & Status Log in DB
            billing_log = models.Billing(company_id=company,start_time = datetime.datetime.now(), status = BillingStatus.Started, 
                                                date = order_date)
            billing_log.save()
        
            for process_name in billing_process_names :
                models.BillingProcessStatus(billing = billing_log,process = process_name,status = BillingStatus.NotStarted).save()

    thread = threading.Thread(target = run_billing_process_thread_safe , args = (billing_log.id,data))
    thread.start()
    return JsonResponse({"billing_id" : billing_log.id , "message" : StartBillingMessage.Success})
    


