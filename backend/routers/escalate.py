from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
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
    convo = db.query(Conversation).filter(Conversation.session_id == session_id).first()
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

    # ── Telegram (try independently) ──────────────────────────────────────────
    try:
        tg_ok = await send_telegram_message(summary)
        results["telegram"] = tg_ok
    except Exception as e:
        _log_notification_error(db, bot_id, "telegram", e)

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
            ok = await dispatch_webhook(wh.platform, wh.webhook_url, text)
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
async def public_escalate(
    data: PublicEscalateRequest,
    db: Session = Depends(get_db),
):
    """Escalation endpoint for the embeddable widget (no auth required)."""
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
