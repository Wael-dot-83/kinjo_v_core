"""التنبيهات النشطة (Active Alerts) card on /admin/analytics.

The card could contradict itself: a stale count badge beside an empty state, and
a badge total that disagreed with the number of rows drawn.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"


def _renderer() -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.split("window._renderAlertItems = function", 1)[1].split("\n  /* ──", 1)[0]


def test_badge_is_reset_before_the_empty_return():
    """The badge used to be written after an early return, so clearing the
    alerts left the old count in red next to "no active alerts"."""
    body = _renderer()
    badge_at = body.index("badge.textContent")
    empty_at = body.index("if (!items.length)")
    assert badge_at < empty_at, "badge must be updated before the empty-state return"


def test_badge_hides_itself_at_zero():
    body = _renderer()
    assert "classList.toggle('d-none', items.length === 0)" in body


def test_hidden_alerts_are_disclosed():
    """The badge counts every alert but only six render; the difference has to
    be visible or the header looks wrong."""
    body = _renderer()
    assert "const hidden = items.length - SHOWN" in body
    assert "تنبيهات أخرى" in body and "more" in body


def test_no_cross_language_fallback():
    """Falling back to the English string when the Arabic one is missing is the
    language mixing this interface must not do."""
    body = _renderer()
    assert "تنبيه بدون ترجمة" in body
    assert "Alert not translated" in body
    # The old unconditional fallback chain must be gone.
    assert "(a.message_ar || a.message || '')" not in body
    assert "(a.message_en || a.message || '')" not in body


def test_severity_uses_exact_values_not_substrings():
    """`sev.includes('high')` matched unrelated values such as "highlight"."""
    body = _renderer()
    assert ".includes('high')" not in body
    assert ".includes('critical')" not in body
    assert "sev === 'critical'" in body and "sev === 'high'" in body


def test_severity_reads_an_explicit_field_first():
    body = _renderer()
    assert "a.severity || a.priority" in body


def test_non_array_payload_cannot_throw():
    """A null or object payload previously reached .length/.slice."""
    body = _renderer()
    assert "Array.isArray(alerts)" in body


def test_alert_text_is_escaped():
    assert "esc(msg)" in _renderer()


def test_decorative_icon_is_hidden_from_screen_readers():
    body = _renderer()
    assert 'aria-hidden="true"' in body


def test_empty_state_is_single_language():
    """The empty state chose its language from a different expression than the
    rows did."""
    body = _renderer()
    empty = body.split("if (!items.length)", 1)[1].split("return;", 1)[0]
    assert "isAr ?" in empty
    assert "window.KINJO_LANG === 'en'" not in empty
