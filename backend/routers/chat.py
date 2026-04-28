import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Any

from backend.database import (
    get_db, SessionLocal, Conversation, Message, FAQEntry, BotConfig,
    Visitor, VisitorConversation, SalesConfig, Tenant,
)
from backend.services.auto_reply import find_auto_reply
from backend.services.ai_chat import get_ai_reply, generate_visitor_summary, build_system_prompt
from backend.services.auth import get_current_client
from backend.services.safe_executor import safe_execute
from backend.services.rate_limit import limiter

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request/Response schemas ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """For the admin demo tab (authenticated)."""
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    message: str
    browser_language: Optional[str] = None
    input_method: Optional[str] = "text"


class PublicChatRequest(BaseModel):
    """For the embeddable widget (no auth, bot_id in body)."""
    bot_id: str
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    message: str
    browser_language: Optional[str] = "en"
    input_method: Optional[str] = "text"


class ChatResponse(BaseModel):
    reply: str
    was_auto_reply: bool
    session_id: str
    visitor_id: Optional[str] = None
    needs_escalation: bool = False
    is_returning: bool = False
    detected_language: Optional[str] = None
    sales_action: Optional[Any] = None


class RateRequest(BaseModel):
    """Body for /api/chat/rate. bot_id is required so we can pin the
    conversation lookup to the right tenant — preventing a stranger with a
    leaked session_id from triggering a Claude summary call on someone
    else's visitor record."""
    bot_id: str
    session_id: str
    rating: int


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_or_create_visitor(visitor_id: str, bot_id: str, db: Session) -> Visitor:
    visitor = db.query(Visitor).filter(
        Visitor.visitor_id == visitor_id,
        Visitor.bot_id == bot_id,
    ).first()
    if visitor:
        visitor.visit_count += 1
        visitor.last_seen = datetime.utcnow()
        db.commit()
    else:
        visitor = Visitor(visitor_id=visitor_id, bot_id=bot_id)
        db.add(visitor)
        db.commit()
        db.refresh(visitor)
    return visitor


def _get_visitor_context(visitor: Visitor) -> dict:
    tags = []
    try:
        tags = json.loads(visitor.tags or "[]")
    except Exception:
        pass
    return {
        "visit_count": visitor.visit_count,
        "first_seen": visitor.first_seen.strftime("%B %d, %Y") if visitor.first_seen else None,
        "email": visitor.email,
        "tags": tags,
        "notes": visitor.notes,
    }


def _build_sales_action(sales_meta: dict, sales_config) -> Optional[dict]:
    if not sales_meta:
        return None
    score = sales_meta.get("buying_signal", 0)
    action = sales_meta.get("action", "none")
    if score < 3 or action == "none":
        return None
    if action == "offer_discount" and getattr(sales_config, "discount_code", None):
        return {
            "type": "discount",
            "code": sales_config.discount_code,
            "message": sales_config.discount_message or f"Use code {sales_config.discount_code}!",
        }
    if action == "offer_demo" and getattr(sales_config, "demo_booking_url", None):
        return {
            "type": "demo",
            "booking_url": sales_config.demo_booking_url,
            "message": "Book a free demo with our team!",
        }
    if action == "capture_lead":
        return {"type": "capture_lead", "message": "Want a detailed comparison? Enter your email."}
    return None


async def _summarize_and_update_visitor(visitor_id: str, conversation_id: int):
    db = SessionLocal()
    try:
        msgs = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
        if not msgs:
            return
        convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        bot_id = convo.bot_id if convo else None
        msg_dicts = [{"role": m.role, "content": m.content} for m in msgs]
        result = await generate_visitor_summary(msg_dicts)
        visitor = db.query(Visitor).filter(
            Visitor.visitor_id == visitor_id,
            Visitor.bot_id == bot_id,
        ).first()
        if visitor:
            existing_tags = []
            try:
                existing_tags = json.loads(visitor.tags or "[]")
            except Exception:
                pass
            new_tags = list(set(existing_tags + result.get("tags", [])))
            visitor.tags = json.dumps(new_tags)
            if result.get("summary"):
                visitor.notes = result["summary"]
            db.commit()
    finally:
        db.close()


# ── Phase 7: Fallback chain for AI chat ───────────────────────────────────────

