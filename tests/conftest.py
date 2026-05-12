"""Shared pytest fixtures for the SupportBot Studio v2 test suite.

Design constraints (mirrors the spec given to KAY):

* No real DB on disk — every test gets a fresh in-memory SQLite via StaticPool
  so writes in one connection are visible to all others (StaticPool gives the
  whole test exactly one connection to the in-memory DB).
* No real external services — Anthropic / Telegram / Twilio / HTTP webhooks
  are all mocked at the call sites that production hits.
* No environment dependence — we set ENV=dev + dummy secrets at the top of
  this module BEFORE importing anything from ``backend`` so the boot guard
  in ``backend/config.py`` doesn't ``sys.exit(1)`` on us.
* Rate-limiter disabled — the 5-per-15-minutes login limit and 20/min chat
  limit would falsely fail tests that loop requests. Production keeps it on.
"""

# ── Environment setup (must run before any backend import) ─────────────────────
# The boot guard at the bottom of backend/config.py will sys.exit(1) if ENV is
# not "dev" AND JWT_SECRET_KEY / SUPER_ADMIN_PASSWORD are at defaults. Setting
# these via os.environ.setdefault keeps a real .env from overriding them.
import os

os.environ.setdefault("ENV", "dev")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production-1234567890")
os.environ.setdefault("SUPER_ADMIN_USERNAME", "test_admin")
os.environ.setdefault("SUPER_ADMIN_PASSWORD", "test-admin-pw-1")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Quiet structlog so test output stays scannable. Any production code path that
# emits log.warning / log.error is still exercised — we just suppress the
# rendered line. We mirror this with caplog overrides in individual tests when
# we want to assert *that* a log was emitted.
import logging
import structlog

structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    cache_logger_on_first_use=False,
)
logging.getLogger().setLevel(logging.CRITICAL)


# ── Backend imports (now safe — env is set) ────────────────────────────────────
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.main as main_module
from backend.database import Base, BotConfig, SalesConfig, Tenant, get_db
from backend.services.auth import create_token, hash_password
from backend.services.rate_limit import limiter

# Disable rate-limiting across the whole test session. slowapi reads
# ``enabled`` on every check; flipping it once is the cheapest opt-out.
limiter.enabled = False


# ── Engine + session fixtures ──────────────────────────────────────────────────

@pytest.fixture
def test_engine():
    """Fresh in-memory SQLite engine per test.

    StaticPool keeps a SINGLE connection alive for the engine's lifetime —
    without it, every new Session would hit a fresh empty :memory: DB. With
    it, every connection sees the same data. ``check_same_thread=False`` is
    required because TestClient may dispatch handlers on a worker thread.
    """
    engine = create_engine(
        "sqlite://",  # = sqlite:///:memory:
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def TestSessionLocal(test_engine):
    """sessionmaker bound to the per-test engine.

    Returned as a factory so tests / fixtures that need their OWN session
    (separate from the request-handler's) can build one.
    """
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture
def test_db(TestSessionLocal) -> Generator[Session, None, None]:
    """A SQLAlchemy Session for direct fixture / assertion use.

    Distinct from the session FastAPI hands to the request handler via the
    ``get_db`` dependency override — both bind to the same engine, so writes
    from either are visible to the other after commit + expire_all.
    """
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


# ── App / TestClient fixture ───────────────────────────────────────────────────

@pytest.fixture
def test_client(test_engine, TestSessionLocal, monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient with the production app wired to the test engine.

    Three pieces of wiring:

    1. ``app.dependency_overrides[get_db]`` so every ``Depends(get_db)`` in
       every router yields a session bound to ``test_engine``.
    2. ``monkeypatch.setattr`` on ``backend.database.SessionLocal`` AND on
       ``backend.main.SessionLocal`` so production code that calls
       ``SessionLocal()`` directly (e.g. ``_log_daily_usage``,
       ``_summarize_and_update_visitor``) also points at the test engine.
       Because ``main.py`` did ``from backend.database import SessionLocal``,
       the symbol is rebound in two places — patch both.
    3. ``TestClient(app)`` is built WITHOUT a ``with`` block so the lifespan
       handler is skipped — we don't want ``init_db`` re-running, the
       APScheduler firing, or super-admin seeding kicking in mid-test.
    """
    def _override_get_db():
        s = TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    main_module.app.dependency_overrides[get_db] = _override_get_db

    # Point direct-SessionLocal callers at the test engine. monkeypatch
    # auto-reverts after the test, so production state is untouched.
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(main_module, "SessionLocal", TestSessionLocal)

    client = TestClient(main_module.app)
    try:
        yield client
    finally:
        main_module.app.dependency_overrides.clear()


# ── Tenant + bot config fixtures ──────────────────────────────────────────────

@pytest.fixture
def test_tenant(test_db):
    """Create one Tenant row, return a stub with bot_id / token / credentials.

    Returned as a SimpleNamespace (not the ORM object) because the ORM row
    is bound to ``test_db`` — if the test later commits via the request
    handler's session, the original ``tenant`` reference could go stale. The
    namespace carries plain values that stay valid for the whole test.
    """
    raw_password = "TestPass123"
    t = Tenant(
        bot_id="test_bot_001",
        owner_name="Test User",
        owner_email="owner@test.example",
        company_name="Test Co",
        password_hash=hash_password(raw_password),
        api_key="sk_test_abcdef",
        plan="pro",
        is_active=True,
        monthly_message_limit=10_000,
        messages_used_this_month=0,
    )
    test_db.add(t)
    test_db.commit()
    test_db.refresh(t)

    # Issue a real JWT via the production helper so we test the same encode
    # path the login endpoint uses — symmetry catches encode/decode drift.
    token = create_token({"role": "client", "bot_id": t.bot_id})

    return SimpleNamespace(
        id=t.id,
        bot_id=t.bot_id,
        owner_email=t.owner_email,
        raw_password=raw_password,
        company_name=t.company_name,
        token=token,
    )


@pytest.fixture
def test_bot_config(test_db, test_tenant):
    """Create a BotConfig row for the test tenant."""
    cfg = BotConfig(
        bot_id=test_tenant.bot_id,
        business_name="Test Business",
        agent_name="TestBot",
        brand_color="#000000",
        welcome_message="Hello!",
        escalation_email="ops@test.example",
    )
    test_db.add(cfg)
    test_db.commit()
    test_db.refresh(cfg)
    return cfg


@pytest.fixture
def auth_headers(test_tenant) -> dict:
    """Authorization: Bearer <jwt> — works for any endpoint that goes through
    ``get_current_client`` or ``get_super_admin`` (both accept Bearer fallback).
    """
    return {"Authorization": f"Bearer {test_tenant.token}"}


@pytest.fixture
def auth_cookies(test_tenant) -> dict:
    """Cookie payload for endpoints that only read cookies (notably /api/auth/me,
    which has its own Cookie-only auth path rather than going through the
    shared get_current_client dependency).
    """
    return {"sb_client_token": test_tenant.token}
