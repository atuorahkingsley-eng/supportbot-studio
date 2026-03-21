import httpx
from backend.config import settings


async def send_telegram_message(text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        return resp.status_code == 200
