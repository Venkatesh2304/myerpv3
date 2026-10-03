import json
import time
import traceback
import random
from datetime import timedelta
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.tokens import AccessToken
from core.models import ApiRequestLog

SENSITIVE_KEYS = {"password", "secret", "token", "authorization", "key", "access_token"}


def mask_sensitive_data(data):
    """Recursively mask sensitive values in dicts/lists."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                cleaned[k] = "********"
            else:
                cleaned[k] = mask_sensitive_data(v)
        return cleaned
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


class ApiAuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware that records HTTP requests and responses for auditing,
    debugging, and AI diagnostic investigation.
    """

    IGNORE_PREFIXES = (
        "/static/",
        "/media/",
        "/favicon.ico",
        "/admin/jsi18n/",
    )

    def process_request(self, request):
        request._start_time = time.time()
        request._error_traceback = None

        # Check if route should be ignored
        if request.path.startswith(self.IGNORE_PREFIXES):
            request._skip_audit = True
            return

        request._skip_audit = False

        # Read and cache request body safely
        try:
            content_type = request.content_type or ""
            if "multipart/form-data" in content_type or "application/octet-stream" in content_type:
                request._audit_body = "[Multipart/Binary Upload]"
            else:
                # Read up to 32 KB
                body_bytes = request.body[:32768]
                if body_bytes:
                    try:
                        parsed = json.loads(body_bytes.decode("utf-8"))
                        masked = mask_sensitive_data(parsed)
                        request._audit_body = json.dumps(masked, ensure_ascii=False)
                    except Exception:
                        request._audit_body = body_bytes.decode("utf-8", errors="replace")
                else:
                    request._audit_body = ""
        except Exception:
            request._audit_body = "[Could not read request body]"

    def process_exception(self, request, exception):
        request._error_traceback = traceback.format_exc()
        return None

    def process_response(self, request, response):
        if getattr(request, "_skip_audit", False):
            return response

        try:
            duration_ms = int((time.time() - getattr(request, "_start_time", time.time())) * 1000)

            # Determine user
            user_str = None
            if hasattr(request, "user") and request.user and request.user.is_authenticated:
                user_str = str(request.user.username)
            else:
                # Attempt to extract from JWT header if available
                auth_header = request.META.get("HTTP_AUTHORIZATION", "")
                if auth_header.startswith("Bearer "):
                    try:
                        token = auth_header.split(" ")[1]
                        decoded = AccessToken(token)
                        user_str = str(decoded.get("username") or decoded.get("user_id") or "")
                    except Exception:
                        pass

            if not user_str:
                user_str = request.GET.get("user") or "anonymous"

            # Determine company
            company = (
                request.headers.get("X-Company")
                or request.GET.get("company")
                or ""
            )

            # Response body capture
            response_body = ""
            status_code = response.status_code
            content_type = response.get("Content-Type", "")

            if getattr(response, "streaming", False) or "pdf" in content_type or "spreadsheet" in content_type or "octet-stream" in content_type:
                response_body = f"[Streaming/Binary content: {content_type}]"
            else:
                try:
                    # Capture up to 32KB
                    content = getattr(response, "content", b"")[:32768]
                    if content:
                        try:
                            parsed = json.loads(content.decode("utf-8"))
                            masked = mask_sensitive_data(parsed)
                            response_body = json.dumps(masked, ensure_ascii=False)
                        except Exception:
                            response_body = content.decode("utf-8", errors="replace")
                except Exception:
                    response_body = "[Could not read response body]"

            # Query params
            query_dict = {}
            for k in request.GET:
                query_dict[k] = request.GET.get(k)
            query_dict = mask_sensitive_data(query_dict)

            error_tb = getattr(request, "_error_traceback", None)
            is_error = status_code >= 400 or bool(error_tb)

            # Save log entry
            ApiRequestLog.objects.create(
                user=user_str[:150],
                company=company[:100] if company else None,
                method=request.method,
                path=request.path[:500],
                query_params=query_dict,
                request_body=getattr(request, "_audit_body", None),
                status_code=status_code,
                response_body=response_body,
                error_traceback=error_tb,
                duration_ms=duration_ms,
                is_error=is_error,
            )

            # Periodic cleanup: roughly 1 in 500 requests, prune logs older than 7 days
            if random.random() < 0.002:
                cutoff = timezone.now() - timedelta(days=7)
                ApiRequestLog.objects.filter(timestamp__lt=cutoff).delete()

        except Exception as e:
            # Never fail the actual request due to logging error
            pass

        return response
