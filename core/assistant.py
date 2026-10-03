import json
import logging
import subprocess
import shutil
import time
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from core.models import ApiRequestLog

logger = logging.getLogger(__name__)

AGY_BINARY = shutil.which("agy") or "/home/ubuntu/.local/bin/agy"
PROJECT_DIR = "/home/ubuntu/myerpv3"


@api_view(["POST"])
@permission_classes([AllowAny])
def assistant_chat(request):
    """
    Lean AI Assistant endpoint powered by Antigravity (agy CLI) and
    the 'hul-client-assistant' skill.
    Accepts:
    - prompt: string (user question, instruction, or problem description)
    - type: string ('check_failure', 'query', 'action', 'chat', etc.)
    - metadata: dict (arbitrary client context: page, client_error, user, company, etc.)
    - conversation_id: string (optional, to continue multi-turn chats)
    """
    t0 = time.time()
    try:
        data = request.data if isinstance(request.data, dict) else {}
        prompt = (data.get("prompt") or "").strip()
        req_type = (data.get("type") or "chat").lower()
        metadata = data.get("metadata") or {}
        conversation_id = data.get("conversation_id") or None

        # Resolve user & company dynamically
        user_obj = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        user_str = str(user_obj.username) if user_obj else (metadata.get("user") or "anonymous")
        company = request.headers.get("X-Company") or metadata.get("company") or ""
        if not company or company == "1":
            if user_obj and hasattr(user_obj, "companies"):
                user_comps = list(user_obj.companies.values_list("name", flat=True))
                if user_comps:
                    company = user_comps[0]
            if not company:
                from core.models import Company
                first_comp = Company.objects.first()
                company = first_comp.name if first_comp else "devaki_hul"
        page = metadata.get("page") or ""
        client_error = metadata.get("client_error") or metadata.get("error")

        effective_prompt = prompt or "Check why the current operation or page failed."

        # Construct lean prompt - skills handle domain routing, rules handle workspace constraints
        agent_prompt = f"""Activate the 'hul-client-assistant' skill to process this distributor request.

[USER REQUEST]
Prompt: {effective_prompt}

[CLIENT CONTEXT]
- Page: {page or 'Unknown'}
- User: {user_str}
- Company: {company}
- Client Error: {json.dumps(client_error, indent=2) if client_error else 'None'}
"""

        # Resolve model type (low | medium | high) - defaults to 'medium' if not provided
        model_type = data.get("model_type") or data.get("model") or metadata.get("model_type") or "medium"
        model_type = str(model_type).lower().strip()
        MODEL_MAP = {
            "low": "gemini-3.8-flash-low",
            "medium": "gemini-3.8-flash-medium",
            "high": "gemini-3.8-flash-high",
        }
        selected_model = MODEL_MAP.get(model_type, "gemini-3.8-flash-medium")
        effort_level = model_type if model_type in ("low", "medium", "high") else "medium"

        # Build agy command line
        cmd = [
            AGY_BINARY,
            "-p", agent_prompt,
            "--model", selected_model,
            "--effort", effort_level,
            "--output-format", "json",
            "--dangerously-skip-permissions",
        ]
        if conversation_id:
            cmd.extend(["--conversation", str(conversation_id)])

        # Execute agy CLI (10 minute timeout)
        process = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )

        elapsed_ms = int((time.time() - t0) * 1000)

        if process.returncode != 0:
            logger.error(f"agy execution failed with code {process.returncode}: {process.stderr}")
            return JsonResponse({
                "success": False,
                "error": f"Assistant process failed (code {process.returncode})",
                "stderr": process.stderr,
                "response": "I encountered an internal error while analyzing the request. Please check system logs.",
                "duration_ms": elapsed_ms,
            }, status=500)

        # Parse output JSON
        raw_output = process.stdout.strip()
        try:
            parsed = json.loads(raw_output)
            res_text = parsed.get("response", "")
            conv_id = parsed.get("conversation_id", conversation_id)
            return JsonResponse({
                "success": True,
                "conversation_id": conv_id,
                "response": res_text,
                "type": req_type,
                "model_type": effort_level,
                "duration_ms": elapsed_ms,
            })
        except json.JSONDecodeError:
            return JsonResponse({
                "success": True,
                "conversation_id": conversation_id,
                "response": raw_output,
                "type": req_type,
                "model_type": effort_level,
                "duration_ms": elapsed_ms,
            })

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.time() - t0) * 1000)
        return JsonResponse({
            "success": False,
            "error": "Assistant diagnosis timed out after 10 minutes.",
            "response": "The diagnosis/operation timed out after 10 minutes. The system may be under high load.",
            "duration_ms": elapsed_ms,
        }, status=504)
    except Exception as e:
        logger.exception("Exception in assistant_chat view")
        elapsed_ms = int((time.time() - t0) * 1000)
        return JsonResponse({
            "success": False,
            "error": str(e),
            "response": f"An unexpected error occurred: {str(e)}",
            "duration_ms": elapsed_ms,
        }, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def recent_failures(request):
    """
    Returns the latest failed requests for quick inspection.
    """
    limit = int(request.GET.get("limit", 10))
    limit = min(limit, 50)
    errors = ApiRequestLog.objects.filter(is_error=True).order_by("-timestamp")[:limit]

    items = []
    for log in errors:
        items.append({
            "id": log.id,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "user": log.user,
            "company": log.company,
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "error_traceback": bool(log.error_traceback),
            "duration_ms": log.duration_ms,
        })

    return JsonResponse({"status": "success", "count": len(items), "data": items})
