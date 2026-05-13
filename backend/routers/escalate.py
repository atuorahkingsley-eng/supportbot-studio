from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Optional

import structlog

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import (
    get_db, get_dialect, Conversation, Message, WebhookConfig, BotConfig, Tenant,
    PendingEscalation, ErrorLog, Lead, VisitorConversation,
)
from backend.services.telegram_notify import send_telegram_message
from backend.services.email_notify import send_emailjs
from backend.services.webhook_sender import dispatch_webhook
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter, check_bot_id_rate_limit
from slowapi.util import get_remote_address

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/escalate", tags=["escalate"])


# Valid values for the structured payload's "reason" field. Kept as a tuple so
# typo'd reasons surface at the call site instead of silently shipping garbage
# to webhook receivers.
_VALID_REASONS = ("customer_requested", "ai_escalated", "message_limit")


class EscalateRequest(BaseModel):
    """Authenticated escalation body — contact fields all optional.

    ``customer_email`` is kept for backward compat with existing clients;
    new callers should populate ``email`` (with optional ``name`` / ``phone``).
    When both are present, ``email`` wins.
    """
    session_id: str
    customer_email: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    reason: Optional[str] = "customer_requested"


class PublicEscalateRequest(BaseModel):
    bot_id: str
    session_id: str
    visitor_id: Optional[str] = None
    customer_email: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    reason: Optional[str] = "customer_requested"


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