async def _get_ai_reply_with_fallback(
    message: str,
    messages: list,
    bot_config,
    faqs: list,
    visitor_context: Optional[dict],
    sales_config,
    bot_id: str,
    db: Session,
) -> dict:
    """
    Fallback chain:
      1. safe_execute(get_ai_reply) with retries
      2. Fuzzy auto-reply at lower threshold (0.45)
      3. Hardcoded fallback message
    """
    # 1. Try Claude API with retry
    try:
        result = await safe_execute(
            get_ai_reply,
            error_type="api_error",
            bot_id=bot_id,
            db=db,
            endpoint="/api/chat",
            # kwargs forwarded to get_ai_reply:
            messages=messages,
            bot_config=bot_config,
            faqs=faqs,
            visitor_context=visitor_context,
            sales_config=sales_config,
        )
        return result
    except Exception:
        pass  # All retries exhausted — fall through

    # 2. Fuzzy match with lower threshold (better than nothing)
    fuzzy_answer = find_auto_reply(message, faqs, threshold=0.45)
    if fuzzy_answer:
        return {
            "reply": (
                f"{fuzzy_answer}\n\n"
                "(I'm experiencing some technical difficulties right now, but I hope this helps! "
                "Please try again in a moment.)"
            ),
            "was_auto_reply": True,
            "detected_language": None,
            "sales_meta": None,
        }

    # 3. Final fallback — always works
    contact = ""
    if bot_config and getattr(bot_config, "escalation_email", None):
        contact = f" or contact us at {bot_config.escalation_email} for immediate help"
    return {
        "reply": (
            f"I'm sorry, I'm experiencing some technical difficulties right now. "
            f"Please try again in a few minutes{contact}."
        ),
        "was_auto_reply": True,
        "detected_language": None,
        "sales_meta": None,
    }


async def _process_chat(
    bot_id: str,
    session_id: str,
    message: str,
    visitor_id: Optional[str],
    browser_language: Optional[str],
    input_method: str,
    db: Session,
    background_tasks: BackgroundTasks,
) -> ChatResponse:
    """Core chat processing logic shared by both public and admin endpoints."""
    # Get or create conversation
    convo = db.query(Conversation).filter(Conversation.session_id == session_id).first()
    if not convo:
        convo = Conversation(session_id=session_id, bot_id=bot_id)
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # Phase 1: visitor memory
    visitor = None
    visitor_context = None
    is_returning = False
    if visitor_id:
        visitor = _get_or_create_visitor(visitor_id, bot_id, db)
        is_returning = visitor.visit_count > 1

        existing_link = db.query(VisitorConversation).filter(
            VisitorConversation.visitor_id == visitor_id,
            VisitorConversation.conversation_id == convo.id,
            VisitorConversation.bot_id == bot_id,
        ).first()
        if not existing_link:
            db.add(VisitorConversation(
                visitor_id=visitor_id,
                conversation_id=convo.id,
                bot_id=bot_id,
            ))
            db.commit()

        if is_returning:
            visitor_context = _get_visitor_context(visitor)

    # Load tenant-specific data
    faqs = db.query(FAQEntry).filter(FAQEntry.bot_id == bot_id).all()
    bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    sales_config = db.query(SalesConfig).filter(SalesConfig.bot_id == bot_id).first()

    # Smart routing: auto-reply first (free, instant, no external dependency)
    auto_reply = find_auto_reply(message, faqs)

    was_auto_reply = False
    needs_escalation = False
    detected_language = None
    sales_action = None

    if auto_reply:
        reply = auto_reply
        was_auto_reply = True
        detected_language = browser_language
    else:
        history = db.query(Message).filter(
            Message.conversation_id == convo.id
        ).order_by(Message.created_at.asc()).all()

        messages = [{"role": m.role, "content": m.content} for m in history]
        messages.append({"role": "user", "content": message})

        # Phase 7: use fallback chain instead of direct AI call
        ai_result = await _get_ai_reply_with_fallback(
            message=message,
            messages=messages,
            bot_config=bot_config,
            faqs=faqs,
            visitor_context=visitor_context,
            sales_config=sales_config,
            bot_id=bot_id,
            db=db,
        )

        reply = ai_result["reply"]
        detected_language = ai_result.get("detected_language") or browser_language

        # Handle was_auto_reply from fallback
        if ai_result.get("was_auto_reply"):
            was_auto_reply = True
        else:
            if "ESCALATE" in reply:
                needs_escalation = True
                reply = reply.replace("ESCALATE", "").strip()

            sales_meta = ai_result.get("sales_meta")
            if sales_meta:
                sales_action = _build_sales_action(sales_meta, sales_config)

    # Save messages with bot_id
    user_msg = Message(
        bot_id=bot_id,
        conversation_id=convo.id,
        role="user",
        content=message,
        was_auto_reply=False,
        detected_language=detected_language,
        input_method=input_method,
    )
    db.add(user_msg)

    assistant_msg = Message(
        bot_id=bot_id,
        conversation_id=convo.id,
        role="assistant",
        content=reply,
        was_auto_reply=was_auto_reply,
        detected_language=detected_language,
    )
    db.add(assistant_msg)

    if detected_language and not convo.primary_language:
        convo.primary_language = detected_language

    convo.message_count = (convo.message_count or 0) + 2
    db.commit()

    return ChatResponse(
        reply=reply,
        was_auto_reply=was_auto_reply,
        session_id=session_id,
        visitor_id=visitor_id,
        needs_escalation=needs_escalation,
        is_returning=is_returning,
        detected_language=detected_language,
        sales_action=sales_action,
    )


