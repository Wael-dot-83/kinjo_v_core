"""The language switcher must move the server's rendering language, not just the DB.

Server-side templates resolve ui_lang from the kinjo_lang cookie. That cookie was
only written at login, so changing the preference persisted to the database while
the server kept rendering the previous language. The client then rewrote
documentElement.lang/dir to the new language, leaving every page with mixed
Arabic/English text and a direction that disagreed with its own content.
"""
import ui_language


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


def test_no_frontend_code_writes_the_kinjo_lang_cookie():
    """The server is the sole writer of kinjo_lang.

    A document.cookie write from the page origin is host-only
    (www.kinjordan.org) while the server sets the cookie with COOKIE_DOMAIN
    (.kinjordan.org). Neither overwrites the other, so the browser kept both
    with different values and the server read whichever it was sent first --
    asking for English rendered Arabic and vice versa. Reading the cookie is
    fine; writing it from the client is what must never come back.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in list((root / "static" / "js").rglob("*.js")) + list((root / "templates").rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            # assignment to document.cookie mentioning kinjo_lang on the same line
            if re.search(r"document\.cookie\s*=", line) and "kinjo_lang" in line:
                offenders.append(f"{path.relative_to(root)}:{line_no}")
    assert not offenders, "client-side kinjo_lang cookie writes reintroduced: " + ", ".join(offenders)


def test_client_still_reads_the_cookie_and_calls_the_api():
    """Removing the write must not turn into removing the sync entirely."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "admin_i18n.js").read_text(encoding="utf-8")
    assert "kinjo_lang" in js, "client no longer reads the server's cookie"
    assert "/api/users/me/language" in js, "client no longer asks the server to persist the change"


def test_anonymous_endpoint_sets_cookie_without_touching_any_user(client):
    """Login and reset-password switch language before a session exists."""
    resp = client.post("/api/ui-language", json={"language": "en"})
    assert resp.status_code == 200
    assert resp.json()["language"] == "en"
    assert resp.cookies["kinjo_lang"] == "en"

    back = client.post("/api/ui-language", json={"language": "ar"})
    assert back.status_code == 200
    assert back.cookies["kinjo_lang"] == "ar"


def test_anonymous_endpoint_rejects_unsupported_language(client):
    resp = client.post("/api/ui-language", json={"language": "fr"})
    assert resp.status_code == 400
    assert "kinjo_lang" not in resp.cookies


def test_anonymous_endpoint_performs_no_database_mutation():
    """An unauthenticated caller must not be able to change a user record."""
    import inspect

    import api.users as users_mod

    src = inspect.getsource(users_mod.set_ui_language)
    for forbidden in ("db.commit", "db.add", "db.query", "current_user", "get_db"):
        assert forbidden not in src, f"anonymous endpoint touches {forbidden}"


def test_both_paths_use_the_same_cookie_helper():
    import inspect

    import api.users as users_mod

    anon = inspect.getsource(users_mod.set_ui_language)
    auth = inspect.getsource(users_mod.update_user_language)
    assert "_set_ui_language_cookie(" in anon
    assert "_set_ui_language_cookie(" in auth
