import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERTS_TEMPLATE = ROOT / "templates" / "admin" / "alerts.html"
ALERTS_JS = ROOT / "static" / "js" / "admin_alerts.js"


def test_table_has_caption_and_column_scope():
    """The alerts table had no <caption> and no scope="col" on any of its 9
    <th> elements."""
    html = ALERTS_TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 9


def test_view_button_has_per_alert_accessible_name():
    """Every row's "View" button had the exact same accessible name across
    every alert, with no aria-label distinguishing which alert it opens."""
    js = ALERTS_JS.read_text(encoding="utf-8")
    match = re.search(r'data-action="view" data-alert-id="\$\{a\.id\}"\s*\n?\s*aria-label="([^"]+)"', js)
    assert match, "no aria-label found on the View button"
    assert "a.metric" in match.group(1) or "metric" in match.group(1)


def test_status_filter_defaults_to_no_filter_not_active_only():
    """GET /api/admin/alerts previously defaulted status to "ACTIVE" when the
    parameter was omitted. The frontend's "All Statuses" option (value="")
    omits the param entirely to mean "no filter", exactly like severity and
    governorate — but unlike those two (which default to None), a non-None
    default on status silently forced every "All Statuses" request back to
    ACTIVE-only. RESOLVED/ACKNOWLEDGED alerts could never be surfaced
    through that control despite the option text promising otherwise."""
    import inspect
    import admin_endpoints
    sig = inspect.signature(admin_endpoints.get_admin_alerts)
    for name in ("status", "severity", "governorate"):
        query_default = sig.parameters[name].default
        actual_default = getattr(query_default, "default", query_default)
        assert actual_default is None, (
            f"{name} query param must default to None (no filter) so omitting "
            f"it behaves like the 'All ___' option promises; got {actual_default!r}"
        )
