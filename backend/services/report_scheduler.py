from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from backend.database import SessionLocal, ReportSchedule, Conversation, Message, BotConfig
from backend.services.telegram_notify import send_telegram_message
from backend.services.email_notify import send_emailjs

scheduler = AsyncIOScheduler()


def _build_report(db: Session) -> str:
    bot_config = db.query(BotConfig).first()
    business_name = bot_config.business_name if bot_config else "SupportBot"

    today = datetime.utcnow().date()
    since = datetime.combine(today, datetime.min.time())

    convos = db.query(Conversation).filter(Conversation.started_at >= since).all()
    msgs = db.query(Message).filter(Message.created_at >= since).all()

    total_convos = len(convos)
    total_msgs = len(msgs)
    escalations = sum(1 for c in convos if c.escalated)
    auto_replies = sum(1 for m in msgs if m.was_auto_reply and m.role == "assistant")
    assistant_msgs = sum(1 for m in msgs if m.role == "assistant")
    auto_pct = round(auto_replies / assistant_msgs * 100, 1) if assistant_msgs > 0 else 0
    savings = round(auto_replies * 0.003, 2)

    rated = [c for c in convos if c.rating]
    avg_rating = round(sum(c.rating for c in rated) / len(rated), 2) if rated else None

    # Top 5 questions
    from collections import Counter
    questions = Counter(m.content for m in msgs if m.role == "user")
    top5 = questions.most_common(5)

    resolved = sum(1 for c in convos if not c.escalated)
    resolution_rate = round(resolved / total_convos * 100, 1) if total_convos > 0 else 0

    top_q_text = ""
    for i, (q, cnt) in enumerate(top5, 1):
        short_q = q[:80] + "..." if len(q) > 80 else q
        top_q_text += f"{i}. {short_q} — {cnt}x\n"

    report = (
        f"📊 SupportBot Daily Report — {business_name}\n"
        f"Date: {today}\n\n"
        f"Conversations: {total_convos}\n"
        f"Messages: {total_msgs}\n"
        f"Auto-replies: {auto_replies} ({auto_pct}% — saved ${savings})\n"
        f"Escalations: {escalations}\n"
        f"Avg Rating: {avg_rating}/4\n\n"
        f"Top 5 Questions:\n{top_q_text}\n"
        f"Resolution Rate: {resolution_rate}%"
    )
    return report


async def send_report():
    db = SessionLocal()
    try:
        schedule = db.query(ReportSchedule).first()
        if not schedule or not schedule.enabled:
            return

        report = _build_report(db)

        if schedule.send_via in ("telegram", "both"):
            await send_telegram_message(report)

        if schedule.send_via in ("email", "both"):
            bot_config = db.query(BotConfig).first()
            to_email = bot_config.escalation_email if bot_config else ""
            await send_emailjs(
                subject=f"SupportBot Daily Report",
                message=report,
                to_email=to_email,
            )

        schedule.last_sent_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(send_report, "cron", hour=8, minute=0)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
