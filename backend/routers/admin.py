"""
Super Admin router — tenant CRUD, billing, system health.
All endpoints require super admin authentication.
"""
import os
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List

from backend.database import (
    get_db, Tenant, SuperAdmin, BotConfig, FAQEntry, Conversation,
    Message, Lead, UsageLog, ErrorLog, generate_bot_id, generate_api_key,
)
from backend.services.auth import hash_password, get_super_admin, validate_password_strength

router = APIRouter(prefix="/api/admin", tags=["admin"])

PLAN_PRICES = {"basic": 100, "pro": 200, "enterprise": 400}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tenant_detail(t: Tenant, db: Session) -> dict:
    faq_count = db.query(FAQEntry).filter(FAQEntry.bot_id == t.bot_id).count()
    convo_count = db.query(Conversation).filter(Conversation.bot_id == t.bot_id).count()
    lead_count = db.query(Lead).filter(Lead.bot_id == t.bot_id).count()
    config = db.query(BotConfig).filter(BotConfig.bot_id == t.bot_id).first()
    return {
        "bot_id": t.bot_id,
        "owner_name": t.owner_name,
        "company_name": t.company_name,
        "owner_email": t.owner_email,
        "plan": t.plan,
        "is_active": t.is_active,
        "messages_used_this_month": t.messages_used_this_month,
        "monthly_message_limit": t.monthly_message_limit,
        "faq_count": faq_count,
        "conversation_count": convo_count,
        "lead_count": lead_count,
        "telegram_handle": config.telegram_handle if config else None,
        "created_at": t.created_at,
        "last_login_at": t.last_login_at,
    }


# ── Tenant CRUD ────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    owner_name: str
    owner_email: str
    company_name: str
    password: str
    plan: str = "basic"


class TenantUpdate(BaseModel):
    plan: Optional[str] = None
    monthly_message_limit: Optional[int] = None
    is_active: Optional[bool] = None
    owner_name: Optional[str] = None
    company_name: Optional[str] = None
    # Per-tenant Telegram chat target — writes through to BotConfig.
    # Lives on BotConfig (not Tenant) so the chat path can read it
    # alongside the rest of the bot's config.
    telegram_handle: Optional[str] = None


