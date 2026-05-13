import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import structlog

from backend.config import settings

log = structlog.get_logger(__name__)

_smtp_port: int | None = None
_smtp_use_ssl: bool = True


def _probe_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check TCP reachability of host:port.

    Args:
        host: SMTP server hostname.
        port: Port number to probe.
        timeout: Connection timeout in seconds.

    Returns:
        True if connection succeeds within timeout, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def configure_smtp_at_startup() -> None:
    """Probe preferred SMTP port at startup.

    Falls back to alternate port if preferred is unreachable.
    Sets module-level ``_smtp_port`` and ``_smtp_use_ssl``.
    Idempotent — safe to call multiple times.
    No-ops if credentials are missing.

    If both ports fail, leaves globals at ``None`` so
    ``send_escalation_email`` falls back to
    ``settings.zoho_smtp_port`` (no behavioural regression
    on transient probe failures).

    Probe runs once at boot only. Re-probe requires redeploy.
    """
    global _smtp_port, _smtp_use_ssl

    if not settings.zoho_smtp_user or not settings.zoho_smtp_password:
        log.info("smtp.probe_skipped", reason="credentials_missing")
        return

    host = settings.zoho_smtp_host
    preferred = settings.zoho_smtp_port
    other = 465 if preferred == 587 else 587

    if _probe_port(host, preferred):
        _smtp_port = preferred
        _smtp_use_ssl = preferred == 465
        log.info("smtp.probe_ok", port=preferred)
        return

    if _probe_port(host, other):
        _smtp_port = other
        _smtp_use_ssl = other == 465
        log.warning("smtp.probe_fellback_to", preferred=preferred, using=other)
        return

    _smtp_port = None
    log.error("smtp.probe_failed", host=host, tried=[preferred, other])


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
        port = _smtp_port if _smtp_port is not None else settings.zoho_smtp_port
        use_ssl = _smtp_use_ssl if _smtp_port is not None else True

        if use_ssl:
            with smtplib.SMTP_SSL(
                settings.zoho_smtp_host,
                port,
                context=context,
            ) as server:
                server.login(settings.zoho_smtp_user, settings.zoho_smtp_password)
                server.sendmail(settings.zoho_smtp_user, to_email, msg.as_string())
        else:
            with smtplib.SMTP(settings.zoho_smtp_host, port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
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
