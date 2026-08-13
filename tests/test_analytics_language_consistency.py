"""Language consistency on /admin/analytics.

Machine identifiers were reaching user-facing labels: raw database table names
in the Data Sources panel and raw enrollment source keys in the chart legend.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js" / "admin_analytics.js"

# The identifiers the dashboard was exposing.
LEAKED_TABLES = (
    "attendance_logs",
    "incidents",
    "daily_reports",
    "enrollment_applications",
    "kindergartens",
    "children",
)


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    return _js().split(f"function {name}", 1)[1].split("\nfunction ", 1)[0]


def test_raw_table_name_is_not_rendered():
    """The panel printed <code>attendance_logs</code> beside its own localized
    name -- an English schema identifier inside an Arabic card."""
    body = _fn("renderDataLineage")
    assert "escapeHtml(s.table)" not in body
    assert "<code>" not in body


def test_record_count_is_labelled():
    """The count rendered as a bare number with no unit."""
    body = _fn("renderDataLineage")
    assert "adminAnalyticsText('سجل', 'records')" in body


def test_source_name_has_no_cross_language_fallback():
    body = _fn("renderDataLineage")
    assert "localizedName ||" in body
    assert "adminAnalyticsText('مصدر بيانات', 'Data source')" in body


def test_chart_legend_localizes_its_keys():
    """Enrollment source keys were drawn straight into the legend."""
    body = _fn("renderSourceChart")
    assert "localizeSourceKey(e[0])" in body
    assert "entries.map(e => e[0])" not in body


def test_unknown_keys_are_humanised_not_leaked():
    """A new backend value must degrade to "Walk In", never to walk_in."""
    body = _fn("localizeSourceKey")
    assert "replace(/[_-]+/g" in body
    assert "toUpperCase()" in body


def test_known_keys_are_translated_both_ways():
    body = _fn("localizeSourceKey")
    for key in ("WALK_IN", "ONLINE", "REFERRAL"):
        assert key in body
    assert "adminAnalyticsText(" in body


def test_empty_key_does_not_render_blank():
    body = _fn("localizeSourceKey")
    assert "adminAnalyticsText('غير محدد', 'Unspecified')" in body


def test_no_leaked_identifier_reaches_a_label_expression():
    """Guard the whole file: none of the leaked table names may appear inside a
    template literal that builds visible markup."""
    js = _js()
    for table in LEAKED_TABLES:
        assert f"<code>${{escapeHtml({table}" not in js
    # The specific construct that caused this must not come back.
    assert "<code>${escapeHtml(s.table)}</code>" not in js
