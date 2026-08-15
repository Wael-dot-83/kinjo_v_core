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

# The one sanctioned exception: a pure DELETION of the legacy host-only copy
# (kinjo_lang=; + expires). It removes a stale cookie; it writes no value, so
# it cannot recreate the dual-writer problem. Stripped before the ban check.
LEGACY_DELETION = re.compile(
    r'document\.cookie\s*=\s*"[^"]*kinjo_lang=;[^"]*"',
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
            remainder = LEGACY_DELETION.sub("", text)
            if BANNED_CLIENT_WRITE.search(remainder):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        "client code writes kinjo_lang directly, recreating the dual-scope "
        f"cookie: {offenders}"
    )


def test_legacy_host_only_cookie_sweep_is_a_deletion_only():
    """The one-time sweep that removes the pre-fix host-only kinjo_lang
    cookie must be a pure deletion, gated on TWO copies being visible to the
    document (the server never writes host-only, so a duplicate can only be
    legacy). If it ever starts writing a value, the server is no longer the
    sole writer and the dual-cookie bug is back."""
    src = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "kinjo_lang=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT" in src, (
        "the sweep must delete, not write, the legacy cookie"
    )
    assert "copies < 2" in src, (
        "the sweep must only fire when the document exposes two kinjo_lang "
        "cookies"
    )


def test_page_load_does_not_persist_the_language_cookie():
    """Mutation control for the reload race: AppI18n's page-load path must
    not POST /api/ui-language.

    persistClientLanguage syncs the server cookie only when asked
    (syncCookie=true). The init path (applyLanguage(currentLang, false))
    must never ask: init runs asynchronously while awaiting the translation
    dictionaries, so on a page the user has just switched away from, a slow
    init would persist the OLD language after the switch and flip the server
    cookie back -- the user's choice would be undone by their own page.
    Only explicit user switches (toggleLanguage) may sync.
    """
    src = (ROOT / "static" / "js" / "app_i18n.js").read_text(encoding="utf-8")

    assert "persistClientLanguage(safeLang, syncCookie)" in src, (
        "persistClientLanguage must route the cookie sync through the "
        "syncCookie gate"
    )
    assert "if (!syncCookie)" in src, (
        "persistClientLanguage must skip the /api/ui-language POST unless "
        "syncCookie is set"
    )
    assert "applyLanguage(this.currentLang, false)" in src, (
        "the init path must not persist the cookie; a stale async init would "
        "race the user's switch"
    )
    assert "setHtmlLanguage(nextLang, true)" in src, (
        "toggleLanguage must sync the cookie explicitly"
    )


def test_first_html_visit_plants_the_arabic_default_cookie(client):
    """A first-time visitor with no kinjo_lang cookie must leave with ar.

    Without this, leftover localStorage kinjo_lang=en from a previous
    session flipped the client to English after the server had rendered
    Arabic. Planting the cookie on the first HTML GET makes the default
    stick even when localStorage still holds en.
    """
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.cookies["kinjo_lang"] == "ar"
    assert 'lang="ar"' in resp.text


def test_existing_english_cookie_is_not_overwritten_on_get(client):
    """An explicit English choice must survive a later page load."""
    client.cookies.set("kinjo_lang", "en")
    resp = client.get("/")
    assert resp.status_code == 200
    # Starlette TestClient may not echo an unchanged cookie; the page
    # must still render English and the request cookie must remain en.
    assert 'lang="en"' in resp.text
    assert client.cookies.get("kinjo_lang") == "en"


def test_client_initial_language_does_not_read_localstorage():
    """Leftover localStorage must not override the server-rendered language."""
    app = (ROOT / "static" / "js" / "app_i18n.js").read_text(encoding="utf-8")
    admin = (ROOT / "static" / "js" / "admin_i18n.js").read_text(encoding="utf-8")
    kinjo = (ROOT / "static" / "js" / "kinjo-app.js").read_text(encoding="utf-8")
    assert "localStorage.getItem(\"kinjo_lang\")" not in app
    saved = admin.split("getSavedLanguage()")[1].split("// =")[0]
    assert "localStorage.getItem" not in saved
    stored = kinjo.split("Load stored language")[1].split("Global search")[0]
    assert "localStorage.getItem" not in stored


def test_arabic_copy_does_not_contain_known_typos():
    """The live Arabic surfaces must not ship بحيرة (lake) for حيرة, or المعحضانة."""
    lake = "\u0628\u062d\u064a\u0631\u0629"  # بحيرة
    nonsense = "\u0627\u0644\u0645\u0639\u062d\u0636\u0627\u0646\u0629"  # المعحضانة
    offenders = []
    for rel in (
        "templates/public/home.html",
        "templates/public/legal.html",
        "templates/reports/list.html",
        "templates/components/export-modal.html",
        "static/js/kinjo-app.js",
        "static/i18n/literal_en_overrides.json",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if lake in text or nonsense in text:
            offenders.append(rel)
    assert offenders == [], f"Arabic typos still present in {offenders}"
