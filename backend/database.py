import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
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


class BotConfig(Base):
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, default="My Business")
    agent_name = Column(String, default="SupportBot")
    brand_color = Column(String, default="#6366F1")
    welcome_message = Column(String, default="Hi! How can I help you today?")
    escalation_email = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FAQEntry(Base):
    __tablename__ = "faq_entries"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source = Column(String, default="manual")  # "manual" | "uploaded_doc"
    source_filename = Column(String, nullable=True)
    embedding_text = Column(Text)  # question + answer combined
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    escalated = Column(Boolean, default=False)
    customer_email = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    message_count = Column(Integer, default=0)

    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    was_auto_reply = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)  # "slack" | "discord" | "whatsapp"
    webhook_url = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    notify_on = Column(String, default="escalation")  # "escalation" | "all" | "daily_summary"
    last_test_ok = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    frequency = Column(String, default="daily")  # "daily" | "weekly"
    send_via = Column(String, default="telegram")  # "telegram" | "email" | "both"
    send_at_hour = Column(Integer, default=8)  # 0-23 UTC
    send_on_day = Column(Integer, nullable=True)  # 0=Mon for weekly
    enabled = Column(Boolean, default=True)
    last_sent_at = Column(DateTime, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Seed default BotConfig if none exists
    db = SessionLocal()
    try:
        if not db.query(BotConfig).first():
            db.add(BotConfig())
            db.commit()
        if not db.query(ReportSchedule).first():
            db.add(ReportSchedule())
            db.commit()
    finally:
        db.close()
