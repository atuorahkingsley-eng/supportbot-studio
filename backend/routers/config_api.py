from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, BotConfig, Tenant
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter

router = APIRouter(prefix="/api/config", tags=["config"])


class BotConfigSchema(BaseModel):
    business_name: str
    agent_name: str
    brand_color: str
    welcome_message: str
    escalation_email: str
    voice_enabled: bool = True
    # Optional so older clients that don't send the field don't wipe the
    # stored value on save. The widget falls back to its own default if
    # this is empty / null.
    greeting_message: Optional[str] = None
    # Per-tenant Telegram chat target. None = field not in payload (don't
    # touch DB). "" = explicit clear by the tenant. See database.py for
    # the @username-vs-numeric-id caveat.
    telegram_handle: Optional[str] = None


class BotConfigResponse(BotConfigSchema):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Public endpoint (no auth — for embed widget) ───────────────────────────────

@router.get("/public/{bot_id}")
@limiter.limit("20/minute")
def get_public_config(request: Request, bot_id: str, db: Session = Depends(get_db)):
    """Return safe public config for the embed widget. No authentication required."""
    tenant = db.query(Tenant).filter(
        Tenant.bot_id == bot_id,
        Tenant.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Bot not found")

    config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()

    return {
        "bot_id": bot_id,
        "business_name": config.business_name if config else tenant.company_name,
        "agent_name": config.agent_name if config else "SupportBot",
        "brand_color": config.brand_color if config else "#6366F1",
        "welcome_message": config.welcome_message if config else "Hi! How can I help?",
        "voice_enabled": config.voice_enabled if config else False,
        # Empty / missing → widget falls back to its own default.
        "greeting_message": (config.greeting_message if config else None) or "Hi! Need help? 👋",
    }


# ── Authenticated endpoints ────────────────────────────────────────────────────

@router.get("", response_model=BotConfigResponse)
def get_config(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    config = db.query(BotConfig).filter(BotConfig.bot_id == tenant.bot_id).first()
    if not config:
        config = BotConfig(bot_id=tenant.bot_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.put("", response_model=BotConfigResponse)
def update_config(
    data: BotConfigSchema,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    config = db.query(BotConfig).filter(BotConfig.bot_id == tenant.bot_id).first()
    if not config:
        config = BotConfig(bot_id=tenant.bot_id)
        db.add(config)

    config.business_name = data.business_name
    config.agent_name = data.agent_name
    config.brand_color = data.brand_color
    config.welcome_message = data.welcome_message
    config.escalation_email = data.escalation_email
    config.voice_enabled = data.voice_enabled
    # Only overwrite if the client actually sent a value — None means
    # the field wasn't in the payload at all.
    if data.greeting_message is not None:
        config.greeting_message = data.greeting_message
    if data.telegram_handle is not None:
        # "" -> NULL so empty form input clears the override cleanly.
        config.telegram_handle = data.telegram_handle or None
    config.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(config)
    return config
