def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_user_language_preference_defaults_to_ar(client, admin_token):
    response = client.get("/api/users/me/language", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["user_lang"] == "ar"


def test_user_language_preference_persists(client, admin_token):
    update_en = client.put(
        "/api/users/me/language",
        headers=_auth_headers(admin_token),
        json={"user_lang": "en"},
    )
    assert update_en.status_code == 200
    assert update_en.json()["user_lang"] == "en"

    read_en = client.get("/api/users/me/language", headers=_auth_headers(admin_token))
    assert read_en.status_code == 200
    assert read_en.json()["user_lang"] == "en"

    update_ar = client.put(
        "/api/users/me/language",
        headers=_auth_headers(admin_token),
        json={"user_lang": "ar"},
    )
    assert update_ar.status_code == 200
    assert update_ar.json()["user_lang"] == "ar"


def test_login_defaults_to_arabic_html_direction(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert 'lang="ar"' in response.text
    assert 'dir="rtl"' in response.text


def test_500_template_defaults_to_arabic_rtl():
    """The standalone error page must not bypass the site-wide Arabic default."""
    from fastapi.templating import Jinja2Templates
    from starlette.requests import Request

    templates = Jinja2Templates(directory="templates")
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = templates.TemplateResponse(request=request, name="500.html", context={})
    html = response.body.decode("utf-8")

    assert '<html lang="ar" dir="rtl"' in html
    assert "خطأ داخلي في الخادم" in html


def test_all_standalone_document_roots_default_to_arabic_rtl():
    """Every standalone browser entry point declares Arabic RTL at its root."""
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    expected_roots = {
        project_root / "templates" / "500.html": '<html lang="{{ ui_lang | default(\'ar\') }}" dir="{{ ui_dir | default(\'rtl\') }}"',
        project_root / "mobile" / "web" / "index.html": '<html lang="ar" dir="rtl">',
    }

    for path, expected in expected_roots.items():
        assert expected in path.read_text(encoding="utf-8"), path


def test_login_respects_english_cookie_direction(client):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/login")
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_dashboard_respects_english_cookie_language(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/dashboard", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_reports_page_respects_english_cookie(client, supervisor_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/reports", headers=_auth_headers(supervisor_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_manager_page_respects_english_cookie(client, manager_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/manager/absence-requests", headers=_auth_headers(manager_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_change_password_page_respects_english_cookie(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/change-password", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_404_template_respects_english_cookie(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/kindergartens/999999", headers=_auth_headers(admin_token))
    assert response.status_code == 404
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text
