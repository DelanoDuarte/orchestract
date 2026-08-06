"""Internationalization (i18n) support.

The app renders server-side with Jinja, so translation runs through GNU
gettext catalogs (`.po`/`.mo`) loaded per request. Instead of threading a
`locale` argument through every render, the active locale lives in a
``ContextVar`` set once per request (see `install_request_locale` in
`app/api/deps.py`); the ``gettext``/``ngettext`` callables the Jinja i18n
extension calls read it back at render time. Because each request handler runs
in its own task, the ContextVar is naturally isolated between concurrent
requests.

English is the source language: its strings live inline in the templates, so
the ``en`` "catalog" is a no-op (``NullTranslations``) that returns the msgid
unchanged. Only pt/fr/es ship real `.mo` files.
"""

from __future__ import annotations

import contextvars
from functools import lru_cache
from pathlib import Path

from babel import negotiate_locale
from babel.support import NullTranslations, Translations

DEFAULT_LOCALE = "en"

# Locale code -> its endonym (name written in that language), for the switcher.
LOCALE_NAMES: dict[str, str] = {
    "en": "English",
    "pt": "Português",
    "fr": "Français",
    "es": "Español",
}
SUPPORTED_LOCALES: tuple[str, ...] = tuple(LOCALE_NAMES)

# Cookie the language switcher writes so an anonymous visitor's choice sticks,
# and so a logged-in user's saved preference is echoed for fast lookup.
LOCALE_COOKIE_NAME = "locale"

_TRANSLATIONS_DIR = Path(__file__).resolve().parents[2] / "web" / "translations"

_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_locale", default=DEFAULT_LOCALE
)


@lru_cache(maxsize=len(SUPPORTED_LOCALES))
def _translations(locale: str) -> NullTranslations:
    """Load (and cache) the compiled catalog for a locale. English -- the
    source language -- needs no catalog, and any locale whose `.mo` is missing
    falls back to returning msgids verbatim rather than erroring."""
    if locale == DEFAULT_LOCALE:
        return NullTranslations()
    return Translations.load(_TRANSLATIONS_DIR, [locale], domain="messages")


def set_current_locale(locale: str | None) -> str:
    """Pin the active locale for the current request/task, coercing anything
    unsupported to English. Returns the locale actually set."""
    resolved = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    _current_locale.set(resolved)
    return resolved


def get_current_locale() -> str:
    return _current_locale.get()


def gettext(message: str) -> str:
    return _translations(get_current_locale()).gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translations(get_current_locale()).ngettext(singular, plural, n)


def _parse_accept_language(header: str) -> list[str]:
    """Turn an ``Accept-Language`` header into an ordered list of locale codes,
    honouring q-weights. ``pt-BR`` is kept as ``pt_BR`` so Babel can also match
    the base ``pt``."""
    ranked: list[tuple[float, str]] = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        code, _, params = part.partition(";")
        code = code.strip().replace("-", "_")
        if not code:
            continue
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 1.0
        ranked.append((quality, code))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [code for _, code in ranked]


def negotiate_from_header(accept_language: str) -> str | None:
    """Best supported locale for an ``Accept-Language`` header, or None."""
    preferred = _parse_accept_language(accept_language)
    if not preferred:
        return None
    # Babel matches "pt_BR" against available "pt" via its separator handling.
    return negotiate_locale(preferred, list(SUPPORTED_LOCALES), sep="_")


def install_jinja_i18n(env) -> None:
    """Wire the gettext machinery into a Jinja environment: enables
    ``{% trans %}`` / ``{{ _(...) }}`` and the newstyle interpolation used in
    the templates."""
    env.add_extension("jinja2.ext.i18n")
    env.install_gettext_callables(gettext, ngettext, newstyle=True)
