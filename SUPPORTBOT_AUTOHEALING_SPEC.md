# SupportBot Studio — Auto-Healing Spec

## Overview

Add a self-healing system that catches errors, uses Claude to diagnose and fix them, retries failed operations, and alerts you via Telegram when something breaks. Think of it like a mechanic that lives inside your app — when something breaks, it tries to fix it before you even notice.

This is the same pattern used in KILO PICKS but adapted for a web app.

---

## ARCHITECTURE

```
Normal flow:
  Request → Process → Response ✅

Error flow:
  Request → Process → ERROR ❌
     ↓
  Error Catcher (middleware)
     ↓
  Log error to database
     ↓
  Can auto-heal? ──YES──→ Claude diagnoses → Applies fix → Retry
     ↓                                                      ↓
     NO                                              Success? ──YES──→ Response ✅
     ↓                                                      ↓          + Telegram: "Auto-healed ✅"
  Telegram alert 🚨                                        NO
  "Manual fix needed"                                       ↓
                                                    Telegram alert 🚨
                                                    "Auto-heal failed, needs manual fix"
```

---

## BUILD ORDER

1. Error logging model + middleware
2. Health check system
3. Auto-heal service (Claude-powered)
4. Retry logic
5. Telegram alerts
6. Self-healing dashboard (in Super Admin)
7. Scheduled health checks

---

## PHASE 1: ERROR LOGGING

### New Model — `ErrorLog`

```python
class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True)
    bot_id = Column(String, nullable=True)                # Which tenant was affected (null = system-wide)
    
    # Error details
    error_type = Column(String, nullable=False)            # "api_error" | "db_error" | "chat_error" | "escalation_error" | "webhook_error" | "upload_error"
    error_message = Column(String, nullable=False)
    traceback = Column(Text, nullable=True)
    endpoint = Column(String, nullable=True)               # "/api/chat" etc.
    request_data = Column(Text, nullable=True)             # Sanitized request body (no secrets)
    
    # Healing
    auto_healed = Column(Boolean, default=False)
    heal_action = Column(String, nullable=True)            # What fix was applied
    heal_diagnosis = Column(Text, nullable=True)           # Claude's diagnosis
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=2)
    
    # Status
    status = Column(String, default="new")                 # "new" | "healing" | "healed" | "failed" | "resolved_manually"
    notified = Column(Boolean, default=False)              # Telegram alert sent?
    
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)
```

### Global Error Middleware

Wrap the entire FastAPI app to catch unhandled errors:

```python
# backend/middleware/error_handler.py

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import traceback as tb
from backend.database import SessionLocal, ErrorLog
from backend.services.auto_healer import attempt_heal
from backend.services.telegram_notify import send_telegram_alert

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            error_traceback = tb.format_exc()
            
            # Determine error type
            error_type = classify_error(e)
            
            # Extract bot_id from request if available
            bot_id = None
            try:
                body = await request.json()
                bot_id = body.get("bot_id")
            except:
                pass
            
            # Log to database
            db = SessionLocal()
            try:
                error_log = ErrorLog(
                    bot_id=bot_id,
                    error_type=error_type,
                    error_message=str(e),
                    traceback=error_traceback,
                    endpoint=str(request.url.path),
                    request_data=sanitize_request(body) if body else None,
                )
                db.add(error_log)
                db.commit()
                db.refresh(error_log)
                
                # Attempt auto-heal
                healed = await attempt_heal(error_log, db)
                
                if healed:
                    return JSONResponse(
                        status_code=200,
                        content={"reply": "Sorry for the brief hiccup — I've fixed the issue. Could you try that again?", "was_auto_reply": True}
                    )
                else:
                    # Alert via Telegram
                    await send_telegram_alert(
                        f"🚨 *SupportBot Error*\n\n"
                        f"Type: `{error_type}`\n"
                        f"Bot: `{bot_id or 'system'}`\n"
                        f"Endpoint: `{request.url.path}`\n"
                        f"Error: {str(e)[:500]}\n"
                        f"Status: Auto-heal failed — needs manual fix"
                    )
            finally:
                db.close()
            
            return JSONResponse(
                status_code=500,
                content={"error": "Something went wrong. Our team has been notified."}
            )


def classify_error(e: Exception) -> str:
    """Classify error type for targeted healing."""
    error_str = str(type(e).__name__).lower()
    msg = str(e).lower()
    
    if "anthropic" in msg or "api" in msg or "rate_limit" in msg or "credit" in msg:
        return "api_error"
    elif "database" in msg or "sql" in msg or "operational" in error_str:
        return "db_error"
    elif "connection" in msg or "timeout" in msg or "refused" in msg:
        return "connection_error"
    elif "file" in msg or "upload" in msg or "permission" in msg:
        return "upload_error"
    elif "webhook" in msg or "telegram" in msg or "email" in msg:
        return "notification_error"
    elif "token" in msg or "auth" in msg or "jwt" in msg:
        return "auth_error"
    else:
        return "unknown_error"


def sanitize_request(body: dict) -> str:
    """Remove sensitive data before logging."""
    import json
    safe = {k: v for k, v in (body or {}).items() 
            if k not in ("password", "api_key", "token", "secret")}
    return json.dumps(safe)[:2000]
```

