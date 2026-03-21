"""
Global error handler middleware.
Catches unhandled exceptions, logs them to ErrorLog, attempts auto-heal,
and alerts via Telegram when healing fails.
"""
import json
import traceback as tb

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.database import SessionLocal, ErrorLog


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Cache body bytes once so it can be read again in the except block
        body_bytes = b""
        try:
            body_bytes = await request.body()
        except Exception:
            pass

        # Patch receive so the endpoint can still read the body normally
        async def receive():
            return {"type": "http.request", "body": body_bytes}

        request = Request(request.scope, receive)

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
                    return JSONResponse(
                        status_code=200,
                        content={
                            "reply": "Sorry for the brief hiccup — I've fixed the issue. Could you try that again?",
                            "was_auto_reply": True,
                        },
                    )
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

            except Exception:
                pass  # Never let the error handler itself crash the app
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
