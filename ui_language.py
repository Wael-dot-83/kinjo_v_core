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


def normalize_ui_language(value: Optional[str]) -> str:
    """Arabic is the mandatory site language and RTL is therefore universal."""
    return DEFAULT_UI_LANGUAGE


def set_ui_language_cookie(response: Response, language: Optional[str]) -> None:
    """Write the mandatory Arabic UI preference for every client."""
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
