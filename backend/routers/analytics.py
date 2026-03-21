from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from pydantic import BaseModel
import io

from backend.database import get_db, Conversation, Message
from backend.utils.csv_export import generate_conversations_csv

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    total_convos = db.query(Conversation).count()
    total_messages = db.query(Message).count()
    escalations = db.query(Conversation).filter(Conversation.escalated == True).count()

    auto_reply_count = db.query(Message).filter(
        Message.was_auto_reply == True,
        Message.role == "assistant"
    ).count()

    total_assistant_msgs = db.query(Message).filter(Message.role == "assistant").count()
    auto_reply_rate = (auto_reply_count / total_assistant_msgs * 100) if total_assistant_msgs > 0 else 0

    rated = db.query(Conversation).filter(Conversation.rating.isnot(None)).all()
    avg_rating = sum(c.rating for c in rated) / len(rated) if rated else None

    resolved = db.query(Conversation).filter(
        Conversation.escalated == False,
        Conversation.message_count > 0
    ).count()
    resolution_rate = (resolved / total_convos * 100) if total_convos > 0 else 0

    # Estimate savings: $0.003 per auto-reply message saved
    estimated_savings = round(auto_reply_count * 0.003, 2)

    return {
        "total_conversations": total_convos,
        "total_messages": total_messages,
        "escalations": escalations,
        "auto_reply_count": auto_reply_count,
        "auto_reply_rate": round(auto_reply_rate, 1),
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "resolution_rate": round(resolution_rate, 1),
        "estimated_savings": estimated_savings,
    }


@router.get("/conversations")
def get_conversations(
    page: int = 1,
    per_page: int = 20,
    escalated: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Conversation)
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
def get_top_questions(limit: int = 10, db: Session = Depends(get_db)):
    rows = db.query(Message.content, func.count(Message.id).label("count")) \
        .filter(Message.role == "user") \
        .group_by(Message.content) \
        .order_by(func.count(Message.id).desc()) \
        .limit(limit).all()

    return [{"question": r.content, "count": r.count} for r in rows]


@router.get("/hourly")
def get_hourly(db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.role == "user").all()
    hourly = [0] * 24
    for msg in msgs:
        if msg.created_at:
            hourly[msg.created_at.hour] += 1
    return [{"hour": h, "count": hourly[h]} for h in range(24)]


@router.get("/export")
def export_csv(db: Session = Depends(get_db)):
    convos = db.query(Conversation).order_by(Conversation.started_at.desc()).all()
    messages_map = {}
    for convo in convos:
        messages_map[convo.id] = db.query(Message) \
            .filter(Message.conversation_id == convo.id) \
            .order_by(Message.created_at.asc()).all()

    csv_content = generate_conversations_csv(convos, messages_map)

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=conversations.csv"},
    )