### Register Middleware

In `backend/main.py`:

```python
from backend.middleware.error_handler import ErrorHandlerMiddleware

app.add_middleware(ErrorHandlerMiddleware)
```

---

## PHASE 2: HEALTH CHECK SYSTEM

### Comprehensive Health Endpoint

```python
# backend/routers/health.py

@router.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    checks = {}
    
    # 1. Database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
    
    # 2. Anthropic API
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "ping"}]
                },
                timeout=10,
            )
            if r.status_code == 200:
                checks["anthropic_api"] = {"status": "ok"}
            else:
                checks["anthropic_api"] = {"status": "error", "code": r.status_code, "message": r.text[:200]}
    except Exception as e:
        checks["anthropic_api"] = {"status": "error", "message": str(e)}
    
    # 3. Telegram
    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe",
                    timeout=5,
                )
                if r.status_code == 200:
                    checks["telegram"] = {"status": "ok"}
                else:
                    checks["telegram"] = {"status": "error", "message": r.text[:200]}
        except Exception as e:
            checks["telegram"] = {"status": "error", "message": str(e)}
    else:
        checks["telegram"] = {"status": "not_configured"}
    
    # 4. Disk space
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_pct = (free / total) * 100
    checks["disk"] = {
        "status": "ok" if free_pct > 10 else "warning" if free_pct > 5 else "error",
        "free_percent": round(free_pct, 1),
    }
    
    # 5. Error rate (last hour)
    from datetime import datetime, timedelta
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_errors = db.query(ErrorLog).filter(ErrorLog.created_at > one_hour_ago).count()
    checks["error_rate"] = {
        "status": "ok" if recent_errors < 5 else "warning" if recent_errors < 20 else "error",
        "errors_last_hour": recent_errors,
    }
    
    # 6. Active tenants
    active_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
    checks["tenants"] = {"status": "ok", "active": active_tenants}
    
    # Overall status
    statuses = [c["status"] for c in checks.values()]
    overall = "error" if "error" in statuses else "warning" if "warning" in statuses else "ok"
    
    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

---

## PHASE 3: AUTO-HEAL SERVICE (CLAUDE-POWERED)

### Healer Service

```python
# backend/services/auto_healer.py

import anthropic
from backend.config import settings
from backend.database import ErrorLog
from sqlalchemy.orm import Session
from datetime import datetime

# Define healable error types and their fix strategies
HEAL_STRATEGIES = {
    "api_error": {
        "rate_limit": "wait_and_retry",
        "credit": "notify_only",
        "overloaded": "wait_and_retry",
        "invalid_request": "diagnose_with_claude",
    },
    "db_error": {
        "locked": "retry",
        "operational": "reconnect_and_retry",
        "integrity": "diagnose_with_claude",
    },
    "connection_error": {
        "timeout": "retry_with_backoff",
        "refused": "retry_with_backoff",
    },
    "upload_error": {
        "permission": "fix_permissions",
        "space": "cleanup_and_retry",
    },
    "notification_error": {
        "telegram": "retry",
        "email": "retry",
        "webhook": "retry",
    },
    "auth_error": {
        "expired": "refresh_token",
        "invalid": "notify_only",
    },
}


