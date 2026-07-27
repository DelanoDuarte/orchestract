import logging
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _generate_ephemeral_key() -> str:
    logger.warning(
        "ORCHESTRACT_STORAGE_ENCRYPTION_KEY is not set; generated an ephemeral key for this "
        "process. Stored storage credentials (bucket keys, OAuth tokens) will become "
        "undecryptable on restart. Set a persistent key in production."
    )
    return Fernet.generate_key().decode()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRACT_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./orchestract.db"

    # File storage
    storage_encryption_key: str = Field(default_factory=_generate_ephemeral_key)
    local_storage_root: str = "./storage"

    # OAuth (Google Drive / OneDrive read-only import). Empty by default -- the
    # "Connect Google Drive"/"Connect OneDrive" buttons render disabled until an
    # administrator registers an app with each provider and sets these.
    oauth_redirect_base: str = "http://127.0.0.1:8000"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    microsoft_oauth_client_id: str = ""
    microsoft_oauth_client_secret: str = ""

    # Transactional email (Resend). Empty by default -- send_email() logs the
    # message instead of sending it until this is configured.
    resend_api_key: str = ""
    email_from_address: str = "Orchestract <onboarding@resend.dev>"
    app_base_url: str = "http://127.0.0.1:8000"

    # Stripe (test mode). Empty by default -- billing pages render a "not
    # configured" state until an administrator sets these.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_team: str = ""
    stripe_price_business: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
