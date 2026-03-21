import httpx
from typing import Optional
from backend.config import settings


async def send_slack_webhook(webhook_url: str, text: str) -> bool:
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json={"text": text}, timeout=10)
        return resp.status_code == 200


async def send_discord_webhook(webhook_url: str, content: str) -> bool:
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json={"content": content}, timeout=10)
        return resp.status_code in (200, 204)


async def send_whatsapp_webhook(webhook_url: str, body: str) -> bool:
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


async def dispatch_webhook(platform: str, webhook_url: str, text: str) -> bool:
    if platform == "slack":
        return await send_slack_webhook(webhook_url, text)
    elif platform == "discord":
        return await send_discord_webhook(webhook_url, text)
    elif platform == "whatsapp":
        return await send_whatsapp_webhook(webhook_url, text)
    return False
