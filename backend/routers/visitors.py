import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from backend.database import get_db, Visitor, VisitorConversation, Conversation, Message, Tenant
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/visitors", tags=["visitors"])


class VisitorResponse(BaseModel):
    visitor_id: str
    email: Optional[str]
    name: Optional[str]
    first_seen: datetime
    last_seen: datetime
    visit_count: int
    tags: List[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[VisitorResponse])
def list_visitors(
    has_email: Optional[bool] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    q = db.query(Visitor).filter(
        Visitor.bot_id == tenant.bot_id
    ).order_by(Visitor.last_seen.desc())
    if has_email is True:
        q = q.filter(Visitor.email.isnot(None))
    elif has_email is False:
        q = q.filter(Visitor.email.is_(None))
    if tag:
        q = q.filter(Visitor.tags.contains(tag))
    visitors = q.limit(limit).all()

    result = []
    for v in visitors:
        tags = []
        try:
            tags = json.loads(v.tags or "[]")
        except Exception:
            pass
        result.append(VisitorResponse(
            visitor_id=v.visitor_id,
            email=v.email,
            name=v.name,
            first_seen=v.first_seen,
            last_seen=v.last_seen,
            visit_count=v.visit_count,
            tags=tags,
            notes=v.notes,
        ))
    return result


@router.get("/{visitor_id}/history")
def get_visitor_history(
    visitor_id: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    visitor = db.query(Visitor).filter(
        Visitor.visitor_id == visitor_id,
        Visitor.bot_id == tenant.bot_id,
    ).first()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    # Tenant isolation: pin the link lookup to tenant.bot_id, otherwise a
    # visitor_id that happens to exist in another tenant's space leaks that
    # tenant's conversation links. Follow-up Conversation + Message reads
    # are also pinned defensively.
    links = db.query(VisitorConversation).filter(
        VisitorConversation.visitor_id == visitor_id,
        VisitorConversation.bot_id == tenant.bot_id,
    ).all()
    conv_ids = [lk.conversation_id for lk in links]

    convos = []
    for cid in conv_ids:
        c = db.query(Conversation).filter(
            Conversation.id == cid,
            Conversation.bot_id == tenant.bot_id,
        ).first()
        if c:
            msgs = db.query(Message).filter(
                Message.conversation_id == cid,
                Message.bot_id == tenant.bot_id,
            ).order_by(Message.created_at.asc()).all()
            convos.append({
                "id": c.id,
                "session_id": c.session_id,
                "started_at": c.started_at,
                "escalated": c.escalated,
                "rating": c.rating,
                "message_count": c.message_count,
                "messages": [{"role": m.role, "content": m.content} for m in msgs],
            })

    tags = []
    try:
        tags = json.loads(visitor.tags or "[]")
    except Exception:
        pass

    return {
        "visitor_id": visitor.visitor_id,
        "email": visitor.email,
        "name": visitor.name,
        "first_seen": visitor.first_seen,
        "last_seen": visitor.last_seen,
        "visit_count": visitor.visit_count,
        "tags": tags,
        "notes": visitor.notes,
        "conversations": convos,
    }
