from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List

import structlog

from backend.database import (
    get_db, SalesConfig, Lead, Tenant, WebhookConfig, ErrorLog, BotConfig,
)
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter, check_bot_id_rate_limit
from backend.services.webhook_sender import dispatch_webhook
from slowapi.util import get_remote_address

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/sales", tags=["sales"])


# ── Webhook fan-out ───────────────────────────────────────────────────────────

def _log_notification_error(db: Session, bot_id: str, channel: str, error: Exception):
    """Persist a failed webhook attempt to ErrorLog. Best-effort — must not raise.

    Mirrors the helper in backend/routers/escalate.py:32-45 — kept module-local
    rather than extracted to avoid a cross-router import for a 12-line helper.
    """
    try:
        error_log = ErrorLog(
            bot_id=bot_id,
            error_type="notification_error",
            error_message=f"{channel}: {str(error)[:200]}",
            endpoint="/api/sales",
            status="failed",
        )
        db.add(error_log)
        db.commit()
    except Exception:
        pass


async def _fire_lead_captured_webhooks(db: Session, bot_id: str, lead: Lead) -> None:
    """Dispatch a ``lead_captured`` event to every enabled webhook for this tenant.

    Fan-out pattern mirrors backend/routers/escalate.py:125-151 verbatim — each
    webhook gets an isolated try/except so one failure does not abort the others;
    per-webhook errors land in ErrorLog rather than bubbling to the request.

    Subscription gate: ``notify_on == "all"``. Custom-https webhooks created via
    the new UI are forced to notify_on='all', so they match. Legacy slack/discord
    webhooks with notify_on='all' will also receive these — they explicitly opted
    into "all messages" so this matches the contract.

    For custom_https receivers, the structured payload includes a ``contact``
    block (with explicit nulls when the visitor skipped the form), the bot
    business name, and the captured visitor message. Slack/Discord continue to
    get the human-readable summary text only — their payload shapes are fixed.

    Args:
        db: Active SQLAlchemy session for ErrorLog writes.
        bot_id: Tenant identifier; used to scope webhook lookup + payload.
        lead: The freshly-committed Lead row to broadcast.
    """
    webhooks = db.query(WebhookConfig).filter(
        WebhookConfig.bot_id == bot_id,
        WebhookConfig.enabled == True,
        WebhookConfig.notify_on == "all",
    ).all()
    if not webhooks:
        return

    bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    bot_name = bot_config.business_name if bot_config else None

    contact = {
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
    }
    text = (
        f"New lead captured\n"
        f"Name: {lead.name or '—'}\n"
        f"Email: {lead.email or '—'}\n"
        f"Phone: {lead.phone or '—'}\n"
        f"Interest: {lead.interest or ''}\n"
        f"Source: {lead.source}"
    )
    extra = {
        "visitor_id": lead.visitor_id,
        "bot_name": bot_name,
        "message": lead.interest,
        "contact": contact,
    }
    for wh in webhooks:
        try:
            await dispatch_webhook(
                wh.platform,
                wh.webhook_url,
                text,
                secret=wh.secret,
                events=wh.events,
                event="lead_captured",
                bot_id=bot_id,
                extra=extra,
            )
        except Exception as e:
            log.warning(
                "lead_captured.webhook_failed",
                bot_id=bot_id, webhook_id=wh.id, platform=wh.platform, error=str(e),
            )
            _log_notification_error(db, bot_id, f"webhook_{wh.platform}", e)


# ── SalesConfig ───────────────────────────────────────────────────────────────

class SalesConfigSchema(BaseModel):
    enabled: bool = True
    greeting_delay_seconds: int = 30
    greeting_message: str = "Looking for something? I can help you find the perfect plan!"
    discount_code: Optional[str] = None
    discount_message: Optional[str] = None
    demo_booking_url: Optional[str] = None
    exit_intent_enabled: bool = True
    exit_intent_message: str = "Wait! Before you go — here's 10% off."


class SalesConfigResponse(SalesConfigSchema):
    id: int

    class Config:
        from_attributes = True


