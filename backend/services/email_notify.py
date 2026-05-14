"""Escalation email delivery via Resend HTTPS API.

Pre-migration this routed through Zoho SMTP, but Render's free instance type
firewalls outbound SMTP ports (25/465/587) at the network level, so escalation
emails silently failed to send. Resend speaks HTTPS on port 443 — firewalled
nowhere — so this code is portable across hosts (Render free/paid, Vercel,
Cloudflare Workers, etc.).

The Zoho mailbox is still used as the inbox; replies to escalation emails
flow back through the custom-domain MX, which still points to Zoho. Only the
outbound transactional path moved.

Callers in ``backend.routers.escalate`` and ``backend.services.report_scheduler``
import ``send_escalation_email`` and are unchanged — the function signature
and return contract are preserved.
"""
from typing import Optional, Tuple

import httpx
import structlog

from backend.config import settings

log = structlog.get_logger(__name__)


# Resend transactional-email endpoint. Single POST per send, JSON in/out,
# Bearer-token auth. Documented at https://resend.com/docs/api-reference/emails/send-email.
_RESEND_API_URL = "https://api.resend.com/emails"

# Conservative client-side timeout. Resend's median latency is sub-second;
# 10s gives generous headroom for cold TLS handshakes on Render's edge.
_HTTP_TIMEOUT_SECONDS = 10.0


def _render_bodies(
    bot_name: str,
    visitor_message: str,
    session_id: str,
    contact_name: Optional[str],
    contact_email: Optional[str],
    contact_phone: Optional[str],
) -> Tuple[str, str]:
    """Build the plain-text and HTML email bodies.

    Pure formatter — no network, no settings access — so the body shape can
    be unit-tested independently of the transport layer.

    Args:
        bot_name: Name of the bot that escalated. Goes in subject + body header.
        visitor_message: First user message that triggered the escalation.
        session_id: Conversation session ID, surfaced for support-team triage.
        contact_name: Visitor name if captured.
        contact_email: Visitor email if captured.
        contact_phone: Visitor phone if captured.

    Returns:
        Tuple of (plain-text body, HTML body) ready to drop into the Resend
        payload. Both render the same information; recipients see whichever
        their mail client prefers.
    """
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

    return body_text, body_html


async def send_escalation_email(
    to_email: str,
    bot_name: str,
    visitor_message: str,
    session_id: str,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
) -> bool:
    """Send an escalation notification via Resend.

    Returns True on a 200/202 response from Resend, False on missing config,
    non-2xx, network error, or unexpected exception. Failure modes are logged
    with enough detail to debug from log output alone — no exceptions leak
    out, so callers can safely treat this as a best-effort fire-and-forget.

    Args:
        to_email: The recipient's email address — typically the tenant's
            configured escalation contact.
        bot_name: Name of the bot that escalated. Used in subject + body.
        visitor_message: First user message that triggered the escalation.
        session_id: Conversation session ID, surfaced for support-team triage.
        contact_name: Visitor name if captured during escalation form submit.
        contact_email: Visitor email if captured.
        contact_phone: Visitor phone if captured.

    Returns:
        True when Resend accepted the send (2xx), False otherwise.
    """
    if not settings.resend_api_key:
        log.error(
            "escalation_email_skipped",
            reason="RESEND_API_KEY not configured",
        )
        return False
    if not settings.resend_from_email:
        log.error(
            "escalation_email_skipped",
            reason="RESEND_FROM_EMAIL not configured",
        )
        return False

    body_text, body_html = _render_bodies(
        bot_name=bot_name,
        visitor_message=visitor_message,
        session_id=session_id,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )

    payload = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": f"New Escalation: {bot_name} needs your attention",
        "text": body_text,
        "html": body_html,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(_RESEND_API_URL, headers=headers, json=payload)
    except httpx.HTTPError as e:
        # Covers connect timeouts, DNS failures, TLS errors, read timeouts.
        # Anything network-shaped lands here.
        log.error(
            "escalation_email_http_error",
            error=str(e),
            to=to_email,
            bot=bot_name,
        )
        return False
    except Exception as e:
        # Defensive: callers (escalate router, report scheduler) wrap us in
        # their own try/except, so a leak here would still be caught, but
        # logging at this layer keeps the failure attributable to the
        # email path rather than to the caller.
        log.error(
            "escalation_email_unexpected_error",
            error=str(e),
            to=to_email,
            bot=bot_name,
        )
        return False

    if 200 <= response.status_code < 300:
        # Resend's success body is {"id": "<uuid>"}; capturing the id makes
        # cross-referencing a failed delivery in Resend's dashboard trivial.
        resend_id = None
        try:
            resend_id = response.json().get("id")
        except Exception:
            pass
        log.info(
            "escalation_email_sent",
            to=to_email,
            bot=bot_name,
            session=session_id,
            resend_id=resend_id,
        )
        return True

    # Non-2xx: log status + truncated body. Common failures are 401 (bad API
    # key), 403 (domain not verified), 422 (malformed payload), 429 (rate
    # limit). Body is truncated to 500 chars to keep log lines bounded.
    log.error(
        "escalation_email_resend_failed",
        status=response.status_code,
        body=response.text[:500],
        to=to_email,
        bot=bot_name,
    )
    return False
