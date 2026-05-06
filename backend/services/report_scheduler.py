from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR
from sqlalchemy.orm import Session

from backend.database import SessionLocal, ReportSchedule, Conversation, Message, BotConfig, ErrorLog
from backend.services.telegram_notify import send_telegram_message
from backend.services.email_notify import send_emailjs


# ── Scheduler configuration ───────────────────────────────────────────────────
# timezone="UTC"          — pin job timing across DST/host-tz changes.
# max_instances=1         — one job instance at a time; the next firing waits
#                            rather than piling up if the previous run is slow.
# misfire_grace_time=300  — a missed firing within 5 min still runs once.
# coalesce=True           — collapse a backlog of missed firings into a single
#                            run rather than executing each catch-up.
scheduler = AsyncIOScheduler(
    timezone="UTC",
    job_defaults={
        "max_instances": 1,
        "misfire_grace_time": 300,
        "coalesce": True,
    },
)


def _on_job_error(event) -> None:
    """APScheduler event listener — record job exceptions to ErrorLog.

    Pre-fix every scheduled-job failure was silent: APScheduler logs to its
    own logger which nobody reads. Now operators see them in /api/admin/errors
    alongside request-time errors. Listener must NEVER raise — a raise here
    would re-trigger the same ERROR event and loop.
    """
    db = SessionLocal()
    try:
        log = ErrorLog(
            error_type="scheduler_error",
            error_message=f"job={event.job_id} {type(event.exception).__name__}: {str(event.exception)[:500]}",
            traceback=(str(event.traceback)[:2000] if getattr(event, "traceback", None) else None),
            endpoint=f"scheduler:{event.job_id}",
            status="failed",
        )
        db.add(log)
        db.commit()
    except Exception:
        # Listener swallowing is intentional: bubbling would re-trigger
        # EVENT_JOB_ERROR and loop. ErrorLog write failure is best-effort.
        pass
    finally:
        db.close()


scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)


def _build_report(db: Session, bot_id: str) -> str:
    """Build the daily report text for a single tenant.

    All queries are scoped by bot_id — never read across tenants.
    """
    bot_config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
    business_name = bot_config.business_name if bot_config else "SupportBot"

    today = datetime.utcnow().date()
    since = datetime.combine(today, datetime.min.time())

    convos = db.query(Conversation).filter(
        Conversation.bot_id == bot_id,
        Conversation.started_at >= since,
    ).all()
    msgs = db.query(Message).filter(
        Message.bot_id == bot_id,
        Message.created_at >= since,
    ).all()

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
    """Send the daily report for every tenant with an enabled ReportSchedule.

    Iterates rather than picking the first row — pre-fix this was multi-tenant
    broken: every tenant got tenant-#1's report (or nothing). Each tenant is
    isolated; one tenant's send failure must not abort the others.
    """
    db = SessionLocal()
    try:
        schedules = db.query(ReportSchedule).filter(
            ReportSchedule.enabled == True,
        ).all()

        for schedule in schedules:
            bot_id = schedule.bot_id
            if not bot_id:
                continue
            try:
                report = _build_report(db, bot_id)

                if schedule.send_via in ("telegram", "both"):
                    await send_telegram_message(report)

                if schedule.send_via in ("email", "both"):
                    bot_config = db.query(BotConfig).filter(
                        BotConfig.bot_id == bot_id
                    ).first()
                    to_email = bot_config.escalation_email if bot_config else ""
                    if to_email:
                        await send_emailjs(
                            subject=f"SupportBot Daily Report",
                            message=report,
                            to_email=to_email,
                        )

                schedule.last_sent_at = datetime.utcnow()
                db.commit()
            except Exception:
                # Per-tenant isolation: one tenant's failure must not abort the
                # other tenants' reports. Roll back any partial state on this
                # tenant and continue the loop.
                db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(send_report, "cron", hour=8, minute=0)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
