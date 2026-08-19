import re

from dependencies import get_current_user_optional
from main import app


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _visible_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def test_home_page_is_bilingual_and_promotes_primary_actions(client):
    """An anonymous English visitor is offered sign-in and account creation.

    This asserts the RULE, not a particular marketing phrase, because the
    wording has now moved twice. It previously pinned "Create an account" /
    "Sign in" / "See how it works"; the Stitch redesign ships "Login",
    "Register" and "Sign in to Platform", and dropped the how-it-works CTA
    entirely -- a fact the Arabic test below had already recorded while this
    one was left asserting the old strings. Pinning exact copy in two places
    that drift apart is how a contract stops describing the product.

    What must stay true: both primary actions are reachable, a signed-out
    visitor is not offered a dashboard, and an English render ships no Arabic.
    """
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/", follow_redirects=True)

    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text

    # A signed-out visitor is never offered a dashboard.
    for signed_in_only in ("Open your dashboard", "Go to Dashboard"):
        assert signed_in_only not in response.text

    # Both primary actions are present, however they are currently worded.
    assert "Register" in response.text, "no account-creation action on the English home page"
    assert "Sign in to Platform" in response.text or "Login" in response.text, (
        "no sign-in action on the English home page"
    )

    # The English render must not ship Arabic copy it hides.
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
    # Both primary actions, in Arabic. Wording is the redesign's ("حساب جديد"
    # for account creation, where this test previously pinned "إنشاء حساب");
    # the rule is that both actions are offered in the page's own language.
    assert "حساب جديد" in response.text, "no account-creation action on the Arabic home page"
    assert "تسجيل الدخول" in response.text, "no sign-in action on the Arabic home page"

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
