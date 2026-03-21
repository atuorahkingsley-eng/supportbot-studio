import httpx
from backend.config import settings


async def send_emailjs(subject: str, message: str, to_email: str = "") -> bool:
    if not settings.emailjs_service_id or not settings.emailjs_public_key:
        return False

    url = "https://api.emailjs.com/api/v1.0/email/send"
    payload = {
        "service_id": settings.emailjs_service_id,
        "template_id": settings.emailjs_template_id,
        "user_id": settings.emailjs_public_key,
        "accessToken": settings.emailjs_private_key,
        "template_params": {
            "subject": subject,
            "message": message,
            "to_email": to_email,
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        return resp.status_code == 200
