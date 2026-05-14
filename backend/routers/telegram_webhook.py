"""Telegram webhook receiver for the Connect Telegram button flow.

When an admin clicks "Connect Telegram for alerts" in the admin panel,
they are directed to a ``https://t.me/<bot>?start=botid_<bot_id>`` deep
link. The user taps Start, and Telegram sends an update to this webhook.
The handler extracts the sender's numeric chat ID and stores it on the
tenant's ``BotConfig.telegram_handle``.

The endpoint is deliberately public (no auth) — Telegram webhook payloads
carry a ``secret_token`` that we verify against
``settings.telegram_webhook_secret``. Without the secret, an attacker who
knows the Render URL could forge updates, but the only damage is a bogus
chat ID being stored (no data exfiltration).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db, BotConfig
from backend.services.telegram_notify import send_telegram_message

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Telegram updates via webhook.

    Handles ``/start botid_<bot_id>`` — extracts the sender's numeric
    ``chat_id`` and stores it on ``BotConfig.telegram_handle``.
    Responds with a confirmation message sent back to the same chat.
    """
    update = await request.json()

    if settings.telegram_webhook_secret:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if received != settings.telegram_webhook_secret:
            return JSONResponse({"ok": False, "description": "Unauthorized"}, status_code=401)

    message = update.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))

    if text.startswith("/start botid_"):
        bot_id = text.split("botid_", 1)[1].strip()
        config = db.query(BotConfig).filter(BotConfig.bot_id == bot_id).first()
        if config:
            config.telegram_handle = chat_id
            db.commit()

    if chat_id:
        await send_telegram_message(
            "✅ Connected! Escalations will be sent here.",
            chat_id_override=chat_id,
        )

    return {"ok": True}
