"""Usage alert email system for overage warnings.

Sends threshold-based warnings (80%, 95%, limit_reached) via Resend HTTP API.
Each warning is tracked in the ``usage_alerts`` table to prevent duplicate
alerts per tenant per month per threshold.

All public functions handle their own deduplication via ``should_send_warning``
and ``record_warning_sent``. Background tasks receive string identifiers
(bot_id, threshold) only — never ORM objects.
"""
import httpx
import structlog
from datetime import datetime, timezone
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.database import (
    UsageAlert, Tenant, BotConfig, SessionLocal, format_message_limit,
)

log = structlog.get_logger(__name__)

ThresholdType = Literal["warning_80", "warning_95", "limit_reached"]


def should_send_warning(db: Session, bot_id: str, threshold: ThresholdType) -> bool:
    """Check if a warning has already been sent this month for this threshold.

    Args:
        db: Database session.
        bot_id: Tenant bot ID.
        threshold: Warning threshold level.

    Returns:
        ``True`` if the warning has NOT been sent yet this month.
    """
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    existing = db.query(UsageAlert).filter(
        UsageAlert.bot_id == bot_id,
        UsageAlert.month == month,
        UsageAlert.threshold == threshold,
    ).first()
    return existing is None


def record_warning_sent(db: Session, bot_id: str, threshold: ThresholdType) -> None:
    """Record that a warning was sent for this tenant/month/threshold.

    Silently handles race conditions via ``IntegrityError`` catch on the
    unique constraint. Idempotent — safe to call concurrently.

    Args:
        db: Database session.
        bot_id: Tenant bot ID.
        threshold: Warning threshold level.
    """
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        alert = UsageAlert(bot_id=bot_id, month=month, threshold=threshold)
        db.add(alert)
        db.commit()
    except IntegrityError:
        db.rollback()


def prune_old_alerts(db: Session) -> int:
    """Delete usage alerts older than 60 days.

    Called by the monthly reset job in ``main.py`` to prevent unbounded table growth.

    Args:
        db: Database session.

    Returns:
        Number of rows deleted.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    deleted = db.query(UsageAlert).filter(UsageAlert.sent_at < cutoff).delete()
    db.commit()
    if deleted:
        log.info("usage_alerts_pruned", deleted=deleted)
    return deleted


async def send_usage_warning_task(bot_id: str, threshold: ThresholdType) -> None:
    """Background task runner for usage warning emails.

    Opens its own DB session — the request session is closed before this task
    runs. Handles full lifecycle: dedup check, email send, record sent.

    Args:
        bot_id: Tenant bot ID string.
        threshold: Warning threshold level string.
    """
    db = None
    try:
        db = SessionLocal()
        tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
        bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
        if not tenant or not bot_config:
            log.warning("usage_warning_skipped", reason="tenant_or_config_not_found", bot_id=bot_id)
            return
        if not should_send_warning(db, bot_id, threshold):
            return
        ok = await _send_usage_warning_api(tenant, bot_config, threshold)
        if ok:
            record_warning_sent(db, bot_id, threshold)
    finally:
        if db is not None:
            db.close()


async def _send_usage_warning_api(tenant: Tenant, bot_config: BotConfig, threshold: ThresholdType) -> bool:
    """Send usage warning email via Resend HTTP API.

    Args:
        tenant: Tenant object with usage data.
        bot_config: Bot config with escalation email.
        threshold: Warning threshold level.

    Returns:
        ``True`` if the email was sent successfully.
    """
    if not settings.resend_api_key:
        log.error("usage_warning_skipped", reason="RESEND_API_KEY not configured")
        return False
    if not bot_config.escalation_email:
        log.warning("usage_warning_skipped", reason="no_escalation_email", bot_id=tenant.bot_id)
        return False

    used = tenant.messages_used_this_month
    limit = tenant.monthly_message_limit
    pct = int(used / limit * 100) if limit > 0 else 0
    limit_display = format_message_limit(limit)

    subject_map = {
        "warning_80": f"[{bot_config.business_name}] 80% of monthly messages used",
        "warning_95": f"[{bot_config.business_name}] 95% of monthly messages used — action needed",
        "limit_reached": f"[{bot_config.business_name}] Monthly message limit reached",
    }

    action_map = {
        "warning_80": "You're on track. No action needed yet.",
        "warning_95": "Consider upgrading your plan to avoid service interruption this month.",
        "limit_reached": (
            "Your bot is currently showing a limit-reached message to visitors. "
            "Upgrade your plan to restore full service immediately."
        ),
    }

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:560px;margin:0 auto;">
  <div style="background:#0F6E56;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="color:#fff;margin:0;">Usage Alert — {bot_config.business_name}</h2>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
    <p style="font-size:32px;font-weight:700;color:#1a1a1a;margin:0 0 8px;">{pct}% used</p>
    <p style="color:#666;margin:0 0 16px;">{used:,} of {limit_display} messages this month</p>
    <div style="background:#f7f7f7;padding:12px;border-radius:6px;margin-bottom:16px;">
      <p style="margin:0;color:#333;">{action_map[threshold]}</p>
    </div>
    <a href="https://supportbot-studio.onrender.com" style="display:inline-block;background:#0F6E56;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;">Upgrade Plan →</a>
    <hr style="border:none;border-top:1px solid #e0e0e0;margin:20px 0;">
    <p style="color:#999;font-size:12px;margin:0;">Sent by SupportBot Studio<br>Plan: {tenant.plan.title()} | Resets: 1st of next month</p>
  </div>
</body>
</html>
""".strip()

    body_text = f"""
Usage Alert — {bot_config.business_name}

{pct}% used — {used:,} of {limit_display} messages this month.

{action_map[threshold]}

Upgrade your plan:
https://supportbot-studio.onrender.com

Plan: {tenant.plan.title()}
Resets: 1st of next month
Sent by SupportBot Studio
""".strip()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.resend_from_email,
                    "to": [bot_config.escalation_email],
                    "subject": subject_map[threshold],
                    "html": body_html,
                    "text": body_text,
                },
                timeout=15,
            )
            ok = response.status_code == 200
            if ok:
                log.info("usage_warning_sent", bot_id=tenant.bot_id, threshold=threshold, pct=pct)
            else:
                log.error("usage_warning_resend_failed", status=response.status_code, bot_id=tenant.bot_id)
            return ok
    except Exception as e:
        log.error("usage_warning_failed", error=str(e), bot_id=tenant.bot_id)
        return False
