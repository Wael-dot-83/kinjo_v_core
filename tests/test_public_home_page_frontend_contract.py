import re

from dependencies import get_current_user_optional
from main import app


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _visible_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def test_home_page_is_bilingual_and_promotes_primary_actions(client):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/", follow_redirects=True)

    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text
    assert "Open your dashboard" not in response.text
    assert "Create an account" in response.text
    assert "Sign in" in response.text
    assert "See how it works" in response.text

    visible = _visible_text(response.text)
    assert not ARABIC_RE.search(visible)


def test_home_page_shows_dashboard_cta_when_user_is_signed_in(client, admin_user):
    client.cookies.set("kinjo_lang", "en")
    app.dependency_overrides[get_current_user_optional] = lambda: admin_user
    try:
        response = client.get("/", follow_redirects=True)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Copy moved with the Stitch redesign ("Open your dashboard" -> "Go to
    # Dashboard"). What this test is actually for is the rule, not the wording:
    # a signed-in visitor is offered their dashboard and is never invited to
    # create a second account.
    assert "Go to Dashboard" in response.text
    assert "/dashboard" in response.text
    assert "Create an account" not in response.text
    assert "Sign in" not in response.text


def test_home_page_renders_in_arabic_without_english_ctas(client):
    client.cookies.set("kinjo_lang", "ar")
    response = client.get("/", follow_redirects=True)

    assert response.status_code == 200
    assert 'lang="ar"' in response.text
    assert 'dir="rtl"' in response.text
    assert "إنشاء حساب" in response.text
    assert "تسجيل الدخول" in response.text

    # The "شاهد طريقة العمل" CTA no longer exists -- the redesign dropped it.
    #
    # The page also used to ship BOTH languages and hide one with
    # `body.lang-ar .lang-en-content { display: none }`, which is why the
    # English assertions below were failing: the strings were in the source of
    # every Arabic render. CLAUDE.md requires server-side
    # {% if ui_lang == 'en' %} guards, and the switcher does a full page
    # reload, so nothing needed the client-side toggle. With that converted,
    # these assertions test what they always claimed to.
    for english_cta in ("Create an account", "Sign in", "See how it works", "Go to Dashboard"):
        assert english_cta not in response.text, (
            f"{english_cta!r} rendered on the Arabic page -- Arabic is the "
            f"default language and the page must not ship English copy it hides"
        )
