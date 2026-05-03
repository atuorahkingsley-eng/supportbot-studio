from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import (
    get_db, Conversation, Message, WebhookConfig, BotConfig, Tenant,
    PendingEscalation, ErrorLog,
)
from backend.services.telegram_notify import send_telegram_message
from backend.services.email_notify import send_emailjs
from backend.services.webhook_sender import dispatch_webhook
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter

router = APIRouter(prefix="/api/escalate", tags=["escalate"])


class EscalateRequest(BaseModel):
    session_id: str
    customer_email: Optional[str] = None


class PublicEscalateRequest(BaseModel):
    bot_id: str
    session_id: str
    customer_email: Optional[str] = None


def _log_notification_error(db: Session, bot_id: str, channel: str, error: Exception):
    """Log a failed notification attempt to ErrorLog."""
    try:
        error_log = ErrorLog(
            bot_id=bot_id,
            error_type="notification_error",
            error_message=f"{channel}: {str(error)[:200]}",
            endpoint="/api/escalate",
            status="failed",
        )
        db.add(error_log)
        db.commit()
    except Exception:
        pass


async def _do_escalate(session_id: str, customer_email: Optional[str], bot_id: str, db: Session):
    """
    Shared escalation logic.
    Phase 7: Each notification channel wrapped individually — partial success is OK.
    If ALL channels fail, store a PendingEscalation for scheduler retry.
    """
    # Tenant isolation: a session_id alone is NOT a sufficient lookup key —
    # an attacker could pass another tenant's UUID and route their transcript
    # to our notification channels. Always pin to (session_id, bot_id).
    convo = db.query(Conversation).filter(
        Conversation.session_id == session_id,
        Conversation.bot_id == bot_id,
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(Message).filter(
        Message.conversation_id == convo.id
    ).order_by(Message.created_at.asc()).all()

    bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    business_name = bot_config.business_name if bot_config else "SupportBot"

    transcript_lines = []
    for msg in messages:
        role = "Customer" if msg.role == "user" else "Bot"
        transcript_lines.append(f"{role}: {msg.content}")
    transcript = "\n".join(transcript_lines)

    email = customer_email or convo.customer_email or "Unknown"
    summary = (
        f"SupportBot Escalation — {business_name}\n"
        f"Customer: {email}\n"
        f"Messages: {len(messages)}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"Transcript:\n{transcript}"
    )

    results = {"telegram": False, "email": False}

    # ── Telegram: platform-wide (try independently) ───────────────────────────
    # Always fires (when settings.telegram_chat_id is configured) so the
    # platform operator keeps visibility on every escalation.
    try:
        tg_ok = await send_telegram_message(summary)
        results["telegram"] = tg_ok
    except Exception as e:
        _log_notification_error(db, bot_id, "telegram", e)

    # ── Telegram: per-tenant override (try independently) ─────────────────────
    # Sent IN ADDITION TO the platform-wide chat — never instead of it.
    # Only fires when the tenant has set their own telegram_handle on
    # BotConfig. Tracked separately so partial failure (platform OK,
    # tenant fail or vice-versa) is visible in the response.
    if bot_config and bot_config.telegram_handle:
        try:
            tg_tenant_ok = await send_telegram_message(
                summary,
                chat_id_override=bot_config.telegram_handle,
            )
            results["telegram_tenant"] = tg_tenant_ok
        except Exception as e:
            _log_notification_error(db, bot_id, "telegram_tenant", e)
            results["telegram_tenant"] = False

    # ── Email (try independently) ──────────────────────────────────────────────
    if bot_config and getattr(bot_config, "escalation_email", None):
        try:
            email_ok = await send_emailjs(
                subject=f"Support Escalation — {business_name}",
                message=summary,
                to_email=bot_config.escalation_email,
            )
            results["email"] = email_ok
        except Exception as e:
            _log_notification_error(db, bot_id, "email", e)

    # ── Webhooks (try each independently) ─────────────────────────────────────
    webhooks = db.query(WebhookConfig).filter(
        WebhookConfig.bot_id == bot_id,
        WebhookConfig.enabled == True,
        WebhookConfig.notify_on.in_(["escalation", "all"]),
    ).all()

    for wh in webhooks:
        try:
            if wh.platform == "slack":
                text = f"SupportBot Escalation\nCustomer: {email}\nMessages: {len(messages)}\n\n{transcript}"
            elif wh.platform == "discord":
                text = f"**SupportBot Escalation**\nCustomer: {email}\nMessages: {len(messages)}\n\n{transcript}"
            else:
                text = summary
            ok = await dispatch_webhook(
                wh.platform,
                wh.webhook_url,
                text,
                secret=wh.secret,
                events=wh.events,
                event="escalation",
            )
            results[f"webhook_{wh.platform}_{wh.id}"] = ok
        except Exception as e:
            _log_notification_error(db, bot_id, f"webhook_{wh.platform}", e)
            results[f"webhook_{wh.platform}_{wh.id}"] = False

    # ── If ALL channels failed, queue for retry ───────────────────────────────
    all_results = list(results.values())
    if all_results and not any(all_results):
        try:
            pending = PendingEscalation(
                bot_id=bot_id,
                session_id=session_id,
                customer_email=customer_email,
                retry_after=datetime.utcnow() + timedelta(minutes=5),
            )
            db.add(pending)
        except Exception:
            pass

    convo.escalated = True
    if customer_email:
        convo.customer_email = customer_email
    db.commit()

    return {"ok": True, "results": results}


# ── Public endpoint (embed widget) ────────────────────────────────────────────

@router.post("/public")
@limiter.limit("5/minute")
async def public_escalate(
    request: Request,
    data: PublicEscalateRequest,
    db: Session = Depends(get_db),
):
    """Escalation endpoint for the embeddable widget (no auth required).

    Rate-limited tighter than chat (5/min vs 20/min) — a single escalation
    fans out to Telegram + email + every configured webhook. Easy abuse
    vector if left wide open.
    """
    tenant = db.query(Tenant).filter(
        Tenant.bot_id == data.bot_id,
        Tenant.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Bot not found")
    return await _do_escalate(data.session_id, data.customer_email, data.bot_id, db)


# ── Authenticated endpoint (admin demo) ───────────────────────────────────────

@router.post("")
async def escalate(
    data: EscalateRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    return await _do_escalate(data.session_id, data.customer_email, tenant.bot_id, db)
