from app.infrastructure.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    get_current_locale,
    gettext,
    negotiate_from_header,
    set_current_locale,
)


def test_negotiate_prefers_highest_quality_supported_language():
    # de is unsupported and drops out; fr wins over es on q-weight.
    assert negotiate_from_header("de-DE,fr;q=0.9,es;q=0.4") == "fr"


def test_negotiate_matches_region_variant_to_base_language():
    assert negotiate_from_header("pt-BR,pt;q=0.9,en;q=0.5") == "pt"


def test_negotiate_returns_none_when_nothing_supported():
    assert negotiate_from_header("de-DE,ja;q=0.9") is None
    assert negotiate_from_header("") is None


def test_set_current_locale_coerces_unsupported_to_default():
    assert set_current_locale("fr") == "fr"
    assert get_current_locale() == "fr"
    # Anything not supported (None, garbage) falls back to English.
    assert set_current_locale("xx") == DEFAULT_LOCALE
    assert set_current_locale(None) == DEFAULT_LOCALE


def test_all_supported_locales_have_names_and_english_is_default():
    assert DEFAULT_LOCALE == "en"
    assert set(SUPPORTED_LOCALES) == {"en", "pt", "fr", "es"}


def test_compiled_catalogs_translate_a_known_string():
    # Exercises the actual .mo files shipped in app/web/translations.
    set_current_locale("fr")
    assert gettext("Log in") == "Se connecter"
    set_current_locale("pt")
    assert gettext("Log in") == "Entrar"
    set_current_locale("en")
    # English is the source language -- msgid passes through unchanged.
    assert gettext("Log in") == "Log in"
