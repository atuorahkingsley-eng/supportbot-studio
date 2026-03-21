import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ before pydantic-settings instantiates
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    emailjs_service_id: str = ""
    emailjs_template_id: str = ""
    emailjs_public_key: str = ""
    emailjs_private_key: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    twilio_whatsapp_to: str = ""

    database_url: str = "sqlite:///./data/supportbot.db"
    upload_dir: str = "./uploads"

    # Multi-tenant auth
    jwt_secret_key: str = "dev-insecure-key-change-this-in-production"
    super_admin_username: str = "admin"
    super_admin_password: str = "changeme123"

    # Auto-healing
    auto_heal_enabled: bool = True
    health_check_interval_minutes: int = 15
    max_heal_retries: int = 2


settings = Settings()
