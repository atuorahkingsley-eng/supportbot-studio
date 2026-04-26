import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./supportbot.db")
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Float,
    ForeignKey, Text, text, Date, UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from backend.config import settings

# Ensure data directory exists
os.makedirs("./data", exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Multi-tenant core ──────────────────────────────────────────────────────────

def generate_bot_id() -> str:
    import secrets, string
    chars = string.ascii_lowercase + string.digits
    return "bot_" + "".join(secrets.choice(chars) for _ in range(8))


def generate_api_key() -> str:
    import secrets
    return f"sk_live_{secrets.token_hex(24)}"


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    bot_id = Column(String, unique=True, nullable=False, index=True)

    owner_name = Column(String, nullable=False, default="")
    owner_email = Column(String, nullable=False, unique=True)
    company_name = Column(String, nullable=False, default="")

    password_hash = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False)

    plan = Column(String, default="basic")          # "basic" | "pro" | "enterprise"
    is_active = Column(Boolean, default=True)
    monthly_message_limit = Column(Integer, default=1000)
    messages_used_this_month = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class SuperAdmin(Base):
    __tablename__ = "super_admins"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True)
    bot_id = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False)

    total_messages = Column(Integer, default=0)
    ai_messages = Column(Integer, default=0)
    auto_reply_messages = Column(Integer, default=0)
    escalations = Column(Integer, default=0)
    leads_captured = Column(Integer, default=0)
    voice_messages = Column(Integer, default=0)
    estimated_api_cost = Column(Float, default=0.0)


# ── Original models (now with bot_id) ─────────────────────────────────────────

class BotConfig(Base):
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    business_name = Column(String, default="My Business")
    agent_name = Column(String, default="SupportBot")
    brand_color = Column(String, default="#6366F1")
    welcome_message = Column(String, default="Hi! How can I help you today?")
    escalation_email = Column(String, default="")
    voice_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FAQEntry(Base):
    __tablename__ = "faq_entries"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source = Column(String, default="manual")
    source_filename = Column(String, nullable=True)
    embedding_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    session_id = Column(String, unique=True, index=True, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    escalated = Column(Boolean, default=False)
    customer_email = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    message_count = Column(Integer, default=0)
    primary_language = Column(String, nullable=True)

    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    was_auto_reply = Column(Boolean, default=False)
    detected_language = Column(String, nullable=True)
    input_method = Column(String, default="text")
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    platform = Column(String, nullable=False)
    webhook_url = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    notify_on = Column(String, default="escalation")
    last_test_ok = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    frequency = Column(String, default="daily")
    send_via = Column(String, default="telegram")
    send_at_hour = Column(Integer, default=8)
    send_on_day = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)
    last_sent_at = Column(DateTime, nullable=True)


# ── Phase 1: Conversation Memory ──────────────────────────────────────────────

class Visitor(Base):
    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    visitor_id = Column(String, index=True, nullable=False)
    email = Column(String, nullable=True, index=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    visit_count = Column(Integer, default=1)
    name = Column(String, nullable=True)
    tags = Column(Text, default="[]")
    notes = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("bot_id", "visitor_id", name="uq_visitor_bot"),
    )


class VisitorConversation(Base):
    __tablename__ = "visitor_conversations"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    visitor_id = Column(String, nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)


# ── Phase 3: Proactive Sales Agent ────────────────────────────────────────────

class SalesConfig(Base):
    __tablename__ = "sales_configs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    enabled = Column(Boolean, default=True)
    greeting_delay_seconds = Column(Integer, default=30)
    greeting_message = Column(String, default="Looking for something? I can help you find the perfect plan!")
    discount_code = Column(String, nullable=True)
    discount_message = Column(String, nullable=True)
    demo_booking_url = Column(String, nullable=True)
    exit_intent_enabled = Column(Boolean, default=True)
    exit_intent_message = Column(String, default="Wait! Before you go — here's 10% off.")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, nullable=True, index=True, default="default")
    visitor_id = Column(String, nullable=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    interest = Column(String, nullable=True)
    source = Column(String, default="chat_capture")
    buying_signal_score = Column(Integer, default=1)
    conversation_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    followed_up = Column(Boolean, default=False)


# ── Auto-Healing ──────────────────────────────────────────────────────────────

class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True)
    bot_id = Column(String, nullable=True, index=True)     # null = system-wide

    # Error details
    error_type = Column(String, nullable=False)             # "api_error" | "db_error" | ...
    error_message = Column(String, nullable=False)
    traceback = Column(Text, nullable=True)
    endpoint = Column(String, nullable=True)
    request_data = Column(Text, nullable=True)              # sanitised request body

    # Healing
    auto_healed = Column(Boolean, default=False)
    heal_action = Column(String, nullable=True)
    heal_diagnosis = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=2)

    # Status: "new" | "healing" | "healed" | "failed" | "resolved_manually"
    status = Column(String, default="new")
    notified = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class PendingEscalation(Base):
    """Stores escalations that failed all notification channels — retried by scheduler."""
    __tablename__ = "pending_escalations"

    id = Column(Integer, primary_key=True)
    bot_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False)
    customer_email = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    retry_after = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_columns():
    """Safely add new columns to existing tables (idempotent)."""
    migrations = [
        # Phase 2 (differentiators)
        ("conversations", "primary_language TEXT"),
        ("messages", "detected_language TEXT"),
        ("messages", "input_method TEXT DEFAULT 'text'"),
        ("bot_config", "voice_enabled INTEGER DEFAULT 1"),
        # Phase MT: bot_id multi-tenant columns
        ("bot_config", "bot_id TEXT DEFAULT 'default'"),
        ("faq_entries", "bot_id TEXT DEFAULT 'default'"),
        ("conversations", "bot_id TEXT DEFAULT 'default'"),
        ("messages", "bot_id TEXT DEFAULT 'default'"),
        ("webhook_configs", "bot_id TEXT DEFAULT 'default'"),
        ("report_schedules", "bot_id TEXT DEFAULT 'default'"),
        ("visitors", "bot_id TEXT DEFAULT 'default'"),
        ("visitor_conversations", "bot_id TEXT DEFAULT 'default'"),
        ("sales_configs", "bot_id TEXT DEFAULT 'default'"),
        ("leads", "bot_id TEXT DEFAULT 'default'"),
    ]
    with engine.connect() as conn:
        for table, col_def in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_columns()

    # Seed defaults
    db = SessionLocal()
    try:
        # Create default tenant if none exists
        if not db.query(Tenant).first():
            from backend.services.auth import hash_password  # local import — avoids circular
            default_tenant = Tenant(
                bot_id="default",
                owner_name="Default Admin",
                owner_email="admin@localhost",
                company_name="My Business",
                password_hash=hash_password("admin123"),
                api_key=generate_api_key(),
                plan="pro",
                monthly_message_limit=999999,
                is_active=True,
            )
            db.add(default_tenant)
            db.commit()

        # Seed BotConfig for default tenant
        if not db.query(BotConfig).filter(BotConfig.bot_id == "default").first():
            db.add(BotConfig(bot_id="default"))
            db.commit()

        # Seed ReportSchedule for default tenant
        if not db.query(ReportSchedule).filter(ReportSchedule.bot_id == "default").first():
            db.add(ReportSchedule(bot_id="default"))
            db.commit()

        # Seed SalesConfig for default tenant
        if not db.query(SalesConfig).filter(SalesConfig.bot_id == "default").first():
            db.add(SalesConfig(bot_id="default"))
            db.commit()

    finally:
        db.close()
