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
    visitors, sales, brand_voice, leads,
)
from backend.routers import auth_api, admin, health
from backend.middleware.error_handler import ErrorHandlerMiddleware
from backend.services.rate_limit import limiter, rate_limit_handler
from backend.config import settings
from slowapi.errors import RateLimitExceeded


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


def _log_daily_usage() -> None:
    """APScheduler job: log daily usage stats per tenant.

    Uses a dialect-aware UPSERT (Postgres ON CONFLICT, SQLite ON CONFLICT)
    keyed on the new ``uq_usagelog_bot_date`` constraint so two concurrent
    runs of this job — or a fresh insert racing with a retry — collapse
    into a single row instead of producing duplicates that corrupt the
    monthly billing roll-up.
    """
    from datetime import date
    from backend.database import Tenant, Message, Lead, UsageLog, get_dialect
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    dialect = get_dialect(db)
    if dialect == "postgresql":
        insert_fn = pg_insert
    elif dialect == "sqlite":
        insert_fn = sqlite_insert
    else:
        raise RuntimeError(f"Unsupported database dialect: {dialect}")

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

            values = dict(
                bot_id=bid,
                date=today,
                total_messages=total,
                ai_messages=ai,
                auto_reply_messages=auto,
                voice_messages=voice,
                leads_captured=leads,
                estimated_api_cost=round(ai * 0.003, 4),
            )

            # Build INSERT ... ON CONFLICT (bot_id, date) DO UPDATE.
            # Using the constraint name from the new migration makes the
            # intent explicit and survives column-order changes.
            stmt = insert_fn(UsageLog).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["bot_id", "date"],
                set_={
                    "total_messages": stmt.excluded.total_messages,
                    "ai_messages": stmt.excluded.ai_messages,
                    "auto_reply_messages": stmt.excluded.auto_reply_messages,
                    "voice_messages": stmt.excluded.voice_messages,
                    "leads_captured": stmt.excluded.leads_captured,
                    "estimated_api_cost": stmt.excluded.estimated_api_cost,
                },
            )
            db.execute(stmt)

        db.commit()
    finally:
        db.close()


async def _retry_pending_escalations():
    """APScheduler job: retry escalations that failed all notification channels.

    Native async — AsyncIOScheduler runs this directly on the main event loop
    (no asyncio.run, no thread hop). Each pending escalation gets its own DB
    session so a mid-transaction failure can't corrupt the next iteration.
    """
    from datetime import datetime, timedelta
    from backend.database import PendingEscalation
    from backend.routers.escalate import _do_escalate

    # Read the pending list with a short-lived session, then close.
    read_db = SessionLocal()
    try:
        now = datetime.utcnow()
        pending = read_db.query(PendingEscalation).filter(
            PendingEscalation.retry_after <= now,
            PendingEscalation.retry_count < 3,
        ).all()
        # Snapshot the fields we need before the session closes —
        # detached ORM objects can't be safely mutated downstream.
        items = [(p.id, p.session_id, p.customer_email, p.bot_id) for p in pending]
    finally:
        read_db.close()

    # Process each in its own session — failures stay isolated.
    from backend.routers.escalate import _log_notification_error

    for pid, session_id, customer_email, bot_id in items:
        db = SessionLocal()
        try:
            await _do_escalate(session_id, customer_email, bot_id, db)
            p = db.query(PendingEscalation).filter(PendingEscalation.id == pid).first()
            if p:
                db.delete(p)
                db.commit()
        except Exception as e:
            db.rollback()
            # Pre-fix this except: pass swallowed every retry failure — the
            # retry counter could climb to max silently and the row would
            # then sit forever. Log to ErrorLog so the operator can see it.
            _log_notification_error(db, bot_id, "pending_escalation_retry", e)
            p = db.query(PendingEscalation).filter(PendingEscalation.id == pid).first()
            if p:
                p.retry_count += 1
                p.retry_after = datetime.utcnow() + timedelta(minutes=15)
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

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# ── Middleware ─────────────────────────────────────────────────────────────────
# Tiered CORS: public widget endpoints accept any origin (no cookies);
# admin/auth endpoints lock to APP_URL with credentials. ErrorHandler wraps under.
APP_URL = settings.app_url


class TieredCORSMiddleware:
    """Path-aware CORS dispatcher.

    Public paths (called from arbitrary client websites embedding the widget)
    get permissive CORS without credentials. Everything else gets locked to
    APP_URL with credentials enabled for cookie-based auth.

    Two CORSMiddleware instances are required because browsers reject
    Access-Control-Allow-Origin: * when credentials are present.

    Args:
        app: The downstream ASGI application.
        app_url: Origin permitted for credentialed admin requests.
    """

    _PUBLIC_EXACT = frozenset({
        "/api/chat/public",
        "/api/chat/rate",
        "/api/escalate/public",
        "/api/sales/leads/capture/public",
    })
    _PUBLIC_PREFIXES = ("/api/config/public/",)

    def __init__(self, app, app_url: str) -> None:
        self._public = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
        self._admin = CORSMiddleware(
            app,
            allow_origins=[app_url],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @classmethod
    def _is_public(cls, path: str) -> bool:
        if path in cls._PUBLIC_EXACT:
            return True
        return any(path.startswith(p) for p in cls._PUBLIC_PREFIXES)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and self._is_public(scope.get("path", "")):
            await self._public(scope, receive, send)
        else:
            await self._admin(scope, receive, send)


app.add_middleware(TieredCORSMiddleware, app_url=APP_URL)
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
app.include_router(brand_voice.router)    # /api/brand-voice
app.include_router(leads.router)          # /api/leads


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
