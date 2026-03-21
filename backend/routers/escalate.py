from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, Conversation, Message, WebhookConfig, BotConfig
from backend.services.telegram_notify import send_telegram_message
from backend.services.email_notify import send_emailjs
from backend.services.webhook_sender import dispatch_webhook

router = APIRouter(prefix="/api/escalate", tags=["escalate"])


class EscalateRequest(BaseModel):
    session_id: str
    customer_email: Optional[str] = None


@router.post("")
async def escalate(data: EscalateRequest, db: Session = Depends(get_db)):
    convo = db.query(Conversation).filter(Conversation.session_id == data.session_id).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(Message).filter(
        Message.conversation_id == convo.id
    ).order_by(Message.created_at.asc()).all()

    bot_config = db.query(BotConfig).first()
    business_name = bot_config.business_name if bot_config else "SupportBot"

    # Format transcript
    transcript_lines = []
    for msg in messages:
        role = "Customer" if msg.role == "user" else "Bot"
        transcript_lines.append(f"{role}: {msg.content}")
    transcript = "\n".join(transcript_lines)

    email = data.customer_email or convo.customer_email or "Unknown"
    summary = (
        f"🚨 *SupportBot Escalation — {business_name}*\n"
        f"Customer: {email}\n"
        f"Messages: {len(messages)}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"Transcript:\n{transcript}"
    )

    results = {}

    # Telegram
    tg_ok = await send_telegram_message(summary)
    results["telegram"] = tg_ok

    # Email
    if bot_config and bot_config.escalation_email:
        email_ok = await send_emailjs(
            subject=f"Support Escalation — {business_name}",
            message=summary,
            to_email=bot_config.escalation_email,
        )
        results["email"] = email_ok

    # Webhooks
    webhooks = db.query(WebhookConfig).filter(
        WebhookConfig.enabled == True,
        WebhookConfig.notify_on.in_(["escalation", "all"]),
    ).all()

    for wh in webhooks:
        if wh.platform == "slack":
            text = f"🚨 *SupportBot Escalation*\nCustomer: {email}\nMessages: {len(messages)}\n\n{transcript}"
        elif wh.platform == "discord":
            text = f"🚨 **SupportBot Escalation**\nCustomer: {email}\nMessages: {len(messages)}\n\n{transcript}"
        else:
            text = summary

        ok = await dispatch_webhook(wh.platform, wh.webhook_url, text)
        results[f"webhook_{wh.platform}_{wh.id}"] = ok

    # Update conversation
    convo.escalated = True
    if data.customer_email:
        convo.customer_email = data.customer_email
    db.commit()

    return {"ok": True, "results": results}
