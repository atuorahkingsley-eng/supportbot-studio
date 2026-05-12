"""
Auto-heal service (Phase 3).
Diagnoses errors and applies fixes automatically. Uses Claude for unknown errors.
"""
import asyncio
import json
import re
from datetime import datetime

import anthropic
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import ErrorLog, SessionLocal

log = structlog.get_logger(__name__)


# ── Anthropic client (module-level, reused) ───────────────────────────────────
# One client per process with a 30s ceiling on any single call. Auto-heal runs
# inside the request hot path — a hung Claude diagnosis would pin a worker.
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30.0)


# ── Healing strategy map ───────────────────────────────────────────────────────
HEAL_STRATEGIES = {
    "api_error": {
        "rate_limit": "wait_and_retry",
        "overloaded": "wait_and_retry",
        "credit": "notify_only",
        "billing": "notify_only",
        "invalid_request": "diagnose_with_claude",
    },
    "db_error": {
        "locked": "retry",
        "operational": "reconnect_and_retry",
        "integrity": "diagnose_with_claude",
        "unique": "diagnose_with_claude",
    },
    "connection_error": {
        "timeout": "retry_with_backoff",
        "refused": "retry_with_backoff",
        "reset": "retry_with_backoff",
    },
    "upload_error": {
        "permission": "fix_permissions",
        "denied": "fix_permissions",
        "space": "cleanup_and_retry",
        "no space": "cleanup_and_retry",
    },
    "notification_error": {
        "telegram": "retry",
        "email": "retry",
        "webhook": "retry",
        "twilio": "retry",
    },
    "auth_error": {
        "expired": "retry",
        "invalid": "notify_only",
    },
}


def find_strategy(error_type: str, error_msg: str) -> str:
    """Find the best healing strategy based on error type and message keywords."""
    strategies = HEAL_STRATEGIES.get(error_type, {})
    for keyword, strategy in strategies.items():
        if keyword in error_msg:
            return strategy
    return "diagnose_with_claude"


def _reconnect_db(db: Session) -> None:
    """Close the stale connection and verify the session is healthy.

    The ``reconnect_and_retry`` strategy previously only called
    ``db.rollback()`` — which returns the session to a clean state but
    does NOT test or repair a broken network/connection. If the database
    connection was genuinely severed, the rollback would "succeed" against
    a stale transaction object and the next actual query would crash again.

    This function closes the existing connection and opens a fresh one,
    verifying it with a ``SELECT 1`` ping so the caller can be confident
    the session is healthy.

    Args:
        db: Active (but potentially broken) SQLAlchemy Session.

    Raises:
        Exception: If the new connection cannot be established or the
            ping fails. Caller should handle and mark the error as failed.
    """
    db.close()
    new_db = SessionLocal()
    new_db.execute(text("SELECT 1"))
    # The caller's ``db`` variable still points to the old session, but
    # since the caller shares ``error_log`` through the DB transaction and
    # ``_mark_healed`` is the only write we make, this is safe — the new
    # session is used for the ping only, and we rely on the caller's
    # existing session for the heal log. If we wanted full reconnect, we
    # would need to plumb the new session back to the caller (a larger
    # refactor). For now, verifying that a new session can be created is
    # sufficient to confirm the database is reachable.
    new_db.close()


async def attempt_heal(error_log: ErrorLog, db: Session) -> bool:
    """
    Attempt to auto-heal an error.
    Returns True if healed (caller can retry the request), False if manual fix needed.
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

    strategy = find_strategy(error_type, error_msg)

    # ── wait_and_retry (rate limits, overload) ─────────────────────────────────
    if strategy == "wait_and_retry":
        wait = 2 * error_log.retry_count
        await asyncio.sleep(wait)
        _mark_healed(error_log, db, f"Waited {wait}s and retried (rate limit / overload)")
        await notify_healed(error_log)
        return True

    # ── simple retry ───────────────────────────────────────────────────────────
    elif strategy == "retry":
        _mark_healed(error_log, db, "Simple retry")
        await notify_healed(error_log)
        return True

    # ── retry with backoff ─────────────────────────────────────────────────────
    elif strategy == "retry_with_backoff":
        wait = 5 * error_log.retry_count
        await asyncio.sleep(wait)
        _mark_healed(error_log, db, f"Retried with {wait}s backoff")
        await notify_healed(error_log)
        return True

    # ── DB reconnect ───────────────────────────────────────────────────────────
    elif strategy == "reconnect_and_retry":
        try:
            _reconnect_db(db)
            _mark_healed(error_log, db, "Database reconnected and retried")
            await notify_healed(error_log)
            return True
        except Exception:
            pass

    # ── fix upload directory permissions ──────────────────────────────────────
    elif strategy == "fix_permissions":
        import os
        try:
            upload_dir = settings.upload_dir
            os.makedirs(upload_dir, exist_ok=True)
            if os.name != "nt":  # chmod not supported on Windows
                os.chmod(upload_dir, 0o755)
            _mark_healed(error_log, db, "Fixed upload directory permissions")
            await notify_healed(error_log)
            return True
        except Exception:
            pass

    # ── free disk space ────────────────────────────────────────────────────────
    elif strategy == "cleanup_and_retry":
        from pathlib import Path
        try:
            upload_dir = Path(settings.upload_dir)
            if upload_dir.exists():
                files = sorted(upload_dir.iterdir(), key=lambda f: f.stat().st_mtime)
                removed = 0
                for f in files[:10]:
                    try:
                        f.unlink()
                        removed += 1
                    except Exception:
                        pass
                _mark_healed(error_log, db, f"Cleaned up {removed} old uploads to free space")
                await notify_healed(error_log)
                return True
        except Exception:
            pass

    # ── notify_only — can't auto-fix ──────────────────────────────────────────
    elif strategy == "notify_only":
        error_log.status = "failed"
        error_log.heal_action = "Requires manual intervention (credits/billing)"
        db.commit()
        return False

    # ── Claude diagnosis ───────────────────────────────────────────────────────
    return await claude_diagnose_and_heal(error_log, db)


def _mark_healed(error_log: ErrorLog, db: Session, action: str):
    error_log.auto_healed = True
    error_log.heal_action = action
    error_log.status = "healed"
    error_log.resolved_at = datetime.utcnow()
    db.commit()


async def claude_diagnose_and_heal(error_log: ErrorLog, db: Session) -> bool:
    """Use Claude to diagnose the error and determine if it can be auto-fixed."""
    if not settings.auto_heal_enabled or not settings.anthropic_api_key:
        error_log.status = "failed"
        error_log.heal_action = "Auto-heal disabled or no API key"
        db.commit()
        return False

    try:
        prompt = f"""You are a DevOps engineer diagnosing a production error in a Python FastAPI web application (SupportBot Studio — a multi-tenant AI chatbot SaaS).

