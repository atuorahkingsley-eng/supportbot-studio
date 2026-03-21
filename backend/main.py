import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db, SessionLocal
from backend.services.report_scheduler import start_scheduler, stop_scheduler
from backend.routers import (
    config_api, knowledge, chat, analytics, escalate, webhooks, reports,
    visitors, sales,
)
from backend.routers import auth_api, admin, health
from backend.middleware.error_handler import ErrorHandlerMiddleware


def _setup_super_admin():
    """On startup: create default super admin if none exists."""
    from backend.database import SuperAdmin
    from backend.services.auth import hash_password
    from backend.config import settings

    db = SessionLocal()
    try:
        if not db.query(SuperAdmin).first():
            admin_user = SuperAdmin(
                username=settings.super_admin_username,
                password_hash=hash_password(settings.super_admin_password),
            )
            db.add(admin_user)
            db.commit()
            print(f"Super admin created: {settings.super_admin_username}")
            if settings.super_admin_password == "changeme123":
                print("WARNING: Change the default super admin password in .env!")
    finally:
        db.close()


def _reset_monthly_counts():
    """APScheduler job: reset all tenants' message counts on 1st of month."""
    from backend.database import Tenant
    db = SessionLocal()
    try:
        db.query(Tenant).update({Tenant.messages_used_this_month: 0})
        db.commit()
        print("Monthly message counts reset for all tenants.")
    finally:
        db.close()


def _log_daily_usage():
    """APScheduler job: log daily usage stats per tenant."""
    from datetime import date
    from backend.database import Tenant, Message, Lead, UsageLog
    from sqlalchemy import func

    db = SessionLocal()
    today = date.today()
    try:
        for tenant in db.query(Tenant).filter(Tenant.is_active == True).all():
            bid = tenant.bot_id

            total = db.query(Message).filter(
                Message.bot_id == bid,
                func.date(Message.created_at) == today,
            ).count()

            auto = db.query(Message).filter(
                Message.bot_id == bid,
                Message.was_auto_reply == True,
                func.date(Message.created_at) == today,
            ).count()

            ai = total - auto
            voice = db.query(Message).filter(
                Message.bot_id == bid,
                Message.role == "user",
                Message.input_method == "voice",
                func.date(Message.created_at) == today,
            ).count()

            leads = db.query(Lead).filter(
                Lead.bot_id == bid,
                func.date(Lead.created_at) == today,
            ).count()

            existing = db.query(UsageLog).filter(
                UsageLog.bot_id == bid,
                UsageLog.date == today,
            ).first()

            if existing:
                existing.total_messages = total
                existing.ai_messages = ai
                existing.auto_reply_messages = auto
                existing.voice_messages = voice
                existing.leads_captured = leads
                existing.estimated_api_cost = round(ai * 0.003, 4)
            else:
                log = UsageLog(
                    bot_id=bid,
                    date=today,
                    total_messages=total,
                    ai_messages=ai,
                    auto_reply_messages=auto,
                    voice_messages=voice,
                    leads_captured=leads,
                    estimated_api_cost=round(ai * 0.003, 4),
                )
                db.add(log)

        db.commit()
    finally:
        db.close()


def _retry_pending_escalations():
    """APScheduler job: retry escalations that failed all notification channels."""
    import asyncio
    from datetime import datetime, timedelta
    from backend.database import PendingEscalation

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        pending = db.query(PendingEscalation).filter(
            PendingEscalation.retry_after <= now,
            PendingEscalation.retry_count < 3,
        ).all()

        for p in pending:
            try:
                from backend.routers.escalate import _do_escalate
                asyncio.run(_do_escalate(p.session_id, p.customer_email, p.bot_id, db))
                db.delete(p)
                db.commit()
            except Exception:
                p.retry_count += 1
                p.retry_after = now + timedelta(minutes=15)
                db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _setup_super_admin()
    start_scheduler()

    from backend.services.report_scheduler import scheduler
    from backend.config import settings

    # Monthly counter reset (1st of month at midnight UTC)
    scheduler.add_job(
        _reset_monthly_counts, "cron",
        day=1, hour=0, minute=0,
        id="monthly_reset", replace_existing=True,
    )
    # Daily usage logging
    scheduler.add_job(
        _log_daily_usage, "cron",
        hour=23, minute=55,
        id="daily_usage", replace_existing=True,
    )
    # Scheduled health check
    from backend.services.health_monitor import scheduled_health_check
    scheduler.add_job(
        scheduled_health_check, "interval",
        minutes=settings.health_check_interval_minutes,
        id="health_check", replace_existing=True,
    )
    # Retry pending escalations every 5 minutes
    scheduler.add_job(
        _retry_pending_escalations, "interval",
        minutes=5,
        id="retry_escalations", replace_existing=True,
    )

    yield
    stop_scheduler()


app = FastAPI(title="SupportBot Studio v2 (Multi-Tenant + Auto-Healing)", lifespan=lifespan)

# ── Middleware ─────────────────────────────────────────────────────────────────
# CORS first so headers are always set; ErrorHandler wraps underneath
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ErrorHandlerMiddleware)

# ── API routers ────────────────────────────────────────────────────────────────
app.include_router(auth_api.router)       # /api/auth
app.include_router(admin.router)          # /api/admin
app.include_router(health.router)         # /api/health
app.include_router(config_api.router)     # /api/config
app.include_router(knowledge.router)      # /api/knowledge
app.include_router(chat.router)           # /api/chat
app.include_router(analytics.router)      # /api/analytics
app.include_router(escalate.router)       # /api/escalate
app.include_router(webhooks.router)       # /api/webhooks
app.include_router(reports.router)        # /api/reports
app.include_router(visitors.router)       # /api/visitors
app.include_router(sales.router)          # /api/sales


# ── Serve widget.js ────────────────────────────────────────────────────────────

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

@app.get("/widget.js")
async def serve_widget():
    widget_path = os.path.join(_static_dir, "widget.js")
    if not os.path.exists(widget_path):
        return Response("// SupportBot widget not found", media_type="application/javascript")
    return FileResponse(
        widget_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Serve React frontend in production ────────────────────────────────────────

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API routes or widget.js
        if full_path.startswith("api/") or full_path == "widget.js":
            from fastapi import HTTPException as FE
            raise FE(status_code=404)
        index = os.path.join(frontend_dist, "index.html")
        return FileResponse(index)
