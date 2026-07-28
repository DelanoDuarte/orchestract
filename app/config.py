import logging
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _normalize_database_url(url: str) -> str:
    """Coerce a managed-provider Postgres URL to the async driver the app and
    Alembic use.

    Managed Postgres providers (Render, Railway, Heroku, Supabase, Fly, ...)
    hand out ``postgres://`` / ``postgresql://`` URLs, often with a
    ``?sslmode=require`` query param. Two things break the async stack:

    * No driver in the scheme -> SQLAlchemy picks its default *sync* driver,
      psycopg2, which this async-only app doesn't install
      (``ModuleNotFoundError: No module named 'psycopg2'``).
    * ``sslmode`` is a libpq/psycopg2 param name; asyncpg's connect() rejects it
      and instead takes the equivalent value under ``ssl`` (asyncpg maps the
      libpq strings ``require``/``verify-full``/``disable``/...).

    So: force the ``+asyncpg`` driver and rename ``sslmode`` -> ``ssl``. URLs
    that already name a driver keep it; SQLite and other URLs pass through.
    """
    if url.startswith("postgres://"):  # Heroku-style scheme
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):  # no driver -> would default to psycopg2
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    if url.startswith("postgresql+asyncpg://") and "sslmode=" in url:
        parts = urlsplit(url)
        query = [(("ssl" if k == "sslmode" else k), v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


def _generate_ephemeral_key() -> str:
    logger.warning(
        "ORCHESTRACT_STORAGE_ENCRYPTION_KEY is not set; generated an ephemeral key for this "
        "process. Stored storage credentials (bucket keys, OAuth tokens) will become "
        "undecryptable on restart. Set a persistent key in production."
    )
    return Fernet.generate_key().decode()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRACT_", env_file=".env", extra="ignore")

    # "development" | "production". Set ORCHESTRACT_APP_ENV=production in real
    # deployments (Docker Compose's prod overlay does). In production the app
    # refuses to boot on SQLite (see _validate_database) so you can't ship the
    # single-file dev database by accident.
    app_env: str = "development"

    # SQLAlchemy async URL. The SQLite default is a zero-setup convenience for
    # `uv run` local dev only. Docker Compose overrides this to
    # postgresql+asyncpg://...@db for both local and prod stacks; for a
    # non-Compose deployment set ORCHESTRACT_DATABASE_URL to your Postgres DSN,
    # e.g. postgresql+asyncpg://user:pass@host:5432/orchestract
    database_url: str = "sqlite+aiosqlite:///./orchestract.db"

    # Session cookie. Set ORCHESTRACT_SESSION_COOKIE_SECURE=true in production so
    # the session cookie is only ever sent over HTTPS. Left off by default so
    # local http://127.0.0.1 development keeps working.
    session_cookie_secure: bool = False

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
    # configured" state until an administrator sets these. Prefer a restricted
    # API key (rk_...) over a full secret key in production. Create the products
    # and prices with `uv run python -m app.infrastructure.billing.setup_stripe`,
    # which prints the price ids to paste below.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_team: str = ""
    stripe_price_business: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @model_validator(mode="after")
    def _validate_database(self) -> "Settings":
        """Normalize the DB URL to the async driver, then guard against SQLite in
        production (which would silently use an ephemeral single-file DB) and
        flag SQLite use in dev so it's never a surprise."""
        normalized = _normalize_database_url(self.database_url)
        if normalized != self.database_url:
            logger.info("Normalized Postgres URL to the async asyncpg driver.")
            self.database_url = normalized
        if self.database_url.startswith("sqlite"):
            if self.is_production:
                raise ValueError(
                    "ORCHESTRACT_APP_ENV=production but ORCHESTRACT_DATABASE_URL is SQLite "
                    f"({self.database_url!r}). Point it at PostgreSQL, e.g. "
                    "postgresql+asyncpg://user:pass@host:5432/orchestract."
                )
            logger.info(
                "Using SQLite (%s) for local development. Production must use PostgreSQL "
                "(set ORCHESTRACT_DATABASE_URL); Docker Compose does this automatically.",
                self.database_url,
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
