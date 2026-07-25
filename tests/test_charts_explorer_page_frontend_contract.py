from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"


def test_route_supplies_sources_and_chart_types(client, auth_headers_admin):
    """Verify that the backend passes all 5 data sources and all 9 chart types
    into the template context so the source-card grid and chart-type selector
    render fully populated (no silent empty-Jinja-loop bug)."""
    resp = client.get("/admin/analytics/charts", headers=auth_headers_admin)
    assert resp.status_code == 200
    html = resp.text
    for source in ("incidents", "attendance", "daily_reports", "enrollments", "kindergartens"):
        assert f'data-source="{source}"' in html
    for chart_type in ("line", "bar", "scatter", "pie", "histogram"):
        assert f'data-ct="{chart_type}"' in html


def test_dead_breadcrumb_block_removed():
    """11th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_plotly_loads_from_local_vendor_file_not_a_blocked_cdn():
    """cdn.plot.ly is not in this site's CSP script-src allowlist
    (middleware/security.py only permits jsdelivr/cdnjs/unpkg) -- the CDN
    <script> tag was therefore blocked by the browser on every single page
    load, always falling through to the local vendor copy via a
    document.write fallback. Removed the always-failing CDN attempt and
    its fallback-detection script; load the local file directly."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "https://cdn.plot.ly" not in html
    assert 'src="/static/vendor/plotly-2.35.2.min.js"' in html


def test_share_chart_has_clipboard_fallback_for_non_secure_contexts():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "navigator.clipboard && window.isSecureContext" in html
    assert "document.execCommand('copy')" in html


def test_drilldown_is_scoped_to_kindergartens_source():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "if (_currentSource !== 'kindergartens') return;" in html
    assert "data.source === 'kindergartens' && data.drilldown" in html
