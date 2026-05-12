"""
Global error handler middleware.
Catches unhandled exceptions, logs them to ErrorLog, attempts auto-heal,
and alerts via Telegram when healing fails.
"""
import json
import traceback as tb

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.database import SessionLocal, ErrorLog

log = structlog.get_logger(__name__)


def _error_response_for_path(path: str, message: str) -> dict:
    if path.startswith("/api/chat"):
        return {
            "reply": message,
            "was_auto_reply": True,
            "error": True
        }
    elif path.startswith("/api/analytics"):
        return {
            "error": True,
            "message": message,
            "data": None
        }
    elif path.startswith("/api/leads"):
        return {
            "error": True,
            "message": message,
            "leads": [],
            "total": 0
        }
    else:
        return {
            "error": True,
            "message": message
        }


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Cache body bytes once so it can be read again in the except block
        body_bytes = b""
        try:
            body_bytes = await request.body()
        except Exception:
            pass

        # Create a new receive that replays the cached body so the endpoint
        # can still read the body normally. We keep the original request
        # object so that request.state (populated by upstream middleware) is
        # NOT discarded.
        original_receive = request.receive

        async def receive():
            return {"type": "http.request", "body": body_bytes}

        # Patch the receive callable in place rather than creating a new
        # Request — re-creating the Request from scope discards the
        # request.state dict that upstream middleware may have populated
        # (auth, rate-limit, tenant).
        request._receive = receive

        try:
            response = await call_next(request)
            return response

        except Exception as e:
            error_traceback = tb.format_exc()
            error_type = classify_error(e)

            # Try to extract bot_id from cached body
            bot_id = None
            request_data = None
            try:
                body = json.loads(body_bytes) if body_bytes else {}
                bot_id = body.get("bot_id")
                request_data = sanitize_request(body)
            except Exception:
                pass

            db = SessionLocal()
            try:
                error_log = ErrorLog(
                    bot_id=bot_id,
                    error_type=error_type,
                    error_message=str(e)[:1000],
                    traceback=error_traceback[:5000],
                    endpoint=str(request.url.path),
                    request_data=request_data,
                    max_retries=2,
                )
                db.add(error_log)
                db.commit()
                db.refresh(error_log)

                # Attempt auto-heal (import here to avoid circular at module load)
                from backend.services.auto_healer import attempt_heal
                healed = await attempt_heal(error_log, db)

                if healed:
                    body = _error_response_for_path(
                        str(request.url.path),
                        "Sorry for the brief hiccup — I've fixed the issue. Could you try that again?",
                    )
                    return JSONResponse(status_code=200, content=body)
                else:
                    # Alert via Telegram
                    from backend.services.telegram_notify import send_telegram_alert
                    await send_telegram_alert(
                        f"SupportBot Error\n\n"
                        f"Type: {error_type}\n"
                        f"Bot: {bot_id or 'system'}\n"
                        f"Endpoint: {request.url.path}\n"
                        f"Error: {str(e)[:300]}\n"
                        f"Status: Auto-heal failed — needs manual fix"
                    )

            except Exception as handler_exc:
                # The error handler itself blew up. We MUST still return a
                # response — but a silent ``pass`` here previously meant a
                # broken handler was invisible in production. Log explicitly
                # before falling through to the 500 response.
                #
                # Request context (path, method, original error_type, bot_id)
                # is included so the structured log is actionable on its own
                # without needing to correlate to upstream traces.
                try:
                    log.error(
                        "error_handler.crashed",
                        path=str(request.url.path),
                        method=request.method,
                        original_error_type=error_type,
                        original_error=str(e)[:300],
                        handler_error=str(handler_exc)[:300],
                        handler_traceback=tb.format_exc()[:3000],
                        bot_id=bot_id,
                    )
                except Exception:
                    # Logging failed too (e.g. structlog misconfigured). At
                    # this point the safest action is to return the generic
                    # 500 below — we cannot afford to raise from middleware.
                    pass
            finally:
                db.close()

            return JSONResponse(
                status_code=500,
                content={"error": "Something went wrong. Our team has been notified."},
            )


def classify_error(e: Exception) -> str:
    """Classify error type for targeted healing strategies."""
    error_class = type(e).__name__.lower()
    msg = str(e).lower()

    if "anthropic" in msg or "rate_limit" in msg or "credit" in msg or "overloaded" in msg:
        return "api_error"
    elif "database" in msg or "sql" in msg or "operational" in error_class or "integrity" in error_class:
        return "db_error"
    elif "connection" in msg or "timeout" in msg or "refused" in msg or "connect" in error_class:
        return "connection_error"
    elif "file" in msg or "upload" in msg or "permission" in msg or "errno" in error_class:
        return "upload_error"
    elif "webhook" in msg or "telegram" in msg or "email" in msg or "twilio" in msg:
        return "notification_error"
    elif "token" in msg or "auth" in msg or "jwt" in msg or "unauthorized" in msg:
        return "auth_error"
    else:
        return "unknown_error"


def sanitize_request(body: dict) -> str:
    """Remove sensitive fields before logging the request body."""
    SENSITIVE = {"password", "api_key", "token", "secret", "authorization", "key"}
    safe = {k: v for k, v in (body or {}).items() if k.lower() not in SENSITIVE}
    try:
        return json.dumps(safe)[:2000]
    except Exception:
        return "{}"
