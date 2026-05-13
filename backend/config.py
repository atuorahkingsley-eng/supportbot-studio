import os
import sys
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

    # Zoho SMTP for escalation email delivery
    zoho_smtp_user: str = ""
    zoho_smtp_password: str = ""
    zoho_smtp_host: str = "smtp.zoho.com"
    zoho_smtp_port: int = 465

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    twilio_whatsapp_to: str = ""

    database_url: str = "sqlite:///./data/supportbot.db"
    upload_dir: str = "./uploads"

    # Public URL of the deployed app — used as the credentialed CORS origin
    # for admin/auth endpoints. Dev fallback is the local uvicorn host.
    app_url: str = "http://localhost:8000"

    # Multi-tenant auth
    jwt_secret_key: str = "dev-insecure-key-change-this-in-production"
    super_admin_username: str = "admin"
    super_admin_password: str = "changeme123"

    # Auto-healing
    auto_heal_enabled: bool = True
    health_check_interval_minutes: int = 15
    max_heal_retries: int = 2

    # Boot guard and dev seeding — split into two env vars so operators can
    # disable the boot guard independently of seeding demo data (or vice versa).
    skip_boot_guard: bool = False
    seed_dev_data: bool = False


settings = Settings()

# Boot guard — fail fast if defaults are still set
DANGEROUS_DEFAULTS = {
    "JWT_SECRET_KEY": "dev-insecure-key-change-this-in-production",
    "SUPER_ADMIN_PASSWORD": "changeme123",
}

if not settings.skip_boot_guard:
    for key, default_val in DANGEROUS_DEFAULTS.items():
        actual = os.getenv(key, "")
        if not actual or actual == default_val:
            print(f"STARTUP BLOCKED: {key} is missing or still set to default.", file=sys.stderr, flush=True)
            sys.exit(1)

print("Boot guard passed.", flush=True)