@router.get("/config", response_model=SalesConfigResponse)
def get_sales_config(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    cfg = db.query(SalesConfig).filter(SalesConfig.bot_id == tenant.bot_id).first()
    if not cfg:
        cfg = SalesConfig(bot_id=tenant.bot_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.put("/config", response_model=SalesConfigResponse)
def update_sales_config(
    data: SalesConfigSchema,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    cfg = db.query(SalesConfig).filter(SalesConfig.bot_id == tenant.bot_id).first()
    if not cfg:
        cfg = SalesConfig(bot_id=tenant.bot_id)
        db.add(cfg)
    for field, value in data.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return cfg


# ── Leads ─────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    """Inline lead-capture form payload — every contact field is optional.

    A Skipped form is still a meaningful signal (the buying-intent score
    fired) so we record the row with null contact details rather than
    rejecting the request.
    """
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    interest: Optional[str] = None
    source: str = "chat_capture"
    buying_signal_score: int = 1
    visitor_id: Optional[str] = None
    conversation_id: Optional[int] = None


class PublicLeadCreate(LeadCreate):
    bot_id: str


class LeadResponse(BaseModel):
    id: int
    email: Optional[str]
    name: Optional[str]
    phone: Optional[str]
    interest: Optional[str]
    source: str
    buying_signal_score: int
    visitor_id: Optional[str]
    conversation_id: Optional[int]
    created_at: datetime
    followed_up: bool
    type: str
    status: str

    class Config:
        from_attributes = True


@router.get("/leads", response_model=List[LeadResponse])
def list_leads(
    source: Optional[str] = None,
    followed_up: Optional[bool] = None,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    q = db.query(Lead).filter(Lead.bot_id == tenant.bot_id).order_by(Lead.created_at.desc())
    if source:
        q = q.filter(Lead.source == source)
    if followed_up is not None:
        q = q.filter(Lead.followed_up == followed_up)
    return q.limit(200).all()


@router.post("/leads/capture", response_model=LeadResponse)
async def capture_lead(
    data: LeadCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    lead = Lead(bot_id=tenant.bot_id, **data.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    # Fire lead_captured webhooks AFTER commit — pattern from escalate.py:140-147.
    # Awaited inline to match the existing fan-out style; per-webhook failures
    # are isolated and logged, so a slow receiver delays the response but a
    # broken one does not break it.
    await _fire_lead_captured_webhooks(db, tenant.bot_id, lead)
    return lead


# Public lead capture (for embed widget)
@router.post("/leads/capture/public", response_model=LeadResponse)
@limiter.limit("20/minute")
async def capture_lead_public(
    request: Request,
    data: PublicLeadCreate,
    db: Session = Depends(get_db),
):
    # Per-(bot_id, ip) second-line rate limit — see chat.public_chat.
    if not check_bot_id_rate_limit(data.bot_id, get_remote_address(request), max_per_minute=20):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this bot")

    from backend.database import Tenant as TenantModel
    tenant = db.query(TenantModel).filter(
        TenantModel.bot_id == data.bot_id,
        TenantModel.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Bot not found")
    lead_data = data.model_dump()
    lead_data.pop("bot_id")
    lead = Lead(bot_id=data.bot_id, **lead_data)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    # Same fan-out as the authenticated endpoint — see capture_lead above.
    await _fire_lead_captured_webhooks(db, data.bot_id, lead)
    return lead


@router.put("/leads/{lead_id}/follow-up")
def mark_followed_up(
    lead_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.bot_id == tenant.bot_id,
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.followed_up = True
    db.commit()
    return {"ok": True}


@router.get("/leads/stats")
def lead_stats(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    bid = tenant.bot_id
    total = db.query(Lead).filter(Lead.bot_id == bid).count()
    this_week = db.query(Lead).filter(Lead.bot_id == bid, Lead.created_at >= week_ago).count()
    this_month = db.query(Lead).filter(Lead.bot_id == bid, Lead.created_at >= month_ago).count()
    pending = db.query(Lead).filter(Lead.bot_id == bid, Lead.followed_up == False).count()

    by_source = db.query(Lead.source, func.count(Lead.id)).filter(
        Lead.bot_id == bid
    ).group_by(Lead.source).all()

    return {
        "total": total,
        "this_week": this_week,
        "this_month": this_month,
        "pending_follow_up": pending,
        "by_source": {src: cnt for src, cnt in by_source},
    }
