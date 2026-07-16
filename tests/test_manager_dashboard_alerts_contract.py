"""The manager dashboard must render the `alerts` payload the API sends it.

`/api/manager/dashboard` returns an `alerts` list (licence expiry, pending
applications, pending reports), each entry bilingual (`message_ar`/`message_en`) with
a `priority` — see `api/manager.py`. The page read only `classes_without_supervisor`
and `classes_near_capacity`, so every one of those alerts was computed and thrown
away, and the all-clear banner was keyed off the two class lists alone.

Verified in a real browser on 2026-07-16 against a kindergarten whose licence expired
5 days earlier, with classes fully staffed and under capacity:

    before: #alertsAllClear visible -> True   ("No operational alerts — everything
            looks good.") while the licence had lapsed
    after : #alertsAllClear hidden; #alertsFromApi renders
            'انتهت صلاحية الترخيص منذ 5 يوم'

`tests/test_manager_license_alerts.py` covers the API side and passed throughout — the
payload was always correct. Nothing asserted anyone displayed it, which is the gap
this file closes.

These are source-level assertions because the suite has no browser harness; they
follow the existing `test_*_frontend_contract.py` convention. They pin the wiring, not
the rendering — the rendering was verified by hand in the browser, as recorded above.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER_DASHBOARD = ROOT / "templates" / "manager" / "dashboard.html"


def _html() -> str:
    return MANAGER_DASHBOARD.read_text(encoding="utf-8")


def test_template_exists():
    """Guards every assertion below: a moved template would make them vacuous."""
    assert MANAGER_DASHBOARD.is_file(), f"{MANAGER_DASHBOARD} is missing"


def test_dashboard_reads_the_alerts_payload():
    """The licence-expiry alert reaches the page only if something reads d.alerts."""
    html = _html()
    assert "d.alerts" in html, (
        "manager/dashboard.html never reads `d.alerts`, so every alert "
        "/api/manager/dashboard computes — including an expired licence — is "
        "silently discarded."
    )


def test_dashboard_renders_alerts_into_a_container():
    html = _html()
    assert 'id="alertsFromApi"' in html, (
        "no container for the API's alerts; reading d.alerts without rendering it "
        "changes nothing."
    )


def test_all_clear_banner_accounts_for_api_alerts():
    """The actual defect: a lapsed licence rendered a green 'everything looks good'.

    The all-clear banner must not be keyed off the two class lists alone.
    """
    html = _html()
    assert "noSup.length || nearCap.length || extra.length" in html, (
        "#alertsAllClear is computed without the API's alerts, so a kindergarten "
        "with an expired licence but no supervisor/capacity gaps shows "
        "'No operational alerts — everything looks good.'"
    )


def test_alert_text_is_bilingual_not_the_english_only_alias():
    """`message` is the English-only compatibility alias (api/manager.py). An
    Arabic-primary UI must prefer message_ar/message_en."""
    html = _html()
    assert "a.message_ar" in html and "a.message_en" in html, (
        "alert text must come from the bilingual message_ar/message_en fields; "
        "`message` is an English-only compatibility alias and would show English "
        "text to Arabic users."
    )
