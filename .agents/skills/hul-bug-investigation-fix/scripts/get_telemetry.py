#!/usr/bin/env python3
import os
import sys
import json
import argparse
from datetime import datetime, timedelta, date

sys.path.insert(0, '/home/ubuntu/myerpv3')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myerpv2.settings')
import django
django.setup()

from django.utils import timezone
from core.models import ApiRequestLog, UserSession

PAGE_ENDPOINT_MAP = {
    "/billing": ["/billing", "/get_order", "/post_order", "/get_billing_stats", "/salesman", "/orderpage"],
    "/print": ["/print", "/bill", "/bills"],
    "/scan": ["/scan", "/scan_bill", "/push_impact", "/download_scan_pdf"],
    "/delivery": ["/scan", "/scan_bill", "/push_impact", "/download_scan_pdf", "/bill_scan"],
    "/bank": ["/bank", "/bankstatement", "/chequedeposit"],
    "/gst": ["/gst", "/custom/captcha", "/custom/login", "/einv"],
    "/truck": ["/truck", "/load", "/cbu"],
    "/cheque": ["/cheque", "/chequedeposit"],
    "/ledger": ["/ledger", "/unilever"],
    "/reports": ["/report", "/reports", "/sync_report"],
}

def get_telemetry(company=None, user=None, page=None, minutes=45):
    telemetry = {
        "timestamp": datetime.now().isoformat(),
        "query_params": {"company": company, "user": user, "page": page, "minutes": minutes},
        "billing_lock": None,
        "ikea_session": None,
        "recent_errors": []
    }

    # 1. Check Billing Lock
    try:
        from bill.models import Billing
        from bill.views import BILLING_LOCK_TIMEOUT
        comp_filter = company or "devaki_hul"
        b = Billing.objects.filter(company_id=comp_filter, date=date.today()).first()
        if b and b.ongoing:
            now_dt = timezone.now()
            duration_sec = int((now_dt - b.time).total_seconds()) if b.time else 0
            is_expired = duration_sec > BILLING_LOCK_TIMEOUT
            telemetry["billing_lock"] = {
                "ongoing": True,
                "process": b.process,
                "user": b.user,
                "active_seconds": duration_sec,
                "active_minutes": duration_sec // 60,
                "is_expired": is_expired,
                "timeout_minutes": BILLING_LOCK_TIMEOUT // 60
            }
        else:
            telemetry["billing_lock"] = {"ongoing": False}
    except Exception as ex:
        telemetry["billing_lock"] = {"error": str(ex)}

    # 2. Check IKEA Session
    try:
        comp_check = company or "devaki_hul"
        sess = UserSession.objects.filter(user=comp_check, key="ikea").first()
        has_cookies = bool(sess and sess.cookies)
        telemetry["ikea_session"] = {
            "company": comp_check,
            "has_cookies": has_cookies,
            "last_updated": sess.updated_at.isoformat() if sess and hasattr(sess, 'updated_at') and sess.updated_at else None
        }
    except Exception as ex:
        telemetry["ikea_session"] = {"error": str(ex)}

    # 3. Query Recent Errors from ApiRequestLog
    try:
        cutoff = timezone.now() - timedelta(minutes=minutes)
        base_errors = ApiRequestLog.objects.filter(is_error=True, timestamp__gte=cutoff)

        matched_errors = []
        # Match by page endpoint map
        if page:
            for prefix, routes in PAGE_ENDPOINT_MAP.items():
                if prefix in page:
                    for route in routes:
                        for m in base_errors.filter(path__icontains=route).order_by("-timestamp")[:3]:
                            if m not in matched_errors:
                                matched_errors.append(m)
        # Match by user
        if user and user not in ("anonymous", "None", ""):
            for m in base_errors.filter(user=user).order_by("-timestamp")[:3]:
                if m not in matched_errors:
                    matched_errors.append(m)
        # Match by company
        if company:
            for m in base_errors.filter(company=company).order_by("-timestamp")[:3]:
                if m not in matched_errors:
                    matched_errors.append(m)

        # Fallback to general errors if no targeted matches
        if not matched_errors:
            matched_errors = list(base_errors.order_by("-timestamp")[:3])

        for log in matched_errors[:4]:
            telemetry["recent_errors"].append({
                "id": log.id,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "user": log.user,
                "company": log.company,
                "method": log.method,
                "path": log.path,
                "query_params": log.query_params,
                "request_body": (log.request_body[:600] + "... [truncated]") if log.request_body and len(log.request_body) > 600 else log.request_body,
                "status_code": log.status_code,
                "response_body": (log.response_body[:1000] + "... [truncated]") if log.response_body and len(log.response_body) > 1000 else log.response_body,
                "error_traceback": (log.error_traceback[:1500] + "... [truncated]") if log.error_traceback and len(log.error_traceback) > 1500 else log.error_traceback,
                "duration_ms": log.duration_ms,
            })
    except Exception as ex:
        telemetry["recent_errors"] = [{"error": str(ex)}]

    return telemetry

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch ERP diagnostic telemetry on demand.")
    parser.add_argument("--company", type=str, default=None, help="Distributor company")
    parser.add_argument("--user", type=str, default=None, help="Active user")
    parser.add_argument("--page", type=str, default=None, help="Current active frontend page")
    parser.add_argument("--minutes", type=int, default=45, help="Time window in minutes")
    args = parser.parse_args()

    result = get_telemetry(company=args.company, user=args.user, page=args.page, minutes=args.minutes)
    print(json.dumps(result, indent=2))
