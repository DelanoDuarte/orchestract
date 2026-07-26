import re
from datetime import UTC, datetime

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "n-a"


def utcnow() -> datetime:
    """Naive UTC timestamp -- SQLite (this app's only backend so far) drops
    tzinfo on round-trip regardless of the column type, so every value read
    back from the DB is naive. Returning naive here too keeps freshly
    computed timestamps comparable to ones loaded from a row (needed by
    UserSession.is_valid()) instead of raising on offset-aware vs -naive."""
    return datetime.now(UTC).replace(tzinfo=None)