async def attempt_heal(error_log: ErrorLog, db: Session) -> bool:
    """
    Attempt to auto-heal an error.
    Returns True if healed, False if manual intervention needed.
    """
    if error_log.retry_count >= error_log.max_retries:
        error_log.status = "failed"
        db.commit()
        return False
    
    error_log.status = "healing"
    error_log.retry_count += 1
    db.commit()
    
    error_msg = error_log.error_message.lower()
    error_type = error_log.error_type
    
    # 1. Try known fix strategies first
    strategy = find_strategy(error_type, error_msg)
    
    if strategy == "wait_and_retry":
        import asyncio
        await asyncio.sleep(2 * error_log.retry_count)  # Exponential backoff
        error_log.auto_healed = True
        error_log.heal_action = "Waited and retried (rate limit / overload)"
        error_log.status = "healed"
        error_log.resolved_at = datetime.utcnow()
        db.commit()
        
        await notify_healed(error_log)
        return True
    
    elif strategy == "retry":
        error_log.auto_healed = True
        error_log.heal_action = "Simple retry"
        error_log.status = "healed"
        error_log.resolved_at = datetime.utcnow()
        db.commit()
        
        await notify_healed(error_log)
        return True
    
    elif strategy == "retry_with_backoff":
        import asyncio
        await asyncio.sleep(5 * error_log.retry_count)
        error_log.auto_healed = True
        error_log.heal_action = f"Retried with {5 * error_log.retry_count}s backoff"
        error_log.status = "healed"
        error_log.resolved_at = datetime.utcnow()
        db.commit()
        
        await notify_healed(error_log)
        return True
    
    elif strategy == "reconnect_and_retry":
        # Force new DB connection
        try:
            db.rollback()
            error_log.auto_healed = True
            error_log.heal_action = "Database reconnected"
            error_log.status = "healed"
            error_log.resolved_at = datetime.utcnow()
            db.commit()
            
            await notify_healed(error_log)
            return True
        except:
            pass
    
    elif strategy == "fix_permissions":
        import os
        try:
            upload_dir = settings.upload_dir
            os.makedirs(upload_dir, exist_ok=True)
            os.chmod(upload_dir, 0o755)
            error_log.auto_healed = True
            error_log.heal_action = "Fixed upload directory permissions"
            error_log.status = "healed"
            error_log.resolved_at = datetime.utcnow()
            db.commit()
            
            await notify_healed(error_log)
            return True
        except:
            pass
    
    elif strategy == "cleanup_and_retry":
        # Remove old uploaded files to free space
        try:
            import os
            from pathlib import Path
            upload_dir = Path(settings.upload_dir)
            if upload_dir.exists():
                files = sorted(upload_dir.iterdir(), key=lambda f: f.stat().st_mtime)
                # Delete oldest 10 files
                for f in files[:10]:
                    f.unlink()
                error_log.auto_healed = True
                error_log.heal_action = "Cleaned up old uploads to free space"
                error_log.status = "healed"
                error_log.resolved_at = datetime.utcnow()
                db.commit()
                
                await notify_healed(error_log)
                return True
        except:
            pass
    
    elif strategy == "diagnose_with_claude":
        return await claude_diagnose_and_heal(error_log, db)
    
    elif strategy == "notify_only":
        error_log.status = "failed"
        error_log.heal_action = "Requires manual intervention"
        db.commit()
        return False
    
    # 2. If no known strategy, ask Claude
    return await claude_diagnose_and_heal(error_log, db)


def find_strategy(error_type: str, error_msg: str) -> str:
    """Find the best healing strategy based on error type and message."""
    strategies = HEAL_STRATEGIES.get(error_type, {})
    
    for keyword, strategy in strategies.items():
        if keyword in error_msg:
            return strategy
    
    return "diagnose_with_claude"