# ── Public endpoint (embed widget — no auth) ──────────────────────────────────

@router.post("/public", response_model=ChatResponse)
@limiter.limit("20/minute")
async def public_chat(
    request: Request,
    data: PublicChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Chat endpoint for the embeddable widget. No authentication required."""
    tenant = db.query(Tenant).filter(
        Tenant.bot_id == data.bot_id,
        Tenant.is_active == True,
    ).first()
    if not tenant:
        return ChatResponse(
            reply="This chatbot is not available.",
            was_auto_reply=True,
            session_id=data.session_id or str(uuid.uuid4()),
        )

    if tenant.messages_used_this_month >= tenant.monthly_message_limit:
        return ChatResponse(
            reply="This chatbot has reached its monthly message limit. Please contact the site administrator.",
            was_auto_reply=True,
            session_id=data.session_id or str(uuid.uuid4()),
        )

    session_id = data.session_id or str(uuid.uuid4())
    result = await _process_chat(
        bot_id=data.bot_id,
        session_id=session_id,
        message=data.message,
        visitor_id=data.visitor_id,
        browser_language=data.browser_language,
        input_method=data.input_method or "text",
        db=db,
        background_tasks=background_tasks,
    )

    # Increment usage counter (only for AI replies)
    if not result.was_auto_reply:
        tenant.messages_used_this_month += 1
        db.commit()

    return result


# ── Authenticated endpoint (admin demo) ───────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Chat endpoint for the admin demo tab. Requires authentication."""
    session_id = data.session_id or str(uuid.uuid4())
    return await _process_chat(
        bot_id=tenant.bot_id,
        session_id=session_id,
        message=data.message,
        visitor_id=data.visitor_id,
        browser_language=data.browser_language,
        input_method=data.input_method or "text",
        db=db,
        background_tasks=background_tasks,
    )


# ── Rate conversation (public — called by embed widget and admin demo) ─────────

@router.post("/rate")
@limiter.limit("10/minute")
async def rate_conversation(
    request: Request,
    data: RateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Public endpoint — no auth required, but the (session_id, bot_id) pair
    is verified before any write. Rate-limited because the success path
    queues a Claude summary call (paid API)."""
    if not 1 <= data.rating <= 4:
        raise HTTPException(status_code=400, detail="Rating must be 1-4")
    convo = db.query(Conversation).filter(
        Conversation.session_id == data.session_id,
        Conversation.bot_id == data.bot_id,
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    convo.rating = data.rating
    convo.ended_at = datetime.utcnow()
    db.commit()

    link = db.query(VisitorConversation).filter(
        VisitorConversation.conversation_id == convo.id,
        VisitorConversation.bot_id == data.bot_id,
    ).first()
    if link:
        background_tasks.add_task(_summarize_and_update_visitor, link.visitor_id, convo.id)

    return {"ok": True}
