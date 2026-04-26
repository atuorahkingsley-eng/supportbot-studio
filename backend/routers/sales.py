from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List

from backend.database import get_db, SalesConfig, Lead, Tenant
from backend.services.auth import get_current_client
from backend.services.rate_limit import limiter

router = APIRouter(prefix="/api/sales", tags=["sales"])


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
    email: str
    name: Optional[str] = None
    interest: Optional[str] = None
    source: str = "chat_capture"
    buying_signal_score: int = 1
    visitor_id: Optional[str] = None
    conversation_id: Optional[int] = None


class PublicLeadCreate(LeadCreate):
    bot_id: str


class LeadResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    interest: Optional[str]
    source: str
    buying_signal_score: int
    visitor_id: Optional[str]
    conversation_id: Optional[int]
    created_at: datetime
    followed_up: bool

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
def capture_lead(
    data: LeadCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    lead = Lead(bot_id=tenant.bot_id, **data.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


# Public lead capture (for embed widget)
@router.post("/leads/capture/public", response_model=LeadResponse)
@limiter.limit("20/minute")
def capture_lead_public(
    request: Request,
    data: PublicLeadCreate,
    db: Session = Depends(get_db),
):
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
