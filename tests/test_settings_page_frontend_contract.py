import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE_TEMPLATE = ROOT / "templates" / "admin_base.html"
ADMIN_COMPONENTS_JS = ROOT / "static" / "js" / "admin_components.js"
SETTINGS_TEMPLATE = ROOT / "templates" / "admin" / "settings.html"


def test_session_timeout_meta_tag_is_emitted():
    """admin_components.js's client-side auto-logout timer has always read
    <meta name="session-timeout-minutes"> (with a documented "falls back to
    30 if not present" comment), but admin_base.html never emitted that tag
    anywhere. The timer silently hardcoded 30 minutes regardless of the real
    configured SESSION_TIMEOUT_MINUTES, disagreeing with server-side
    enforcement (dependencies.py) whenever an operator changes it away from
    the default — exactly the kind of value the Settings page itself
    displays as if it were authoritative."""
    js = ADMIN_COMPONENTS_JS.read_text(encoding="utf-8")
    assert 'meta[name="session-timeout-minutes"]' in js

    base_html = ADMIN_BASE_TEMPLATE.read_text(encoding="utf-8")
    # Match the tag structurally rather than as one exact line. The previous
    # pattern required `<meta name="..." content="..."` with single spaces, so it
    # broke the moment a formatter wrapped the attributes onto their own lines —
    # reporting "tag is not emitted" while admin_base.html emitted it correctly.
    # Attribute order and whitespace are not part of this contract; the tag being
    # present and fed from the Jinja global is.
    meta_tag = re.search(r'<meta\b[^>]*name="session-timeout-minutes"[^>]*>', base_html)
    assert meta_tag, "session-timeout-minutes meta tag is not emitted in admin_base.html"
    content = re.search(r'content="([^"]+)"', meta_tag.group(0))
    assert content, "session-timeout-minutes meta tag has no content attribute"
    assert "session_timeout_minutes" in content.group(1)


def test_settings_page_and_meta_tag_read_the_same_source_of_truth():
    """Both the visible Settings-page value and the meta tag consumed by the
    JS timer must derive from the same Jinja global (session_timeout_minutes,
    set once in frontend.py from settings.SESSION_TIMEOUT_MINUTES) rather
    than one of them drifting to a hardcoded literal."""
    settings_html = SETTINGS_TEMPLATE.read_text(encoding="utf-8")
    base_html = ADMIN_BASE_TEMPLATE.read_text(encoding="utf-8")
    assert "session_timeout_minutes" in settings_html
    assert "session_timeout_minutes" in base_html