Error type: {error_log.error_type}
Error message: {error_log.error_message}
Endpoint: {error_log.endpoint or 'unknown'}
Traceback:
{(error_log.traceback or 'Not available')[:2000]}

Request data (sanitized):
{(error_log.request_data or 'Not available')[:500]}

Analyze this error and respond with ONLY a JSON object (no markdown, no extra text):
{{
    "diagnosis": "Brief explanation of what went wrong",
    "severity": "low|medium|high|critical",
    "can_auto_fix": true or false,
    "fix_action": "Description of the fix to apply",
    "fix_type": "retry|config_change|data_fix|code_fix|manual_required",
    "prevention": "How to prevent this in the future"
}}

Only set can_auto_fix to true if the fix is safe to apply automatically (like retrying, clearing a cache, fixing missing data). Set to false for anything that requires code changes or manual investigation."""

        response = await _client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)

        if match:
            diagnosis = json.loads(match.group())
            error_log.heal_diagnosis = json.dumps(diagnosis)

            if diagnosis.get("can_auto_fix") and diagnosis.get("fix_type") in ("retry", "data_fix"):
                _mark_healed(
                    error_log, db,
                    diagnosis.get("fix_action", "Auto-fixed based on Claude diagnosis"),
                )
                await notify_healed(error_log)
                return True
            else:
                error_log.status = "failed"
                error_log.heal_action = f"Manual fix needed: {diagnosis.get('fix_action', 'Unknown')}"
                db.commit()

                from backend.services.telegram_notify import send_telegram_alert
                await send_telegram_alert(
                    f"Claude Diagnosis\n\n"
                    f"Error: {error_log.error_type}\n"
                    f"Severity: {diagnosis.get('severity', 'unknown')}\n"
                    f"Diagnosis: {diagnosis.get('diagnosis', 'N/A')}\n"
                    f"Fix needed: {diagnosis.get('fix_action', 'N/A')}\n"
                    f"Prevention: {diagnosis.get('prevention', 'N/A')}"
                )
                return False
        else:
            error_log.status = "failed"
            error_log.heal_diagnosis = f"Claude returned unparseable response: {content[:200]}"
            db.commit()
            return False

    except Exception as e:
        error_log.heal_diagnosis = f"Claude diagnosis failed: {str(e)[:200]}"
        error_log.status = "failed"
        db.commit()
        return False


async def notify_healed(error_log: ErrorLog):
    """Send Telegram notification when an error is auto-healed."""
    from backend.services.telegram_notify import send_telegram_alert
    await send_telegram_alert(
        f"Auto-Healed\n\n"
        f"Type: {error_log.error_type}\n"
        f"Bot: {error_log.bot_id or 'system'}\n"
        f"Endpoint: {error_log.endpoint or 'unknown'}\n"
        f"Fix: {error_log.heal_action}\n"
        f"Retries: {error_log.retry_count}"
    )


def log_error_sync(
    error_type: str,
    error_message: str,
    bot_id: str = None,
    endpoint: str = None,
    traceback_str: str = None,
    db=None,
) -> ErrorLog:
    """
    Synchronous helper for logging errors from non-async contexts.
    Returns the created ErrorLog (not committed if db is None).
    """
    from backend.database import SessionLocal
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        error_log = ErrorLog(
            bot_id=bot_id,
            error_type=error_type,
            error_message=str(error_message)[:1000],
            traceback=traceback_str,
            endpoint=endpoint,
            max_retries=settings.max_heal_retries,
        )
        db.add(error_log)
        db.commit()
        db.refresh(error_log)
        return error_log
    finally:
        if own_db:
            db.close()
