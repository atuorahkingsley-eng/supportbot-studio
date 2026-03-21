"""
Comprehensive health check endpoint (Phase 2).
Checks: database, Anthropic API, Telegram, disk space, error rate, tenants.
"""
import shutil
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db, ErrorLog, Tenant, FAQEntry

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    checks = {}

    # ── 1. Database ────────────────────────────────────────────────────────────
    try:
        db.execute(text("SELECT 1"))
        faq_count = db.query(FAQEntry).count()
        tenant_count = db.query(Tenant).count()
        checks["database"] = {
            "status": "ok",
            "faq_count": faq_count,
            "tenant_count": tenant_count,
        }
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)[:200]}

    # ── 2. Anthropic API ───────────────────────────────────────────────────────
    if settings.anthropic_api_key:
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
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=10,
                )
                # 200 = ok, 400 = bad request (key valid), 404 = model issue (key valid)
                # Only 401/403 mean the key itself is bad
                if r.status_code in (200, 400, 404):
                    checks["anthropic_api"] = {"status": "ok"}
                elif r.status_code in (401, 403):
                    checks["anthropic_api"] = {"status": "error", "code": r.status_code, "message": "Invalid API key"}
                else:
                    checks["anthropic_api"] = {
                        "status": "error",
                        "code": r.status_code,
                        "message": r.text[:200],
                    }
        except Exception as e:
            checks["anthropic_api"] = {"status": "error", "message": str(e)[:200]}
    else:
        checks["anthropic_api"] = {"status": "not_configured"}

    # ── 3. Telegram ────────────────────────────────────────────────────────────
    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
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
            checks["telegram"] = {"status": "error", "message": str(e)[:200]}
    else:
        checks["telegram"] = {"status": "not_configured"}

    # ── 4. Disk space ──────────────────────────────────────────────────────────
    try:
        import os
        disk_path = "C:\\" if os.name == "nt" else "/"
        total, used, free = shutil.disk_usage(disk_path)
        free_pct = round((free / total) * 100, 1)
        checks["disk"] = {
            "status": "ok" if free_pct > 10 else "warning" if free_pct > 5 else "error",
            "free_percent": free_pct,
            "free_gb": round(free / (1024 ** 3), 1),
        }
    except Exception as e:
        checks["disk"] = {"status": "error", "message": str(e)[:100]}

    # ── 5. Error rate (last hour) ──────────────────────────────────────────────
    try:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_errors = db.query(ErrorLog).filter(ErrorLog.created_at > one_hour_ago).count()
        failed_errors = db.query(ErrorLog).filter(
            ErrorLog.created_at > one_hour_ago,
            ErrorLog.status == "failed",
        ).count()
        checks["error_rate"] = {
            "status": "ok" if recent_errors < 5 else "warning" if recent_errors < 20 else "error",
            "errors_last_hour": recent_errors,
            "failed_last_hour": failed_errors,
        }
    except Exception:
        checks["error_rate"] = {"status": "ok", "errors_last_hour": 0, "failed_last_hour": 0}

    # ── 6. Active tenants ──────────────────────────────────────────────────────
    try:
        active_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
        checks["tenants"] = {"status": "ok", "active": active_tenants}
    except Exception as e:
        checks["tenants"] = {"status": "error", "message": str(e)[:100]}

    # ── Overall status ─────────────────────────────────────────────────────────
    statuses = [c.get("status", "ok") for c in checks.values()]
    overall = (
        "error" if "error" in statuses
        else "warning" if "warning" in statuses
        else "ok"
    )

    return {
        "status": overall,
        "checks": checks,
        "has_api_key": bool(settings.anthropic_api_key),
        "multi_tenant": True,
        "auto_reply_ready": checks.get("database", {}).get("faq_count", 0) > 0,
        "faq_count": checks.get("database", {}).get("faq_count", 0),
        "tenant_count": checks.get("database", {}).get("tenant_count", 0),
        "timestamp": datetime.utcnow().isoformat(),
    }
