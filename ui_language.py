"""One definition of the UI-language cookie.

The cookie was previously written in main.py only, at login. When the language
endpoint in api/users.py also needed to write it, copying the attributes would
have invited drift: the cookie is only interchangeable between writers if the
domain matches exactly. A cookie written host-only does not replace a
domain-wide cookie of the same name — the browser keeps both, and the server
then reads whichever it is sent first, which is how the UI ended up rendering
one language while the DOM claimed another.

main.py and api/users.py both go through here so there is exactly one set of
attributes in the codebase.
"""

from typing import Optional

from fastapi import Response

from config import settings

DEFAULT_UI_LANGUAGE = "ar"
SUPPORTED_UI_LANGUAGES = {"ar", "en"}


def normalize_ui_language(value: Optional[str]) -> str:
    """Return a supported UI language code, defaulting to Arabic.

    The site is Arabic-primary but every template carries bilingual
    ``{% if ui_lang == 'en' %}`` blocks and the UI exposes a language
    switcher (``/api/users/me/language``).  Returning ``ar``
    unconditionally made the server ignore the user's English choice, so
    pages rendered Arabic while the client rewrote ``documentElement`` to
    LTR — mixed-language output on every page.
    """
    normalized = str(value or DEFAULT_UI_LANGUAGE).strip().lower()
    return normalized if normalized in SUPPORTED_UI_LANGUAGES else DEFAULT_UI_LANGUAGE


def set_ui_language_cookie(response: Response, language: Optional[str]) -> None:
    """Write the kinjo_lang cookie so server-side rendering follows the user's choice."""
    response.set_cookie(
        key="kinjo_lang",
        value=normalize_ui_language(language),
        max_age=31536000,  # 1 year
        path="/",
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.ENVIRONMENT.lower() == "production",
        httponly=False,  # the client reads it to keep its own state in sync
        domain=settings.COOKIE_DOMAIN or None,
    )


def ensure_default_ui_language_cookie(request, response) -> None:
    """Plant the Arabic default on the first HTML visit.

    A leftover localStorage kinjo_lang=en from a previous session used to
    flip the client to English after the server had rendered Arabic. The
    client now reads the cookie first; planting ar here makes that first
    visit Arabic even when localStorage still holds en. An existing cookie
    is left alone so an explicit English choice still wins.
    """
    if getattr(request, "method", "GET") not in {"GET", "HEAD"}:
        return
    path = getattr(getattr(request, "url", None), "path", "") or ""
    if path.startswith("/api") or path.startswith("/static"):
        return
    cookies = getattr(request, "cookies", {}) or {}
    if cookies.get("kinjo_lang"):
        return
    set_ui_language_cookie(response, DEFAULT_UI_LANGUAGE)
