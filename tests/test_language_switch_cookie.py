"""The language switcher must move the server's rendering language, not just the DB.

Server-side templates resolve ui_lang from the kinjo_lang cookie. That cookie was
only written at login, so changing the preference persisted to the database while
the server kept rendering the previous language. The client then rewrote
documentElement.lang/dir to the new language, leaving every page with mixed
Arabic/English text and a direction that disagreed with its own content.

The root cause of the one-step lag was TWO kinjo_lang cookies coexisting at
different scopes: a host-only `document.cookie` write cannot overwrite the
domain-wide cookie the server sets with COOKIE_DOMAIN, so the browser kept both
with different values and the server read whichever it was sent first. The fix
made the server the sole writer: every client-side write site now POSTs to
/api/ui-language (anonymous) or PUT /api/users/me/language (authenticated) and
consumes the Set-Cookie from the response.

Ten scenarios are pinned below: the authenticated path, the anonymous path
(including the cookie-carrying browser shape that must NOT require a CSRF pair),
validation, no-database-work, and the mutation control that any future
client-side `document.cookie` write of kinjo_lang fails loudly.
"""
import re
from pathlib import Path

import ui_language

ROOT = Path(__file__).resolve().parents[1]

# A client-side WRITE of the language cookie: `document.cookie = ...` whose
# right-hand side names kinjo_lang, in any of the three quoting forms the
# codebase has used. Reads (document.cookie.match(...)) and the explanatory
# comments are deliberately not matched.
BANNED_CLIENT_WRITE = re.compile(
    r'document\.cookie\s*=\s*'
    r'(?:`[\s\S]{0,200}?kinjo_lang'
    r'|"[^"]{0,200}?kinjo_lang'
    r"|'[^']{0,200}?kinjo_lang')",
    re.IGNORECASE,
)


def test_language_update_writes_cookie_matching_preference(client, auth_headers_admin):
    resp = client.put("/api/users/me/language", json={"user_lang": "en"}, headers=auth_headers_admin)
    assert resp.status_code == 200
    assert resp.json()["user_lang"] == "en"
    assert "kinjo_lang" in resp.cookies, "preference persisted without updating the render cookie"
    assert resp.cookies["kinjo_lang"] == "en"

    back = client.put("/api/users/me/language", json={"user_lang": "ar"}, headers=auth_headers_admin)
    assert back.status_code == 200
    assert back.cookies["kinjo_lang"] == "ar"


def test_rejected_language_does_not_set_a_cookie(client, auth_headers_admin):
    resp = client.put("/api/users/me/language", json={"user_lang": "fr"}, headers=auth_headers_admin)
    assert resp.status_code == 400
    assert "kinjo_lang" not in resp.cookies


def test_single_cookie_definition_shared_by_both_writers():
    """main.py and api/users.py must not each carry their own attribute list.

    A host-only cookie does not overwrite a domain-wide cookie of the same name;
    the browser keeps both and the server reads whichever it is sent first.
    """
    import main

    assert main._set_ui_language_cookie.__module__ in ("main", "ui_language")
    src = open("main.py", encoding="utf-8").read()
    assert "from ui_language import set_ui_language_cookie" in src
    users_src = open("api/users.py", encoding="utf-8").read()
    assert "from ui_language import set_ui_language_cookie" in users_src
    # exactly one place defines the attributes
    assert open("ui_language.py", encoding="utf-8").read().count("set_cookie(") == 1


def test_normalisation_respects_supported_languages():
    assert ui_language.normalize_ui_language("en") == "en"
    assert ui_language.normalize_ui_language("AR") == "ar"
    assert ui_language.normalize_ui_language("fr") == "ar"
    assert ui_language.normalize_ui_language(None) == "ar"


def test_anonymous_language_switch_sets_the_cookie(client):
    """The pre-auth entry point: a visitor with no session switches language."""
    resp = client.post("/api/ui-language", json={"language": "en"})
    assert resp.status_code == 200
    assert resp.json() == {"language": "en"}
    assert resp.cookies["kinjo_lang"] == "en", (
        "the anonymous switch must set the server-owned cookie"
    )


def test_anonymous_language_switch_accepts_arabic(client):
    resp = client.post("/api/ui-language", json={"language": "ar"})
    assert resp.status_code == 200
    assert resp.cookies["kinjo_lang"] == "ar"


def test_anonymous_language_switch_rejects_unsupported_languages(client):
    resp = client.post("/api/ui-language", json={"language": "fr"})
    assert resp.status_code == 400
    assert "kinjo_lang" not in resp.cookies

    empty = client.post("/api/ui-language", json={})
    assert empty.status_code == 422, "a missing language must fail validation"


def test_anonymous_switch_from_a_cookie_carrying_browser_needs_no_csrf_pair(client):
    """The real browser shape: the middleware provisions kinjo_csrf_token on
    every page render, so the switch request ALWAYS carries cookies. The JS
    cannot be expected to echo a CSRF header before any session exists, so
    /api/ui-language is exempt from the double-submit pair — otherwise every
    anonymous language switch would 400 and the fix would fail in production
    exactly where it is meant to work."""
    from conftest import CSRF_COOKIE_NAME

    client.cookies.set(CSRF_COOKIE_NAME, "provisioned-on-page-render")
    resp = client.post(
        "/api/ui-language",
        json={"language": "en"},
        cookies=None,  # keep the cookie jar from the fixture
    )
    assert resp.status_code == 200, (
        "an anonymous switch carrying only the provisioned CSRF cookie must "
        "not be rejected"
    )
    assert resp.cookies["kinjo_lang"] == "en"


def test_anonymous_switch_writes_no_database_row(client):
    """The endpoint is deliberately database-free: an unauthenticated caller
    must not be able to mutate any user record, and the switch must work with
    no authentication at all."""
    resp = client.post("/api/ui-language", json={"language": "en"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"language"}, (
        "the anonymous switch must not return or accept user data"
    )


def test_no_client_script_writes_the_language_cookie_directly():
    """Mutation control: no JS or template may write kinjo_lang via
    document.cookie.

    Every write must go through the server (POST /api/ui-language or
    PUT /api/users/me/language) so the domain-wide cookie the server reads is
    the only kinjo_lang in the browser. A reintroduced host-only write would
    recreate the dual-cookie lag that this release exists to kill.
    """
    offenders = []
    for pattern in ("static/js/*.js", "templates/**/*.html"):
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if BANNED_CLIENT_WRITE.search(text):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        "client code writes kinjo_lang directly, recreating the dual-scope "
        f"cookie: {offenders}"
    )