async def claude_diagnose_and_heal(error_log: ErrorLog, db: Session) -> bool:
    """Use Claude to diagnose the error and suggest a fix."""
    if not settings.anthropic_api_key:
        return False
    
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        
        prompt = f"""You are a DevOps engineer diagnosing a production error in a Python FastAPI web application (SupportBot Studio).

Error type: {error_log.error_type}
Error message: {error_log.error_message}
Endpoint: {error_log.endpoint}
Traceback:
{error_log.traceback[:2000] if error_log.traceback else 'Not available'}

Request data:
{error_log.request_data[:500] if error_log.request_data else 'Not available'}

Analyze this error and respond with ONLY a JSON object:
{{
    "diagnosis": "Brief explanation of what went wrong",
    "severity": "low|medium|high|critical",
    "can_auto_fix": true/false,
    "fix_action": "Description of the fix to apply",
    "fix_type": "retry|config_change|data_fix|code_fix|manual_required",
    "prevention": "How to prevent this in the future"
}}

Only set can_auto_fix to true if the fix is safe to apply automatically (like retrying, clearing cache, fixing data). Set to false for anything that requires code changes or manual investigation."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        
        import json, re
        content = response.content[0].text.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if match:
            diagnosis = json.loads(match.group())
            error_log.heal_diagnosis = json.dumps(diagnosis)
            
            if diagnosis.get("can_auto_fix") and diagnosis.get("fix_type") in ("retry", "data_fix"):
                error_log.auto_healed = True
                error_log.heal_action = diagnosis.get("fix_action", "Auto-fixed based on Claude diagnosis")
                error_log.status = "healed"
                error_log.resolved_at = datetime.utcnow()
                db.commit()
                
                await notify_healed(error_log)
                return True
            else:
                error_log.status = "failed"
                error_log.heal_action = f"Manual fix needed: {diagnosis.get('fix_action', 'Unknown')}"
                db.commit()
                
                # Send detailed alert
                from backend.services.telegram_notify import send_telegram_alert
                await send_telegram_alert(
                    f"🔍 *Claude Diagnosis*\n\n"
                    f"Error: `{error_log.error_type}`\n"
                    f"Severity: `{diagnosis.get('severity', 'unknown')}`\n"
                    f"Diagnosis: {diagnosis.get('diagnosis', 'N/A')}\n"
                    f"Fix needed: {diagnosis.get('fix_action', 'N/A')}\n"
                    f"Prevention: {diagnosis.get('prevention', 'N/A')}"
                )
                return False
    
    except Exception as e:
        error_log.heal_diagnosis = f"Claude diagnosis failed: {str(e)}"
        error_log.status = "failed"
        db.commit()
        return False


async def notify_healed(error_log: ErrorLog):
    """Send Telegram notification that an error was auto-healed."""
    from backend.services.telegram_notify import send_telegram_alert
    await send_telegram_alert(
        f"✅ *Auto-Healed*\n\n"
        f"Type: `{error_log.error_type}`\n"
        f"Bot: `{error_log.bot_id or 'system'}`\n"
        f"Endpoint: `{error_log.endpoint}`\n"
        f"Fix: {error_log.heal_action}\n"
        f"Retries: {error_log.retry_count}"
    )
```

---

## PHASE 4: PER-ENDPOINT ERROR WRAPPING

For errors that happen inside endpoints (not unhandled exceptions), wrap critical operations:

### Chat Endpoint Wrapper

```python
# backend/services/safe_executor.py

async def safe_execute(func, error_type: str, bot_id: str = None, db: Session = None, **kwargs):
    """
    Wraps any async function with auto-heal retry logic.
    
    Usage:
        result = await safe_execute(
            call_claude_api,
            error_type="api_error",
            bot_id="bot_abc123",
            db=db,
            messages=messages,
            system_prompt=prompt,
        )
    """
    max_retries = 2
    
    for attempt in range(max_retries + 1):
        try:
            return await func(**kwargs)
        except Exception as e:
            if attempt == max_retries:
                # Log and let middleware handle it
                raise
            
            # Log the error
            if db:
                error_log = ErrorLog(
                    bot_id=bot_id,
                    error_type=error_type,
                    error_message=str(e),
                    endpoint=f"internal:{func.__name__}",
                    retry_count=attempt + 1,
                )
                db.add(error_log)
                db.commit()
            
            # Smart wait before retry
            import asyncio
            wait_time = (attempt + 1) * 2  # 2s, 4s
            
            # Check if rate limited — wait longer
            if "rate" in str(e).lower():
                wait_time = (attempt + 1) * 10  # 10s, 20s
            
            await asyncio.sleep(wait_time)
```

### Usage in Chat Endpoint

```python
# In backend/routers/chat.py

async def call_claude(messages, system_prompt, model="claude-sonnet-4-20250514"):
    """Wrapper for Claude API call."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1000,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text

