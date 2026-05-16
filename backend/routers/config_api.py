import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional

from backend.database import get_db, BotConfig, Tenant
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter
from backend.services.telegram_notify import get_bot_username

router = APIRouter(prefix="/api/config", tags=["config"])


# Lightweight email regex — matches "<local>@<domain>.<tld>" with no whitespace.
# Deliberately not using pydantic.EmailStr because that pulls the
# `email-validator` package, which isn't a current dependency. KAY_SKILL.md
# forbids silent dep adds; if stricter validation is wanted later, add the
# package explicitly and switch this field to EmailStr.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BotConfigSchema(BaseModel):
    business_name: str
    agent_name: str
    brand_color: str
    welcome_message: str
    # Optional + format-validated. "" / None / missing all coerce to None so
    # an empty form input doesn't 422 the save.
    escalation_email: Optional[str] = None
    voice_enabled: bool = True

    @field_validator("escalation_email", mode="before")
    @classmethod
    def _validate_escalation_email(cls, v):
        if v is None or v == "":
            return None
        if not isinstance(v, str) or not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v
    # Optional so older clients that don't send the field don't wipe the
    # stored value on save. The widget falls back to its own default if
    # this is empty / null.
    greeting_message: Optional[str] = None
    # Per-tenant Telegram chat target. None = field not in payload (don't
    # touch DB). "" = explicit clear by the tenant. See database.py for
    # the @username-vs-numeric-id caveat.
    telegram_handle: Optional[str] = None
    # Per-tenant free-text instructions appended to the system prompt AFTER
    # all platform rules (see ai_chat.build_system_prompt's custom_block).
    # Same Optional / "" → None semantics as telegram_handle above so an empty
    # textarea clears the override on save. Validator caps length at 2000
    # chars — mirrors _sanitize_custom_instructions in ai_chat.py so we 422
    # at the boundary instead of silently truncating server-side. Whitespace
    # is stripped before the empty-check so "   " also collapses to NULL.
    custom_instructions: Optional[str] = None

    @field_validator("custom_instructions", mode="before")
    @classmethod
    def _validate_custom_instructions(cls, v):
        # None passes through unchanged so the PUT handler can use the
        # "None = field missing from payload, don't touch DB" pattern that
        # telegram_handle / greeting_message use — required for backward compat
        # with clients that don't know about this field yet. "" is preserved
        # (NOT collapsed to None here) so the PUT handler can distinguish
        # "explicit clear" from "field missing", and itself maps "" -> NULL.
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("custom_instructions must be a string")
        v = v.strip()
        if len(v) > 2000:
            raise ValueError("custom_instructions must be 2000 characters or fewer")
        return v


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
        # Distinguish None (not set) from "" (intentionally empty).
        "greeting_message": config.greeting_message if config and config.greeting_message is not None else "Hi! Need help? 👋",
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
    if data.custom_instructions is not None:
        # "" -> NULL (tenant cleared the textarea). Non-empty string is
        # stored as-is (already stripped + length-validated by the
        # field_validator above). None on the request body means the client
        # didn't send the field at all — don't touch the stored value.
        config.custom_instructions = data.custom_instructions or None
    config.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(config)
    return config


@router.get("/bot-username")
async def get_telegram_bot_username():
    """Return the Telegram bot username for the Connect button.

    The admin panel uses this to build the deep-link URL
    ``https://t.me/<username>?start=botid_<bot_id>``.
    """
    username = await get_bot_username()
    return {"username": username}
