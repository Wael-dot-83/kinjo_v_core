import re

import pytest


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _visible_text(html: str) -> str:
    text = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _assert_english_clean(response, route: str) -> None:
    assert response.status_code in (200, 403, 404), (
        f"Unexpected status for {route}: {response.status_code}"
    )
    assert 'lang="en"' in response.text, f"Missing lang=en on route {route}"
    assert 'dir="ltr"' in response.text, f"Missing dir=ltr on route {route}"

    visible = _visible_text(response.text)
    match = ARABIC_RE.search(visible)
    assert not match, (
        f"Arabic leakage detected in English mode for {route}: "
        f"{visible[max(0, match.start() - 60):match.start() + 120]}"
    )


def _assert_arabic_shell(response, route: str) -> None:
    assert response.status_code in (200, 403, 404), (
        f"Unexpected status for {route}: {response.status_code}"
    )
    assert 'lang="ar"' in response.text, f"Missing lang=ar on route {route}"
    assert 'dir="rtl"' in response.text, f"Missing dir=rtl on route {route}"


@pytest.mark.parametrize("route", ["/login", "/register", "/help", "/privacy", "/terms"])
def test_public_pages_are_english_without_arabic_mix(client, route):
    client.cookies.set("kinjo_lang", "en")
    response = client.get(route, follow_redirects=True)
    _assert_english_clean(response, route)


@pytest.mark.parametrize(
    "route",
    [
        "/",
        "/dashboard",
        "/kindergartens",
        "/classes",
        "/enrollments",
        "/attendance/daily",
        "/reports",
        "/settings",
        "/admin/users",
    ],
)
def test_redirected_login_stays_english_with_persisted_cookie(client, route):
    client.cookies.set("kinjo_lang", "en")
    response = client.get(route, follow_redirects=True)
    _assert_english_clean(response, route)
    assert "Sign in" in response.text


@pytest.mark.parametrize(
    "route",
    [
        "/dashboard",
        "/kindergartens",
        "/classes",
        "/enrollments",
        "/enrollments/create",
        "/attendance/daily",
        "/attendance/history",
        "/reports",
        "/reports/create",
        "/tasks",
        "/safety",
        "/messages",
        "/settings",
        "/notifications",
        "/audit-logs",
        "/admin/dashboard",
        "/admin/users",
        "/admin/users/create",
        "/admin/messages",
        "/admin/messages/compose",
        "/admin/analytics",
        "/admin/analytics/reports",
        "/admin/governance-reports",
        "/admin/classification",
        "/admin/import-kindergartens",
    ],
)
def test_admin_routes_have_zero_arabic_leakage_in_english(
    client, admin_token, sample_kindergarten, sample_class, route
):
    client.cookies.set("kinjo_lang", "en")
    client.cookies.set("kinjo_token", admin_token)
    response = client.get(route, headers=_auth_headers(admin_token), follow_redirects=True)
    _assert_english_clean(response, route)


@pytest.mark.parametrize(
    "route",
    [
        "/dashboard",
        "/kindergartens",
        "/classes",
        "/enrollments",
        "/enrollments/create",
        "/attendance/daily",
        "/attendance/history",
        "/reports",
        "/reports/create",
        "/tasks",
        "/safety",
        "/messages",
        "/settings",
        "/notifications",
        "/manager/benchmarking",
        "/manager/absence-requests",
    ],
)
def test_manager_routes_have_zero_arabic_leakage_in_english(
    client, manager_token, sample_kindergarten, sample_class, route
):
    client.cookies.set("kinjo_lang", "en")
    client.cookies.set("kinjo_token", manager_token)
    response = client.get(route, headers=_auth_headers(manager_token), follow_redirects=True)
    _assert_english_clean(response, route)


@pytest.mark.parametrize(
    "route",
    [
        "/dashboard",
        "/supervisor/dashboard",
        "/attendance/daily",
        "/attendance/history",
        "/reports",
        "/tasks",
        "/safety",
        "/messages",
        "/settings",
        "/notifications",
        "/supervisor/performance",
        "/supervisor/observations",
    ],
)
def test_supervisor_routes_have_zero_arabic_leakage_in_english(
    client, supervisor_token, sample_kindergarten, sample_class, route
):
    client.cookies.set("kinjo_lang", "en")
    client.cookies.set("kinjo_token", supervisor_token)
    response = client.get(route, headers=_auth_headers(supervisor_token), follow_redirects=True)
    _assert_english_clean(response, route)


@pytest.mark.parametrize(
    "route",
    [
        "/dashboard",
        "/parent/dashboard",
        "/parent/profile",
        "/parent/children",
        "/parent/enrollments",
        "/enrollments/create",
        "/settings",
        "/notifications",
    ],
)
def test_parent_routes_have_zero_arabic_leakage_in_english(
    client,
    parent_token,
    parent_user,
    sample_kindergarten,
    sample_child,
    route,
):
    client.cookies.set("kinjo_lang", "en")
    client.cookies.set("kinjo_token", parent_token)
    response = client.get(route, headers=_auth_headers(parent_token), follow_redirects=True)
    _assert_english_clean(response, route)


@pytest.mark.parametrize("route", ["/login", "/register", "/help", "/privacy", "/terms"])
def test_public_pages_render_arabic_shell_by_default(client, route):
    client.cookies.set("kinjo_lang", "ar")
    response = client.get(route, follow_redirects=True)
    _assert_arabic_shell(response, route)
