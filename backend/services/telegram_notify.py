from typing import Optional

import httpx

from backend.config import settings


async def send_telegram_message(
    text: str,
    chat_id_override: Optional[str] = None,
) -> bool:
    """Send a Telegram message via the platform bot.

    If `chat_id_override` is provided, the message goes to that chat instead
    of the platform-wide settings.telegram_chat_id. Used for per-tenant
    escalations (escalate.py) where the tenant has set their own
    telegram_handle on BotConfig.

    System-level callers (auto-healer, error middleware via
    `send_telegram_alert`) deliberately don't pass the override — those
    alerts always go to the platform operator's chat.
    """
    if not settings.telegram_bot_token:
        return False
    chat_id = chat_id_override or settings.telegram_chat_id
    if not chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            return resp.status_code == 200
    except Exception:
        return False


# Alias used by auto-healer and error middleware. Always goes to the
# platform-wide chat — those alerts are not tenant-scoped.
async def send_telegram_alert(text: str) -> bool:
    return await send_telegram_message(text)
