from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from backend.database import get_db, WebhookConfig, Tenant
from backend.services.webhook_sender import dispatch_webhook
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


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
    for field, value in data.model_dump(exclude_none=True).items():
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