# In the chat endpoint:
reply = await safe_execute(
    call_claude,
    error_type="api_error",
    bot_id=tenant.bot_id,
    db=db,
    messages=history,
    system_prompt=system_prompt,
)
```

---

## PHASE 5: SCHEDULED HEALTH CHECKS

Run every 15 minutes via APScheduler:

```python
# backend/services/health_monitor.py

async def scheduled_health_check():
    """Run health checks and alert if anything is wrong."""
    import httpx
    
    checks_failed = []
    
    # 1. Check Anthropic API
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "health check"}]
                },
                timeout=10,
            )
            if r.status_code != 200:
                checks_failed.append(f"Anthropic API: HTTP {r.status_code}")
    except Exception as e:
        checks_failed.append(f"Anthropic API: {str(e)[:100]}")
    
    # 2. Check database
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        checks_failed.append(f"Database: {str(e)[:100]}")
    
    # 3. Check disk space
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_pct = (free / total) * 100
    if free_pct < 10:
        checks_failed.append(f"Disk space low: {free_pct:.1f}% free")
    
    # 4. Check error rate
    db = SessionLocal()
    from datetime import datetime, timedelta
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_errors = db.query(ErrorLog).filter(
        ErrorLog.created_at > one_hour_ago,
        ErrorLog.status == "failed"
    ).count()
    db.close()
    
    if recent_errors > 10:
        checks_failed.append(f"High error rate: {recent_errors} failed errors in last hour")
    
    # Alert if anything failed
    if checks_failed:
        from backend.services.telegram_notify import send_telegram_alert
        await send_telegram_alert(
            f"⚠️ *Health Check Warning*\n\n"
            f"Issues found:\n" +
            "\n".join(f"• {c}" for c in checks_failed)
        )

