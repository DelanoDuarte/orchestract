import re
from datetime import UTC, datetime

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "n-a"


def utcnow() -> datetime:
    return datetime.now(UTC)
