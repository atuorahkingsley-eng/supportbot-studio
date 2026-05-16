import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, field_validator
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
    """Base config schema — no field validators. Used for reading existing data.

    Intentionally does NOT validate ``brand_color`` format because existing
    DB values may have been saved before validation existed. The write-only
    subclass ``BotConfigUpdateSchema`` adds validation + auto-fix.
    """
    business_name: str
    agent_name: str
    brand_color: Optional[str] = None
    welcome_message: Optional[str] = None
    escalation_email: Optional[str] = None
    voice_enabled: bool = False
    greeting_message: Optional[str] = None
    telegram_handle: Optional[str] = None
    custom_instructions: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BotConfigUpdateSchema(BotConfigSchema):
    """Schema for writing config — adds validation + auto-fix for brand_color."""

    @field_validator("brand_color", mode="before")
    @classmethod
    def validate_hex_color(cls, v: str | None) -> str | None:
        """Validate brand_color is a 6-digit hex color on write.

        Auto-fixes: if ``v`` is 6 hex digits without ``#``, prepends it.
        This heals existing DB values on next save.

        Args:
            v: Color value being written.

        Returns:
            Validated color with ``#`` prefix, or ``None``.

        Raises:
            ValueError: If not a valid hex color format.
        """
        if not v:
            return v
        s = v.strip()
        # 6 hex digits without # → auto-fix
        if re.match(r'^[0-9a-fA-F]{6}$', s):
            return f'#{s.upper()}'
        # Full format with #
        if re.match(r'^#[0-9a-fA-F]{6}$', s):
            return s.upper()
        raise ValueError("brand_color must be a 6-digit hex color e.g. #6366F1")

    @field_validator("escalation_email", mode="before")
    @classmethod
    def _validate_escalation_email(cls, v):
        if v is None or v == "":
            return None
        if not isinstance(v, str) or not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v

    @field_validator("custom_instructions", mode="before")
    @classmethod
    def _validate_custom_instructions(cls, v):
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
    data: BotConfigUpdateSchema,
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
async def get_telegram_bot_username(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Return the Telegram bot username for the Connect button.

    The admin panel uses this to build the deep-link URL
    ``https://t.me/<username>?start=botid_<bot_id>``.
    """
    username = await get_bot_username()
    return {"username": username}
