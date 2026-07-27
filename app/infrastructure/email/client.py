import logging

import resend

from app.config import get_settings

logger = logging.getLogger(__name__)


def email_enabled() -> bool:
    return bool(get_settings().resend_api_key)


def send_email(to: str, subject: str, html: str) -> None:
    """Sends via Resend when configured; otherwise logs the message as a
    dev-mode fallback so registration/reset flows never get blocked on a
    missing key (mirrors the storage-encryption-key ephemeral fallback in
    app/config.py)."""
    settings = get_settings()
    if not email_enabled():
        logger.info("Email not configured -- logging instead of sending.\nTo: %s\nSubject: %s\n%s", to, subject, html)
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.email_from_address,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )
