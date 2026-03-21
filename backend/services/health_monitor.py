"""
Scheduled health monitor (Phase 5).
Runs every N minutes via APScheduler. Alerts via Telegram if anything is wrong.
"""
import shutil
from datetime import datetime, timedelta

import httpx

from backend.config import settings
from backend.database import SessionLocal, ErrorLog


async def scheduled_health_check():
    """
    Run health checks on a schedule. Send Telegram alert if anything fails.
    Registered in main.py lifespan with APScheduler interval job.
    """
    checks_failed = []

    # ── 1. Anthropic API ───────────────────────────────────────────────────────
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
                        "messages": [{"role": "user", "content": "health check"}],
                    },
                    timeout=10,
                )
                # 200/400/404 = API reachable, key valid; 401/403 = bad key; 5xx = API down
                if r.status_code in (401, 403):
                    checks_failed.append(f"Anthropic API: invalid key (HTTP {r.status_code})")
                elif r.status_code >= 500:
                    checks_failed.append(f"Anthropic API: server error (HTTP {r.status_code})")
        except Exception as e:
            checks_failed.append(f"Anthropic API: {str(e)[:100]}")

    # ── 2. Database ────────────────────────────────────────────────────────────
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        checks_failed.append(f"Database: {str(e)[:100]}")

    # ── 3. Disk space ──────────────────────────────────────────────────────────
    try:
        import os
        disk_path = "C:\\" if os.name == "nt" else "/"
        total, used, free = shutil.disk_usage(disk_path)
        free_pct = (free / total) * 100
        if free_pct < 10:
            checks_failed.append(f"Disk space low: {free_pct:.1f}% free")
    except Exception:
        pass

    # ── 4. Error rate (last hour) ──────────────────────────────────────────────
    try:
        db = SessionLocal()
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_failed = db.query(ErrorLog).filter(
            ErrorLog.created_at > one_hour_ago,
            ErrorLog.status == "failed",
        ).count()
        db.close()
        if recent_failed > 10:
            checks_failed.append(f"High error rate: {recent_failed} failed errors in last hour")
    except Exception:
        pass

    # ── Alert if anything failed ───────────────────────────────────────────────
    if checks_failed:
        from backend.services.telegram_notify import send_telegram_alert
        issues = "\n".join(f"* {c}" for c in checks_failed)
        await send_telegram_alert(
            f"Health Check Warning\n\n"
            f"Issues found:\n{issues}\n\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