def _resolve_contact(
    *,
    db: Session,
    bot_id: str,
<<<<<<< HEAD
    convo: Conversation,
    visitor_id: Optional[str] = None,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Resolve contact details for an escalation.

    Merges explicit request fields with prior Lead data from the
    same visitor. Priority: explicit args > prior Lead > conversation
    ``customer_email``.

    Args:
        db: Active SQLAlchemy session.
        bot_id: Tenant identifier; used to scope the Lead lookup.
        convo: Current conversation — provides legacy ``customer_email`` fallback.
        visitor_id: Resolved visitor identifier from the join table. If provided,
            used to look up prior Lead data for contact prefill.
        name: Contact name supplied on the escalate request, if any.
        email: Contact email supplied on the escalate request, if any.
        phone: Contact phone supplied on the escalate request, if any.

    Returns:
        Dict with exactly three keys (name, email, phone), each mapped to a
        str or None. Always returns all three keys so receivers can rely on
        shape stability.
    """
=======
    visitor_id: Optional[str],
    customer_email: Optional[str],
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
) -> dict[str, Optional[str]]:
    """Merge contact details supplied on this request with the visitor's history."""
>>>>>>> 2c222c975f68bd1a257a9d3eae0f3433363f10cb
    prior: Optional[Lead] = None
    if visitor_id:
        prior = (
            db.query(Lead)
            .filter(Lead.bot_id == bot_id, Lead.visitor_id == visitor_id)
            .order_by(Lead.created_at.desc())
            .first()
        )
    return {
        "name": name or (prior.name if prior else None),
        "email": email or (prior.email if prior else None) or customer_email,
        "phone": phone or (prior.phone if prior else None),
    }


async def _do_escalate(
    session_id: str,
    customer_email: Optional[str],
    bot_id: str,
    db: Session,
    *,
    visitor_id: Optional[str] = None,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    reason: Optional[str] = "customer_requested",
) -> dict[str, Any]:
    """Shared escalation logic — fan out to telegram, email, and webhooks.

    Each notification channel is wrapped individually so partial success is
    OK. If ALL channels fail, store a ``PendingEscalation`` for the
    scheduler to retry.

    New (additive) behaviours vs. the original implementation:

    1. Accepts ``name`` / ``email`` / ``phone`` and threads them through the
       webhook payload's ``contact`` block. Missing fields are resolved from
       prior Lead rows in the same visitor's history, so a visitor who filled
       the lead-capture form earlier still gets identified on escalation.
    2. Persists a Lead row of ``type="escalation"`` so the unified Leads tab
       can surface both buying-intent captures and human-support requests in
       one table.
    3. The custom_https webhook now carries a structured ``data`` envelope
       (``visitor_id``, ``bot_name``, ``reason``, ``message_count``, ``contact``)
       in addition to the legacy ``text`` summary — see
       ``send_custom_https_webhook`` for the full shape.
    4. Telegram / email summaries include a Name / Email / Phone block so
       human responders see the contact details inline.

    Args:
        session_id: Conversation session UUID — pinned with bot_id.
        customer_email: Legacy email-only contact field; ``email`` wins
            when both are supplied.
        bot_id: Tenant identifier; used for isolation and to scope all queries.
        db: Active SQLAlchemy session.
        name: Visitor-supplied name (from ContactForm).
        email: Visitor-supplied email; takes precedence over customer_email.
        phone: Visitor-supplied phone.
        reason: One of "customer_requested", "ai_escalated", "message_limit".
            Invalid values are normalised to "customer_requested" rather
            than rejected — we'd rather ship the escalation than 400 on
            a stale client.

    Returns:
        ``{"ok": True, "results": {<channel>: bool, ...}}`` when at least one
        channel delivered. Raises HTTPException(500) when every channel
        failed; a PendingEscalation row is queued for retry first.
    """
    # Tenant isolation: always pin to (session_id, bot_id) — session_id alone
    # is not a sufficient key. If no conversation exists yet (phrase-detection
    # escalation fires before any API message is sent), create a minimal one.
    convo = db.query(Conversation).filter(
        Conversation.session_id == session_id,
        Conversation.bot_id == bot_id,
    ).first()
    if not convo:
        convo = Conversation(session_id=session_id, bot_id=bot_id)
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # visitor_id lives in VisitorConversation (join table), not on Conversation.
    # Prefer the join-table value; fall back to the value passed on this request
    # (present when the embed widget sends it but no chat message preceded the
    # escalation, so no VisitorConversation row exists yet).
    vc_link = db.query(VisitorConversation).filter(
        VisitorConversation.conversation_id == convo.id,
    ).first()
    convo_visitor_id = (vc_link.visitor_id if vc_link else None) or visitor_id

    # If we know the visitor_id and there's no join-table row yet, create one
    # so downstream Lead lookups and visitor history features work normally.
    if convo_visitor_id and not vc_link:
        db.add(VisitorConversation(
            visitor_id=convo_visitor_id,
            conversation_id=convo.id,
            bot_id=bot_id,
        ))
        db.commit()

    messages = db.query(Message).filter(
        Message.conversation_id == convo.id
    ).order_by(Message.created_at.asc()).all()

    bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    business_name = bot_config.business_name if bot_config else "SupportBot"

    # ── Resolve final email + contact details ─────────────────────────────────
    effective_email = email or customer_email

    # Conversation has no visitor_id column — look it up via the join table.
    visitor_link = db.query(VisitorConversation).filter(
        VisitorConversation.conversation_id == convo.id,
    ).first()
    convo_visitor_id = visitor_link.visitor_id if visitor_link else None

    contact = _resolve_contact(
<<<<<<< HEAD
        db=db, bot_id=bot_id, convo=convo,
        visitor_id=convo_visitor_id,
=======
        db=db, bot_id=bot_id,
        visitor_id=convo_visitor_id,
        customer_email=convo.customer_email,
>>>>>>> 2c222c975f68bd1a257a9d3eae0f3433363f10cb
        name=name, email=effective_email, phone=phone,
    )
    normalised_reason = reason if reason in _VALID_REASONS else "customer_requested"

    transcript_lines = []
    for msg in messages:
        role = "Customer" if msg.role == "user" else "Bot"
        transcript_lines.append(f"{role}: {msg.content}")
    transcript = "\n".join(transcript_lines)

    # First user message — what kicked off the conversation. Used as the
    # ``message`` field in the webhook envelope so receivers see context.
    first_user_msg = next((m.content for m in messages if m.role == "user"), None)

    contact_block = (
        f"Name: {contact['name'] or '—'} | "
        f"Email: {contact['email'] or '—'} | "
        f"Phone: {contact['phone'] or '—'}"
    )
    summary = (
        f"SupportBot Escalation — {business_name}\n"
        f"{contact_block}\n"
        f"Reason: {normalised_reason}\n"
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
    # custom_https receivers get the structured envelope (bot_id at the top
    # level, contact/reason/message_count nested under ``data``). Slack and
    # Discord receivers still get only the human-readable summary — their
    # wire formats are fixed by those platforms, so the contact details get
    # inlined into the summary text instead.
    webhooks = db.query(WebhookConfig).filter(
        WebhookConfig.bot_id == bot_id,
        WebhookConfig.enabled == True,
        WebhookConfig.notify_on.in_(["escalation", "all"]),
    ).all()

    webhook_extra: dict[str, Any] = {
        "visitor_id": convo_visitor_id,
        "bot_name": business_name,
        "reason": normalised_reason,
        "message_count": len(messages),
        "contact": contact,
        "message": first_user_msg,
    }

    for wh in webhooks:
        try:
            if wh.platform == "slack":
                text = (
                    f"SupportBot Escalation\n"
                    f"{contact_block}\n"
                    f"Reason: {normalised_reason}\n"
                    f"Messages: {len(messages)}\n\n{transcript}"
                )
            elif wh.platform == "discord":
                text = (
                    f"**SupportBot Escalation**\n"
                    f"{contact_block}\n"
                    f"Reason: {normalised_reason}\n"
                    f"Messages: {len(messages)}\n\n{transcript}"
                )
            else:
                text = summary
            ok = await dispatch_webhook(
                wh.platform,
                wh.webhook_url,
                text,
                secret=wh.secret,
                events=wh.events,
                event="escalation_triggered",
                bot_id=bot_id,
                extra=webhook_extra,
            )
            results[f"webhook_{wh.platform}_{wh.id}"] = ok
        except Exception as e:
            _log_notification_error(db, bot_id, f"webhook_{wh.platform}", e)
            results[f"webhook_{wh.platform}_{wh.id}"] = False

    # ── If ALL channels failed, queue for retry and report failure ────────────
    # Uses an upsert (ON CONFLICT DO NOTHING) keyed on (bot_id, session_id)
    # so the retry scheduler never creates duplicate rows for the same
    # escalation. If the write itself fails, we MUST NOT report "queued" —
    # the escalation is permanently lost. Instead, raise 503 with a clear
    # message so the caller knows to retry.
    all_results = list(results.values())
    if all_results and not any(all_results):
        dialect = get_dialect(db)
        if dialect == "postgresql":
            stmt = pg_insert(PendingEscalation).values(
                bot_id=bot_id, session_id=session_id,
                customer_email=contact["email"],
                retry_after=datetime.utcnow() + timedelta(minutes=5),
            ).on_conflict_do_nothing(
                index_elements=["bot_id", "session_id"]
            )
        elif dialect == "sqlite":
            stmt = sqlite_insert(PendingEscalation).values(
                bot_id=bot_id, session_id=session_id,
                customer_email=contact["email"],
                retry_after=datetime.utcnow() + timedelta(minutes=5),
            ).on_conflict_do_nothing(
                index_elements=["bot_id", "session_id"]
            )
        try:
            db.execute(stmt)
            db.commit()
        except Exception as e:
            db.rollback()
            log.error(
                "escalation_queue_insert_failed",
                error=str(e), bot_id=bot_id, session_id=session_id,
            )
            _log_notification_error(db, bot_id, "pending_escalation_queue", e)
            raise HTTPException(
                status_code=503,
                detail="Escalation queue failed — please try again",
            )
        raise HTTPException(
            status_code=500,
            detail="All notification channels failed; queued for retry.",
        )

    convo.escalated = True
    # Store whatever email we resolved (request → prior Lead → existing column).
    # Keeping the column populated keeps the existing Conversation export +
    # Visitor history features lit up for escalated chats.
    if contact["email"]:
        convo.customer_email = contact["email"]
    db.commit()

    # ── Persist a Lead row so the unified Leads tab surfaces this escalation ──
    # Best-effort: a Lead-write failure must NOT mask a successful escalation
    # (the notifications already fired). Log and move on.
    try:
        escalation_lead = Lead(
            bot_id=bot_id,
            visitor_id=convo_visitor_id,
            name=contact["name"],
            email=contact["email"],
            phone=contact["phone"],
            interest=first_user_msg,
            source="escalation",
            buying_signal_score=0,
            conversation_id=convo.id,
            type="escalation",
            status="new",
        )
        db.add(escalation_lead)
        db.commit()
    except Exception as e:
        db.rollback()
        log.warning(
            "escalation.lead_persist_failed",
            bot_id=bot_id, session_id=session_id, error=str(e),
        )
        _log_notification_error(db, bot_id, "lead_persist", e)

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
    # Per-(bot_id, ip) second-line rate limit — see chat.public_chat.
    if not check_bot_id_rate_limit(data.bot_id, get_remote_address(request), max_per_minute=5):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this bot")

    tenant = db.query(Tenant).filter(
        Tenant.bot_id == data.bot_id,
        Tenant.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Bot not found")
    return await _do_escalate(
        data.session_id,
        data.customer_email,
        data.bot_id,
        db,
        visitor_id=data.visitor_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        reason=data.reason,
    )


# ── Authenticated endpoint (admin demo) ───────────────────────────────────────

@router.post("")
async def escalate(
    data: EscalateRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    return await _do_escalate(
        data.session_id,
        data.customer_email,
        tenant.bot_id,
        db,
        name=data.name,
        email=data.email,
        phone=data.phone,
        reason=data.reason,
    )
