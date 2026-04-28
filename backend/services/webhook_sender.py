import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.config import settings


SIGNATURE_HEADER = "X-SupportBot-Signature"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sign_payload(body: bytes, secret: str) -> str:
    """HMAC-SHA256 over the raw body bytes. Returned as 'sha256=<hex>'.

    Format mirrors Stripe / GitHub conventions so receivers can use the
    same verification idiom they already know.
    """
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _event_subscribed(events_json: Optional[str], event: Optional[str]) -> bool:
    """Decide whether a webhook should receive this event.

    Rules:
      - `events_json` is None / empty   → no filter (legacy passthrough).
      - `event` is None (e.g. test ping) → no filter (don't drop manual sends).
      - Otherwise, parse as a JSON list and check membership.
      - Malformed JSON → fail open (treat as no filter). Losing real
        notifications because someone hand-edited the events column with
        a typo is worse than the alternative.
    """
    if not events_json or event is None:
        return True
    try:
        subs = json.loads(events_json)
    except (ValueError, TypeError):
        return True
    if not isinstance(subs, list) or not subs:
        return True
    return event in subs


async def _post_signed_json(
    webhook_url: str,
    payload: dict,
    secret: Optional[str],
    timeout: int = 10,
) -> httpx.Response:
    """POST a JSON payload, signing with HMAC-SHA256 if secret is set.

    The body is encoded once into stable bytes and reused for both the
    signature and the request, so receivers and senders see byte-for-byte
    identical input to the HMAC. Encoding it twice (e.g. via httpx's
    `json=`) would risk whitespace drift and silent verification failures.
    """
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers[SIGNATURE_HEADER] = _sign_payload(body, secret)
    async with httpx.AsyncClient() as client:
        return await client.post(webhook_url, content=body, headers=headers, timeout=timeout)


# ── Per-platform senders ──────────────────────────────────────────────────────

async def send_slack_webhook(webhook_url: str, text: str, secret: Optional[str] = None) -> bool:
    resp = await _post_signed_json(webhook_url, {"text": text}, secret)
    return resp.status_code == 200


async def send_discord_webhook(webhook_url: str, content: str, secret: Optional[str] = None) -> bool:
    resp = await _post_signed_json(webhook_url, {"content": content}, secret)
    return resp.status_code in (200, 204)


async def send_custom_https_webhook(
    webhook_url: str,
    text: str,
    secret: Optional[str],
    event: Optional[str] = None,
) -> bool:
    """POST a structured event envelope to a tenant-controlled HTTPS endpoint.

    Body shape (locked-in contract — receivers depend on this):
        {
          "event":     "<event-type>" | null,
          "text":      "<message>",
          "timestamp": "<RFC3339 UTC, e.g. 2026-04-28T12:34:56Z>"
        }

    Always signed (the route validator requires a secret on custom_https
    webhooks, so this should never be called without one — but we don't
    crash if it is, we just send unsigned).
    """
    payload = {
        "event": event,
        "text": text,
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    resp = await _post_signed_json(webhook_url, payload, secret)
    return 200 <= resp.status_code < 300


async def send_whatsapp_webhook(webhook_url: str, body: str) -> bool:
    """WhatsApp via Twilio. Uses Twilio's basic-auth — our HMAC doesn't apply."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    data = {
        "Body": body,
        "From": settings.twilio_whatsapp_from or "whatsapp:+14155238886",
        "To": webhook_url,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            data=data,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=10,
        )
        return resp.status_code in (200, 201)


# ── Public entry point ────────────────────────────────────────────────────────

async def dispatch_webhook(
    platform: str,
    webhook_url: str,
    text: str,
    *,
    secret: Optional[str] = None,
    events: Optional[str] = None,
    event: Optional[str] = None,
) -> bool:
    """Send a notification to one webhook destination.

    New keyword-only params (`secret`, `events`, `event`) default to None
    so existing positional callers — `dispatch_webhook(platform, url, text)`
    — keep working unchanged. They just won't get filtering or signing.

    Returns:
      - True  on successful HTTP dispatch
      - True  if the webhook isn't subscribed to this event (skip ≠ failure)
      - False on transport / HTTP errors, or for unknown platforms
    """
    if not _event_subscribed(events, event):
        return True

    if platform == "slack":
        return await send_slack_webhook(webhook_url, text, secret)
    elif platform == "discord":
        return await send_discord_webhook(webhook_url, text, secret)
    elif platform == "whatsapp":
        return await send_whatsapp_webhook(webhook_url, text)
    elif platform == "custom_https":
        return await send_custom_https_webhook(webhook_url, text, secret, event)
    return False
