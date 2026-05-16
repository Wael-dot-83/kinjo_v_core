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


def test_login_respects_english_cookie_direction(client):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/login")
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_dashboard_respects_cookie_language(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/dashboard", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text


def test_reports_page_renders_english_shell_when_cookie_is_en(client, supervisor_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/reports", headers=_auth_headers(supervisor_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert "Daily Reports" in response.text
    assert "Create New Report" in response.text


def test_manager_absence_requests_page_renders_english_shell_when_cookie_is_en(client, manager_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/manager/absence-requests", headers=_auth_headers(manager_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert "Review Absence Requests" in response.text
    assert "Under Review" in response.text


def test_change_password_page_renders_english_when_cookie_is_en(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/change-password", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text
    assert "Change Password" in response.text
    assert "Current password" in response.text
    assert "Confirm new password" in response.text


def test_404_template_respects_english_cookie(client, admin_token):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/kindergartens/999999", headers=_auth_headers(admin_token))
    assert response.status_code == 404
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text
    assert "Page not found" in response.text
    assert "Back to Dashboard" in response.text
