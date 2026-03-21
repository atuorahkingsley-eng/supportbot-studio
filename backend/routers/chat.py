import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, Conversation, Message, FAQEntry, BotConfig
from backend.services.auto_reply import find_auto_reply
from backend.services.ai_chat import get_ai_reply

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    reply: str
    was_auto_reply: bool
    session_id: str
    needs_escalation: bool = False


@router.post("", response_model=ChatResponse)
async def chat(data: ChatRequest, db: Session = Depends(get_db)):
    session_id = data.session_id or str(uuid.uuid4())

    # Get or create conversation
    convo = db.query(Conversation).filter(Conversation.session_id == session_id).first()
    if not convo:
        convo = Conversation(session_id=session_id)
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # Load FAQs
    faqs = db.query(FAQEntry).all()

    # Try auto-reply first
    auto_reply = find_auto_reply(data.message, faqs)

    was_auto_reply = False
    needs_escalation = False

    if auto_reply:
        reply = auto_reply
        was_auto_reply = True
    else:
        # Get conversation history for context
        history = db.query(Message).filter(
            Message.conversation_id == convo.id
        ).order_by(Message.created_at.asc()).all()

        messages = [{"role": m.role, "content": m.content} for m in history]
        messages.append({"role": "user", "content": data.message})

        bot_config = db.query(BotConfig).first()
        reply = await get_ai_reply(messages, bot_config, faqs)

        if "ESCALATE" in reply:
            needs_escalation = True
            reply = reply.replace("ESCALATE", "").strip()

    # Save user message
    user_msg = Message(
        conversation_id=convo.id,
        role="user",
        content=data.message,
        was_auto_reply=False,
    )
    db.add(user_msg)

    # Save assistant reply
    assistant_msg = Message(
        conversation_id=convo.id,
        role="assistant",
        content=reply,
        was_auto_reply=was_auto_reply,
    )
    db.add(assistant_msg)

    # Update conversation message count
    convo.message_count = (convo.message_count or 0) + 2
    db.commit()

    return ChatResponse(
        reply=reply,
        was_auto_reply=was_auto_reply,
        session_id=session_id,
        needs_escalation=needs_escalation,
    )


@router.post("/rate")
def rate_conversation(
    session_id: str,
    rating: int,
    db: Session = Depends(get_db),
):
    if not 1 <= rating <= 4:
        raise HTTPException(status_code=400, detail="Rating must be 1-4")
    convo = db.query(Conversation).filter(Conversation.session_id == session_id).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    convo.rating = rating
    convo.ended_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
