import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import structlog

from backend.config import settings

log = structlog.get_logger(__name__)


async def send_escalation_email(
    to_email: str,
    bot_name: str,
    visitor_message: str,
    session_id: str,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
) -> bool:
    """Send escalation notification via Zoho SMTP.

    Args:
        to_email: Client's escalation email address.
        bot_name: Name of the bot that escalated.
        visitor_message: Message that triggered escalation.
        session_id: Conversation session ID.
        contact_name: Visitor name if captured.
        contact_email: Visitor email if captured.
        contact_phone: Visitor phone if captured.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not settings.zoho_smtp_user or not settings.zoho_smtp_password:
        log.error("escalation_email_skipped", reason="SMTP credentials not configured")
        return False

    contact_lines = []
    if contact_name:
        contact_lines.append(f"Name:  {contact_name}")
    if contact_email:
        contact_lines.append(f"Email: {contact_email}")
    if contact_phone:
        contact_lines.append(f"Phone: {contact_phone}")
    contact_block = "\n".join(contact_lines) if contact_lines else "No contact details provided"
    contact_html = "<br>".join(contact_lines) if contact_lines else "<em>No contact details provided</em>"

    body_text = f"""
New escalation from {bot_name}

VISITOR MESSAGE:
{visitor_message}

CONTACT DETAILS:
{contact_block}

Session ID: {session_id}

---
Sent by SupportBot Studio
    """.strip()

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:560px;margin:0 auto;">
  <div style="background:#0F6E56;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="color:#fff;margin:0;">New Escalation — {bot_name}</h2>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
    <p style="color:#666;font-size:13px;margin:0 0 16px;">A visitor needs human support.</p>
    <h3 style="margin:0 0 8px;color:#1a1a1a;">Visitor Message</h3>
    <p style="background:#f7f7f7;padding:12px;border-radius:6px;color:#333;">{visitor_message}</p>
    <h3 style="margin:16px 0 8px;color:#1a1a1a;">Contact Details</h3>
    <p style="color:#333;line-height:1.8;">{contact_html}</p>
    <hr style="border:none;border-top:1px solid #e0e0e0;margin:20px 0;">
    <p style="color:#999;font-size:12px;margin:0;">Session ID: {session_id}<br>Sent by SupportBot Studio</p>
  </div>
</body>
</html>
    """.strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New Escalation: {bot_name} needs your attention"
    msg["From"] = settings.zoho_smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.zoho_smtp_host,
            settings.zoho_smtp_port,
            context=context,
        ) as server:
            server.login(settings.zoho_smtp_user, settings.zoho_smtp_password)
            server.sendmail(settings.zoho_smtp_user, to_email, msg.as_string())
        log.info("escalation_email_sent", to=to_email, bot=bot_name, session=session_id)
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("escalation_email_auth_failed", user=settings.zoho_smtp_user)
        return False
    except smtplib.SMTPException as e:
        log.error("escalation_email_smtp_failed", error=str(e), to=to_email)
        return False
    except Exception as e:
        log.error("escalation_email_unexpected_error", error=str(e), to=to_email)
        return False
