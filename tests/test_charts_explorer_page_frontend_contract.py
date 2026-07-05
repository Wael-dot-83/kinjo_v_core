from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"


def test_route_supplies_sources_and_chart_types(client, auth_headers_admin):
    """The route rendering this page never passed sources/chart_types into
    the template context, so both <select id="sourceSelect"> and
    <select id="chartTypeSelect"> rendered with zero real options (Jinja's
    default lenient Undefined silently renders an empty loop, no error).
    Clicking "Render Chart" then sent source="" to /admin/charts/render,
    which 422s on an invalid empty source -- the page's entire core
    feature was unusable via this route (a second, unlinked route at
    /admin/charts/dashboard happened to supply this context correctly,
    which is why the bug wasn't caught by that route's own test)."""
    resp = client.get("/admin/analytics/charts", headers=auth_headers_admin)
    assert resp.status_code == 200
    html = resp.text
    for source in ("incidents", "attendance", "daily_reports", "enrollments", "kindergartens"):
        assert f'value="{source}"' in html
    for chart_type in ("line", "bar", "scatter", "pie", "histogram"):
        assert f'value="{chart_type}"' in html


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
