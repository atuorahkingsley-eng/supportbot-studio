from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import Optional, List
from pydantic import BaseModel
import io

from backend.database import get_db, Conversation, Message, Visitor, Lead, Tenant
from backend.utils.csv_export import generate_conversations_csv
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    bid = tenant.bot_id

    total_convos = db.query(Conversation).filter(Conversation.bot_id == bid).count()
    total_messages = db.query(Message).filter(Message.bot_id == bid).count()
    escalations = db.query(Conversation).filter(
        Conversation.bot_id == bid, Conversation.escalated == True
    ).count()

    auto_reply_count = db.query(Message).filter(
        Message.bot_id == bid,
        Message.was_auto_reply == True,
        Message.role == "assistant",
    ).count()

    total_assistant_msgs = db.query(Message).filter(
        Message.bot_id == bid, Message.role == "assistant"
    ).count()
    auto_reply_rate = (auto_reply_count / total_assistant_msgs * 100) if total_assistant_msgs > 0 else 0

    rated = db.query(Conversation).filter(
        Conversation.bot_id == bid, Conversation.rating.isnot(None)
    ).all()
    avg_rating = sum(c.rating for c in rated) / len(rated) if rated else None

    resolved = db.query(Conversation).filter(
        Conversation.bot_id == bid,
        Conversation.escalated == False,
        Conversation.message_count > 0,
    ).count()
    resolution_rate = (resolved / total_convos * 100) if total_convos > 0 else 0

    estimated_savings = round(auto_reply_count * 0.003, 2)

    voice_msgs = db.query(Message).filter(
        Message.bot_id == bid,
        Message.role == "user",
        Message.input_method == "voice",
    ).count()
    voice_rate = round(voice_msgs / total_messages * 100, 1) if total_messages > 0 else 0

    total_visitors = db.query(Visitor).filter(Visitor.bot_id == bid).count()
    returning_visitors = db.query(Visitor).filter(
        Visitor.bot_id == bid, Visitor.visit_count > 1
    ).count()
    total_leads = db.query(Lead).filter(Lead.bot_id == bid).count()

    return {
        "total_conversations": total_convos,
        "total_messages": total_messages,
        "escalations": escalations,
        "auto_reply_count": auto_reply_count,
        "auto_reply_rate": round(auto_reply_rate, 1),
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "resolution_rate": round(resolution_rate, 1),
        "estimated_savings": estimated_savings,
        "voice_messages": voice_msgs,
        "voice_rate": voice_rate,
        "total_visitors": total_visitors,
        "returning_visitors": returning_visitors,
        "total_leads": total_leads,
        "messages_used_this_month": tenant.messages_used_this_month,
        "monthly_message_limit": tenant.monthly_message_limit,
        "plan": tenant.plan,
    }


@router.get("/conversations")
def get_conversations(
    page: int = 1,
    per_page: int = 20,
    escalated: Optional[bool] = None,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    query = db.query(Conversation).filter(Conversation.bot_id == tenant.bot_id)
    if escalated is not None:
        query = query.filter(Conversation.escalated == escalated)

    total = query.count()
    convos = query.order_by(Conversation.started_at.desc()) \
        .offset((page - 1) * per_page).limit(per_page).all()

    results = []
    for c in convos:
        results.append({
            "id": c.id,
            "session_id": c.session_id,
            "started_at": c.started_at,
            "ended_at": c.ended_at,
            "escalated": c.escalated,
            "customer_email": c.customer_email,
            "rating": c.rating,
            "message_count": c.message_count,
        })

    return {"total": total, "page": page, "per_page": per_page, "conversations": results}


@router.get("/top-questions")
def get_top_questions(
    limit: int = 10,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    rows = db.query(Message.content, func.count(Message.id).label("count")) \
        .filter(Message.bot_id == tenant.bot_id, Message.role == "user") \
        .group_by(Message.content) \
        .order_by(func.count(Message.id).desc()) \
        .limit(limit).all()
    return [{"question": r.content, "count": r.count} for r in rows]


@router.get("/hourly")
def get_hourly(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    # Pre-fix this loaded every user message into memory and binned by
    # hour in Python — fine on a fresh tenant, a memory bomb on one with
    # 100K+ messages. Push the GROUP BY into the DB so it returns at most
    # 24 rows. extract('hour', col) is portable: SQLAlchemy emits
    # EXTRACT(hour FROM col) on Postgres and CAST(STRFTIME('%H', col) AS
    # INTEGER) on SQLite — same INTEGER 0..23 result either way.
    hour_expr = extract("hour", Message.created_at)
    rows = db.query(
        hour_expr.label("hour"),
        func.count(Message.id).label("count"),
    ).filter(
        Message.bot_id == tenant.bot_id,
        Message.role == "user",
        Message.created_at.isnot(None),
    ).group_by(hour_expr).all()

    counts = {int(r.hour): r.count for r in rows if r.hour is not None}
    return [{"hour": h, "count": counts.get(h, 0)} for h in range(24)]


@router.get("/export")
def export_csv(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    # Two round trips, regardless of conversation count — instead of N+1 (one
    # query per conversation). The CSV format consumes a {convo_id: [msgs]}
    # dict, so we fetch every message for this tenant in a single ordered
    # query and bucket it in Python. ``generate_conversations_csv`` is
    # unchanged; output bytes are identical.
    convos = db.query(Conversation).filter(
        Conversation.bot_id == tenant.bot_id
    ).order_by(Conversation.started_at.desc()).all()

    messages_map: dict[int, list[Message]] = {c.id: [] for c in convos}
    if convos:
        all_messages = db.query(Message).filter(
            Message.conversation_id.in_(messages_map.keys()),
        ).order_by(Message.conversation_id, Message.created_at.asc()).all()
        for msg in all_messages:
            # Defensive: skip messages whose conversation isn't in the map.
            # Can only happen if a Message row's conversation_id points to a
            # convo from a different bot (data corruption) — silently drop
            # rather than crash the export.
            bucket = messages_map.get(msg.conversation_id)
            if bucket is not None:
                bucket.append(msg)

    csv_content = generate_conversations_csv(convos, messages_map)
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=conversations.csv"},
    )


@router.get("/languages")
def get_language_distribution(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    rows = db.query(
        Message.detected_language,
        func.count(Message.id).label("count"),
    ).filter(
        Message.bot_id == tenant.bot_id,
        Message.role == "user",
        Message.detected_language.isnot(None),
    ).group_by(Message.detected_language).order_by(func.count(Message.id).desc()).all()
    total = sum(r.count for r in rows)
    return [
        {
            "language": r.detected_language,
            "count": r.count,
            "pct": round(r.count / total * 100, 1) if total > 0 else 0,
        }
        for r in rows
    ]