@router.post("/tenants")
def create_tenant(
    data: TenantCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    if db.query(Tenant).filter(Tenant.owner_email == data.owner_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    limits = {"basic": 1000, "pro": 5000, "enterprise": 20000}

    # generate_bot_id() returns 8 chars × 36 alphabet — collision is
    # astronomically unlikely but unhandled it surfaces as a raw 500 from
    # SQLite IntegrityError. Pre-check and return 409 instead. Retry once
    # since regenerating is cheap.
    bot_id = generate_bot_id()
    if db.query(Tenant).filter(Tenant.bot_id == bot_id).first():
        bot_id = generate_bot_id()
        if db.query(Tenant).filter(Tenant.bot_id == bot_id).first():
            raise HTTPException(
                status_code=409,
                detail="bot_id collision — please retry the request",
            )

    api_key = generate_api_key()

    tenant = Tenant(
        bot_id=bot_id,
        owner_name=data.owner_name,
        owner_email=data.owner_email,
        company_name=data.company_name,
        password_hash=hash_password(data.password),
        api_key=api_key,
        plan=data.plan,
        monthly_message_limit=limits.get(data.plan, 1000),
        is_active=True,
    )
    db.add(tenant)

    # Seed BotConfig for new tenant
    db.add(BotConfig(
        bot_id=bot_id,
        business_name=data.company_name,
    ))
    db.commit()
    db.refresh(tenant)

    base_url = os.getenv("APP_URL", "https://your-app.onrender.com")
    embed_code = f'<script src="{base_url}/widget.js" data-bot-id="{bot_id}"></script>'

    return {
        "bot_id": bot_id,
        "api_key": api_key,
        "admin_url": f"{base_url}/admin",
        "embed_code": embed_code,
        "owner_email": tenant.owner_email,
        "company_name": tenant.company_name,
        "plan": tenant.plan,
    }


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [_tenant_detail(t, db) for t in tenants]


@router.get("/tenants/{bot_id}")
def get_tenant(
    bot_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    detail = _tenant_detail(tenant, db)
    base_url = os.getenv("APP_URL", "https://your-app.onrender.com")
    detail["embed_code"] = f'<script src="{base_url}/widget.js" data-bot-id="{bot_id}"></script>'
    detail["api_key_masked"] = tenant.api_key[:12] + "..." + tenant.api_key[-4:]
    return detail


@router.put("/tenants/{bot_id}")
def update_tenant(
    bot_id: str,
    data: TenantUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data.plan is not None:
        tenant.plan = data.plan
    if data.monthly_message_limit is not None:
        tenant.monthly_message_limit = data.monthly_message_limit
    if data.is_active is not None:
        tenant.is_active = data.is_active
    if data.owner_name is not None:
        tenant.owner_name = data.owner_name
    if data.company_name is not None:
        tenant.company_name = data.company_name

    # telegram_handle lives on BotConfig — write through here so the super
    # admin can manage it from the same form. Empty string clears the value
    # (tenant intentionally turning per-tenant Telegram off).
    if data.telegram_handle is not None:
        config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
        if not config:
            config = BotConfig(bot_id=bot_id)
            db.add(config)
        config.telegram_handle = data.telegram_handle or None  # "" -> NULL

    db.commit()
    return _tenant_detail(tenant, db)


@router.delete("/tenants/{bot_id}")
def deactivate_tenant(
    bot_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """Soft delete — sets is_active=False, preserves data."""
    tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.is_active = False
    db.commit()
    return {"ok": True, "bot_id": bot_id, "is_active": False}


@router.post("/tenants/{bot_id}/reset-password")
def reset_tenant_password(
    bot_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    new_password = body.get("new_password")
    if not new_password:
        raise HTTPException(status_code=400, detail="new_password required")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    # bcrypt silently truncates input past 72 bytes — two distinct long passwords
    # could hash identically. Reject at the boundary so the user picks a shorter one.
    if len(new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 bytes or fewer (bcrypt limit)")
    strength_error = validate_password_strength(new_password)
    if strength_error:
        raise HTTPException(status_code=400, detail=strength_error)
    tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.password_hash = hash_password(new_password)
    db.commit()
    return {"ok": True}


@router.post("/tenants/{bot_id}/reset-api-key")
def reset_api_key(
    bot_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    tenant = db.query(Tenant).filter(Tenant.bot_id == bot_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.api_key = generate_api_key()
    db.commit()
    return {"ok": True, "api_key": tenant.api_key}


# ── Super admin password change ────────────────────────────────────────────────

@router.put("/super/password")
def change_super_password(
    body: dict,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_super_admin),
):
    new_password = body.get("new_password")
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    # bcrypt silently truncates input past 72 bytes — see reset_tenant_password.
    if len(new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 bytes or fewer (bcrypt limit)")
    strength_error = validate_password_strength(new_password)
    if strength_error:
        raise HTTPException(status_code=400, detail=strength_error)
    admin = db.query(SuperAdmin).filter(
        SuperAdmin.username == payload["username"]
    ).first()
    if admin:
        admin.password_hash = hash_password(new_password)
        db.commit()
    return {"ok": True}


# ── Billing summary ────────────────────────────────────────────────────────────

@router.get("/billing")
def billing_summary(
    month: Optional[str] = None,  # "2026-03"
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    if month:
        try:
            year, mo = map(int, month.split("-"))
            period_start = date(year, mo, 1)
            next_month = mo % 12 + 1
            next_year = year + (1 if next_month == 1 else 0)
            period_end = date(next_year, next_month, 1)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid month format, use YYYY-MM")
    else:
        today = date.today()
        period_start = date(today.year, today.month, 1)
        period_end = today

    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    rows = []
    total_revenue = 0
    total_api_cost = 0

    for t in tenants:
        logs = db.query(UsageLog).filter(
            UsageLog.bot_id == t.bot_id,
            UsageLog.date >= period_start,
            UsageLog.date < period_end,
        ).all()

        total_msgs = sum(l.total_messages for l in logs)
        ai_msgs = sum(l.ai_messages for l in logs)
        auto_msgs = sum(l.auto_reply_messages for l in logs)
        api_cost = round(ai_msgs * 0.003, 2)
        plan_price = PLAN_PRICES.get(t.plan, 0)
        profit = round(plan_price - api_cost, 2)

        total_revenue += plan_price
        total_api_cost += api_cost

        rows.append({
            "bot_id": t.bot_id,
            "company_name": t.company_name,
            "plan": t.plan,
            "plan_price": plan_price,
            "total_messages": total_msgs,
            "ai_messages": ai_msgs,
            "auto_reply_messages": auto_msgs,
            "estimated_api_cost": api_cost,
            "profit": profit,
        })

    return {
        "month": month or str(period_start)[:7],
        "tenants": rows,
        "totals": {
            "revenue": total_revenue,
            "api_costs": round(total_api_cost, 2),
            "profit": round(total_revenue - total_api_cost, 2),
        },
    }


# ── Platform overview ──────────────────────────────────────────────────────────

@router.get("/overview")
def platform_overview(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    tenants = db.query(Tenant).all()
    active = [t for t in tenants if t.is_active]

    today_start = datetime.combine(date.today(), datetime.min.time())
    convos_today = db.query(Conversation).filter(
        Conversation.started_at >= today_start
    ).count()

    month_start = date.today().replace(day=1)
    total_msgs_month = db.query(Message).filter(
        Message.created_at >= datetime.combine(month_start, datetime.min.time())
    ).count()

    total_leads = db.query(Lead).count()

    avg_price = sum(PLAN_PRICES.get(t.plan, 0) for t in active) / len(active) if active else 0
    revenue_estimate = sum(PLAN_PRICES.get(t.plan, 0) for t in active)
    api_cost_estimate = round(total_msgs_month * 0.003, 2)

    return {
        "total_tenants": len(tenants),
        "active_tenants": len(active),
        "inactive_tenants": len(tenants) - len(active),
        "total_messages_this_month": total_msgs_month,
        "conversations_today": convos_today,
        "total_leads": total_leads,
        "revenue_estimate": revenue_estimate,
        "api_cost_estimate": api_cost_estimate,
    }


# ── System health ──────────────────────────────────────────────────────────────

@router.get("/system")
def system_health(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    import os
    from backend.config import settings

    db_path = settings.database_url.replace("sqlite:///", "")
    db_size_mb = 0
    if os.path.exists(db_path):
        db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2)

    tenants_count = db.query(Tenant).count()
    faq_count = db.query(FAQEntry).count()
    convo_count = db.query(Conversation).count()
    msg_count = db.query(Message).count()
    lead_count = db.query(Lead).count()

    env_status = {
        "ANTHROPIC_API_KEY": bool(settings.anthropic_api_key),
        "JWT_SECRET_KEY": settings.jwt_secret_key != "dev-insecure-key-change-this-in-production",
        "TELEGRAM_BOT_TOKEN": bool(settings.telegram_bot_token),
        "EMAILJS_SERVICE_ID": bool(settings.emailjs_service_id),
    }

    return {
        "db_size_mb": db_size_mb,
        "tenants": tenants_count,
        "total_faqs": faq_count,
        "total_conversations": convo_count,
        "total_messages": msg_count,
        "total_leads": lead_count,
        "env_status": env_status,
    }


# ── Reset monthly counters ────────────────────────────────────────────────────

@router.post("/reset-monthly-counters")
def reset_monthly_counters(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    db.query(Tenant).update({Tenant.messages_used_this_month: 0})
    db.commit()
    return {"ok": True, "message": "All monthly counters reset"}


# ── Self-healing dashboard endpoints (Phase 6) ────────────────────────────────

@router.get("/health")
async def full_health_check(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """Comprehensive health check — super admin only."""
    from backend.routers.health import health_check
    return await health_check(db)


@router.get("/errors")
def list_errors(
    status: Optional[str] = None,          # new|healing|healed|failed|resolved_manually
    error_type: Optional[str] = None,
    bot_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """List recent errors with optional filters."""
    q = db.query(ErrorLog).order_by(ErrorLog.created_at.desc())
    if status:
        q = q.filter(ErrorLog.status == status)
    if error_type:
        q = q.filter(ErrorLog.error_type == error_type)
    if bot_id:
        q = q.filter(ErrorLog.bot_id == bot_id)

    total = q.count()
    errors = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "errors": [
            {
                "id": e.id,
                "bot_id": e.bot_id,
                "error_type": e.error_type,
                "error_message": e.error_message[:200],
                "endpoint": e.endpoint,
                "status": e.status,
                "auto_healed": e.auto_healed,
                "heal_action": e.heal_action,
                "heal_diagnosis": e.heal_diagnosis,
                "retry_count": e.retry_count,
                "notified": e.notified,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
            }
            for e in errors
        ],
    }


@router.post("/errors/{error_id}/resolve")
def resolve_error(
    error_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """Mark an error as manually resolved."""
    error_log = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
    if not error_log:
        raise HTTPException(status_code=404, detail="Error not found")
    error_log.status = "resolved_manually"
    error_log.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": error_id, "status": "resolved_manually"}


@router.post("/errors/{error_id}/retry")
async def retry_error(
    error_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """Manually trigger an auto-heal retry for a specific error."""
    error_log = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
    if not error_log:
        raise HTTPException(status_code=404, detail="Error not found")

    # Reset for retry
    error_log.status = "new"
    error_log.retry_count = 0
    db.commit()

    from backend.services.auto_healer import attempt_heal
    healed = await attempt_heal(error_log, db)
    return {"ok": True, "healed": healed, "status": error_log.status, "heal_action": error_log.heal_action}


@router.get("/errors/stats")
def error_stats(
    db: Session = Depends(get_db),
    _: dict = Depends(get_super_admin),
):
    """Healing statistics for the last 24 hours."""
    since = datetime.utcnow() - timedelta(hours=24)
    errors = db.query(ErrorLog).filter(ErrorLog.created_at >= since).all()

    total = len(errors)
    healed = sum(1 for e in errors if e.auto_healed)
    failed = sum(1 for e in errors if e.status == "failed")
    manual = sum(1 for e in errors if e.status == "resolved_manually")

    heal_rate = round((healed / total * 100), 1) if total > 0 else 0.0

    # Average heal time
    heal_times = []
    for e in errors:
        if e.auto_healed and e.resolved_at and e.created_at:
            delta = (e.resolved_at - e.created_at).total_seconds()
            heal_times.append(delta)
    avg_heal_time = round(sum(heal_times) / len(heal_times), 1) if heal_times else 0.0

    # By error type
    by_type = {}
    for e in errors:
        et = e.error_type
        if et not in by_type:
            by_type[et] = {"total": 0, "healed": 0}
        by_type[et]["total"] += 1
        if e.auto_healed:
            by_type[et]["healed"] += 1

    return {
        "period_hours": 24,
        "total_24h": total,
        "auto_healed": healed,
        "failed": failed,
        "resolved_manually": manual,
        "heal_rate": heal_rate,
        "avg_heal_time_seconds": avg_heal_time,
        "by_type": by_type,
    }
