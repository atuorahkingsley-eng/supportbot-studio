import re
import secrets
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


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    """Return a UI-safe representation of an HMAC secret — 28 bullets + last 4 chars.

    Constant width on purpose: receivers can't infer real secret length from
    a screenshot or DOM inspection. Returns None when no secret is set, so
    the frontend can distinguish "no secret" from "secret set but masked".
    """
    if not secret:
        return None
    return "\u2022" * 28 + secret[-4:]


def _serialize_webhook(wh: WebhookConfig, plaintext_secret: Optional[str] = None) -> dict:
    """Build a response payload for a WebhookConfig row.

    `plaintext_secret` is non-None ONLY on the create + regenerate responses
    that are explicitly allowed to surface the raw secret once. Every other
    code path passes through `_mask_secret` so the wire never carries
    credentials in cleartext after the initial reveal.
    """
    return {
        "id": wh.id,
        "platform": wh.platform,
        "webhook_url": wh.webhook_url,
        "enabled": wh.enabled,
        "notify_on": wh.notify_on,
        "events": wh.events,
        "secret": plaintext_secret if plaintext_secret is not None else _mask_secret(wh.secret),
        "secret_generated": bool(wh.secret),
        "last_test_ok": wh.last_test_ok,
        "created_at": wh.created_at,
    }


def _validate_webhook_url(platform: str, url: str, secret: Optional[str] = None) -> None:
    """Reject any webhook URL that doesn't target a known integration host (SSRF guard).

    `secret` is required for the generic `custom_https` platform — it's the
    HMAC key the receiver uses to verify message authenticity. Without one,
    we'd be letting tenants point us at arbitrary HTTPS endpoints with no
    way for the receiver to know the request really came from us.
    """
    if not url:
        return
    p = (platform or "").lower()
    if secret and p != "custom_https":
        raise HTTPException(status_code=400, detail="secret is only supported for custom_https webhooks")
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
    if p == "custom_https":
        # Generic developer-facing webhook: any HTTPS host is allowed, but
        # only if the tenant has set an HMAC signing secret. The receiver
        # uses it to verify the request body wasn't tampered with.
        if not secret:
            raise HTTPException(
                status_code=400,
                detail="custom_https webhooks require a non-empty 'secret' for HMAC signing",
            )
        return

    raise HTTPException(status_code=400, detail=f"Unsupported webhook platform: {platform}")


class WebhookCreate(BaseModel):
    platform: str
    webhook_url: str
    enabled: bool = True
    notify_on: str = "escalation"
    secret: Optional[str] = None
    events: Optional[str] = None  # JSON-encoded list, e.g. '["escalation","lead.captured"]'


class WebhookUpdate(BaseModel):
    platform: Optional[str] = None
    webhook_url: Optional[str] = None
    enabled: Optional[bool] = None
    notify_on: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[str] = None


class WebhookResponse(BaseModel):
    id: int
    platform: str
    webhook_url: str
    enabled: bool
    notify_on: str
    events: Optional[str] = None
    # `secret` is masked on list/get/update (28 bullets + last 4 chars) and
    # plaintext only on the create + regenerate responses that surface it
    # exactly once. `secret_generated` lets the UI render "Secret set" badges
    # without ever shipping the credential itself.
    secret: Optional[str] = None
    secret_generated: bool = False
    last_test_ok: Optional[bool] = None
    created_at: datetime


@router.get("", response_model=List[WebhookResponse])
def list_webhooks(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    rows = db.query(WebhookConfig).filter(WebhookConfig.bot_id == tenant.bot_id).all()
    return [_serialize_webhook(wh) for wh in rows]


@router.post("", response_model=WebhookResponse)
def create_webhook(
    data: WebhookCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    # Auto-generate an HMAC secret for custom_https when the caller didn't
    # supply one. token_hex(32) → 64 hex chars (256 bits) — same entropy
    # band as Slack/Discord signing keys. The plaintext is returned ONCE
    # in this response; subsequent GETs only ever expose the masked form.
    plaintext_to_return: Optional[str] = None
    secret_to_store = data.secret
    if data.platform == "custom_https" and not secret_to_store:
        secret_to_store = secrets.token_hex(32)
        plaintext_to_return = secret_to_store

    _validate_webhook_url(data.platform, data.webhook_url, secret_to_store)

    payload = data.model_dump()
    payload["secret"] = secret_to_store
    wh = WebhookConfig(bot_id=tenant.bot_id, **payload)
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return _serialize_webhook(wh, plaintext_secret=plaintext_to_return)


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
    # Re-validate whenever any field that affects validation changes —
    # including the secret, since clearing it on a custom_https webhook
    # would silently leave it in an unsigned state.
    if any(k in updates for k in ("webhook_url", "platform", "secret")):
        new_url = updates.get("webhook_url", wh.webhook_url)
        new_platform = updates.get("platform", wh.platform)
        new_secret = updates.get("secret", wh.secret)
        _validate_webhook_url(new_platform, new_url, new_secret)
    for field, value in updates.items():
        setattr(wh, field, value)
    db.commit()
    db.refresh(wh)
    return _serialize_webhook(wh)


@router.post("/{webhook_id}/regenerate-secret", response_model=WebhookResponse)
def regenerate_webhook_secret(
    webhook_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Rotate the HMAC secret for a custom_https webhook.

    The old secret is overwritten in place — any active integration relying
    on it breaks immediately. That's the point: rotation is for compromised
    or leaked secrets, so a hard cutover is the safe behaviour. The new
    secret is returned plaintext exactly once; subsequent GETs mask it.
    """
    wh = db.query(WebhookConfig).filter(
        WebhookConfig.id == webhook_id,
        WebhookConfig.bot_id == tenant.bot_id,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if wh.platform != "custom_https":
        raise HTTPException(
            status_code=400,
            detail="Only custom_https webhooks have rotatable secrets",
        )

    new_secret = secrets.token_hex(32)
    wh.secret = new_secret
    db.commit()
    db.refresh(wh)
    return _serialize_webhook(wh, plaintext_secret=new_secret)


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
    # Pass secret so the test request carries a real HMAC header — lets
    # tenants verify their receiver-side signature check end-to-end.
    # Deliberately not passing `event`: a manual test should always go
    # through, regardless of the webhook's subscription list.
    ok = await dispatch_webhook(
        wh.platform,
        wh.webhook_url,
        test_message,
        secret=wh.secret,
    )

    wh.last_test_ok = ok
    db.commit()
    return {"ok": ok}