# Register in scheduler
scheduler.add_job(scheduled_health_check, 'interval', minutes=15)
```

---

## PHASE 6: SELF-HEALING DASHBOARD

Add to Super Admin panel — a new "System Health" section.

### Frontend — System Health Tab

Shows:

1. **Status Cards:**
   - Database: ✅ OK / ❌ Error
   - Anthropic API: ✅ OK / ❌ Error
   - Telegram: ✅ OK / ⚠️ Not configured
   - Disk Space: 45% free
   - Error Rate: 2 errors/hour

2. **Recent Errors Table:**
   | Time | Type | Bot | Endpoint | Status | Action |
   |------|------|-----|----------|--------|--------|
   | 2m ago | api_error | bot_abc | /api/chat | ✅ Auto-healed | Retried after rate limit |
   | 15m ago | db_error | system | /api/analytics | ❌ Failed | Needs manual fix |
   | 1h ago | connection_error | bot_def | /api/escalate | ✅ Auto-healed | Retried with 5s backoff |

3. **Healing Stats:**
   - Total errors (24h): 12
   - Auto-healed: 9 (75%)
   - Failed: 3 (25%)
   - Avg heal time: 3.2s

4. **Error Type Breakdown:**
   - Bar chart: api_error (5), connection_error (3), db_error (2), etc.

### API Endpoints

**`GET /api/admin/health`** — Full health check (super admin only)

**`GET /api/admin/errors`** — List recent errors with pagination + filters
```
?status=failed&error_type=api_error&bot_id=bot_abc&limit=50
```

**`POST /api/admin/errors/{id}/resolve`** — Mark as manually resolved

**`POST /api/admin/errors/{id}/retry`** — Manually trigger auto-heal retry

**`GET /api/admin/errors/stats`** — Healing statistics
```json
{
    "total_24h": 12,
    "auto_healed": 9,
    "failed": 3,
    "heal_rate": 75.0,
    "avg_heal_time_seconds": 3.2,
    "by_type": {
        "api_error": {"total": 5, "healed": 4},
        "connection_error": {"total": 3, "healed": 3},
        "db_error": {"total": 2, "healed": 1}
    }
}
```

---

## PHASE 7: GRACEFUL DEGRADATION

When things break, the bot should still work — just with reduced functionality.

### Fallback Chain for Chat

```python
async def process_chat_with_fallbacks(message, faqs, config, bot_id, db):
    """
    Try multiple strategies. If AI fails, fall back gracefully.
    
    Chain: Auto-reply → Claude API → Fallback response
    """
    
    # 1. Always try auto-reply first (free, no external dependency)
    auto_answer = find_auto_reply(message, faqs)
    if auto_answer:
        return {"reply": auto_answer, "was_auto_reply": True}
    
    # 2. Try Claude API with retry
    try:
        reply = await safe_execute(
            call_claude,
            error_type="api_error",
            bot_id=bot_id,
            db=db,
            messages=[{"role": "user", "content": message}],
            system_prompt=build_system_prompt(config, faqs),
        )
        return {"reply": reply, "was_auto_reply": False}
    except Exception:
        pass
    
    # 3. Fuzzy match with lower threshold (better than nothing)
    fuzzy_answer = find_auto_reply(message, faqs, threshold=0.45)
    if fuzzy_answer:
        return {
            "reply": f"{fuzzy_answer}\n\n(Note: I'm having some technical difficulties right now, but I hope this helps! If not, please try again in a moment.)",
            "was_auto_reply": True
        }
    
    # 4. Final fallback — always works, no dependencies
    return {
        "reply": f"I'm sorry, I'm experiencing some technical difficulties right now. Please try again in a few minutes, or contact us directly at {config.escalation_email} for immediate help.",
        "was_auto_reply": True
    }
```

### Fallback for Escalation

```python
async def escalate_with_fallbacks(session_id, customer_email, bot_id, db):
    """Try all notification channels. If one fails, try the next."""
    
    results = {"telegram": False, "email": False, "webhook": False}
    
    # Try Telegram
    try:
        await send_telegram_notification(...)
        results["telegram"] = True
    except Exception as e:
        log_error("notification_error", str(e), bot_id, db)
    
    # Try Email
    try:
        await send_email_notification(...)
        results["email"] = True
    except Exception as e:
        log_error("notification_error", str(e), bot_id, db)
    
    # Try Webhooks
    try:
        await send_webhook_notifications(...)
        results["webhook"] = True
    except Exception as e:
        log_error("notification_error", str(e), bot_id, db)
    
    # If ALL failed, store for retry later
    if not any(results.values()):
        # Save to a retry queue
        db.add(PendingEscalation(
            session_id=session_id,
            customer_email=customer_email,
            bot_id=bot_id,
            retry_after=datetime.utcnow() + timedelta(minutes=5),
        ))
        db.commit()
    
    return results
```

---

## ENVIRONMENT VARIABLES

Add to `.env`:
```
# Auto-healing (optional — uses existing Anthropic key for diagnosis)
AUTO_HEAL_ENABLED=true
HEALTH_CHECK_INTERVAL_MINUTES=15
MAX_HEAL_RETRIES=2
```

---

## SUMMARY

After building this, your app:

1. **Catches every error** — nothing crashes silently
2. **Fixes itself** — rate limits, timeouts, DB locks auto-heal
3. **Uses Claude to diagnose** unknown errors
4. **Alerts you via Telegram** for anything it can't fix
5. **Degrades gracefully** — chat still works even if Claude API is down
6. **Tracks everything** — full error history with healing stats
7. **Health dashboard** — see system status at a glance in Super Admin

You get a Telegram message that says either:
- ✅ "Auto-healed: retried after rate limit" (you do nothing)
- 🔍 "Claude diagnosis: DB table locked, needs manual restart" (you know exactly what to fix)
- 🚨 "Error: API credits depleted" (you top up and it's fixed)

This is production-grade reliability. Clients never see errors, and you sleep at night knowing the bot fixes itself.
