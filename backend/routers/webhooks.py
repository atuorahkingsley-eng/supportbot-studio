import re
from datetime import datetime
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from backend.database import get_db, WebhookConfig, Tenant
from backend.services.webhook_sender import dispatch_webhook
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


_WHATSAPP_RE = re.compile(r"^whatsapp:\+\d{6,20}$")


def _validate_webhook_url(platform: str, url: str) -> None:
    """Reject any webhook URL that doesn't target a known integration host (SSRF guard)."""
    if not url:
        return
    p = (platform or "").lower()
    # WhatsApp uses a phone-number format; the actual outbound host is hardcoded to api.twilio.com.
    if p == "whatsapp":
        if not _WHATSAPP_RE.match(url):
            raise HTTPException(status_code=400, detail="WhatsApp must be 'whatsapp:+<digits>'")
        return

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Webhook URL must use https")
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    if p == "slack":
        if not (host == "hooks.slack.com" or host.endswith(".slack.com")):
            raise HTTPException(status_code=400, detail="Slack webhooks must point to *.slack.com")
        return
    if p == "discord":
        if host not in ("discord.com", "discordapp.com") or not path.startswith("/api/webhooks/"):
            raise HTTPException(status_code=400, detail="Discord webhooks must be discord.com/api/webhooks/...")
        return
    if p == "twilio":
        if host != "api.twilio.com":
            raise HTTPException(status_code=400, detail="Twilio webhooks must point to api.twilio.com")
        return

    raise HTTPException(status_code=400, detail=f"Unsupported webhook platform: {platform}")


class WebhookCreate(BaseModel):
    platform: str
    webhook_url: str
    enabled: bool = True
    notify_on: str = "escalation"


class WebhookUpdate(BaseModel):
    platform: Optional[str] = None
    webhook_url: Optional[str] = None
    enabled: Optional[bool] = None
    notify_on: Optional[str] = None


class WebhookResponse(BaseModel):
    id: int
    platform: str
    webhook_url: str
    enabled: bool
    notify_on: str
    last_test_ok: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[WebhookResponse])
def list_webhooks(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    return db.query(WebhookConfig).filter(WebhookConfig.bot_id == tenant.bot_id).all()


@router.post("", response_model=WebhookResponse)
def create_webhook(
    data: WebhookCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    _validate_webhook_url(data.platform, data.webhook_url)
    wh = WebhookConfig(bot_id=tenant.bot_id, **data.model_dump())
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    wh = db.query(WebhookConfig).filter(
        WebhookConfig.id == webhook_id,
        WebhookConfig.bot_id == tenant.bot_id,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    updates = data.model_dump(exclude_none=True)
    if "webhook_url" in updates:
        _validate_webhook_url(updates.get("platform") or wh.platform, updates["webhook_url"])
    for field, value in updates.items():
        setattr(wh, field, value)
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    wh = db.query(WebhookConfig).filter(
        WebhookConfig.id == webhook_id,
        WebhookConfig.bot_id == tenant.bot_id,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(wh)
    db.commit()
    return {"ok": True}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    wh = db.query(WebhookConfig).filter(
        WebhookConfig.id == webhook_id,
        WebhookConfig.bot_id == tenant.bot_id,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_message = "✅ SupportBot test message — webhook is working!"
    ok = await dispatch_webhook(wh.platform, wh.webhook_url, test_message)

    wh.last_test_ok = ok
    db.commit()
    return {"ok": ok}
