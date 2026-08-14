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
