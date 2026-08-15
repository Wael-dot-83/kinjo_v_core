import re
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


def test_setloading_does_not_restore_panels_it_did_not_own():
    """renderChart() calls setLoading(false) from a finally block that runs after
    injectChart() has already drawn the figure. setLoading used to unconditionally
    restore #emptyState (display = on ? 'none' : ''), so every successful render
    put the "start exploring" prompt back on top of the chart that had just been
    drawn and pushed the figure out of view. setLoading may only *hide* panels;
    restoring them belongs to the terminal branches."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "document.getElementById('emptyState').style.display = on ? 'none' : '';" not in html
    assert "chartOutput.style.display = on ? 'none' : '';" not in html
    # showError must bring the prompt back when nothing is plotted, so a failed
    # render never leaves an empty panel behind.
    assert "if (!_currentFigDiv) {" in html


def test_aggregated_series_are_not_drawn_as_a_plotly_histogram():
    """The API's ChartType is a semantic label, not a Plotly trace type. Plotly's
    histogram trace bins its x values and ignores y, so passing pre-aggregated
    rows (one row per governorate with a measure) drew a bar of height 1 for every
    category instead of the measure. histogram is the API's default chart_type for
    the kindergartens source, so this was the out-of-the-box view."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "function cartesianTrace(type, name, xs, ys)" in html
    # The raw semantic type must never reach a cartesian trace spec again.
    assert "traces.push({ type: type," not in html
    # Shapes that need their own data layout get built explicitly.
    assert "type: 'heatmap', x: hx, y: hy, z: z" in html
    assert "type: 'treemap'," in html


def test_chart_is_drawn_into_a_visible_host():
    """Plotly measures the container at newPlot time. setLoading(true) hides
    #chartOutput for the duration of the request, so drawing while it was still
    hidden laid the figure out at Plotly's 700x450 default rather than the panel
    width — the chart filled half its panel. It also must start hidden so its
    min-height is not reserved as blank space under the empty state on load.

    Asserted structurally rather than as one exact line: the element also
    carries role="img"/aria-label now, so a literal match broke on markup that
    still satisfies the contract."""
    html = TEMPLATE.read_text(encoding="utf-8")
    host = html.split('id="chartOutput"', 1)[1].split(">", 1)[0]
    assert 'style="display: none"' in host
    assert "out.style.display = '';" in html


def test_pie_is_honoured_on_two_dimensional_series():
    """A series with two categorical columns and one measure (incidents by type
    per month) takes the grouped branch, which had no pie case — so choosing
    "pie" for incidents or enrollments silently drew grouped bars instead. The
    time dimension is collapsed and the measure shown by category."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "var pieTotals = {};" in html
    assert "pieTotals[g] = (pieTotals[g] || 0) + (r[yCol] || 0);" in html


def test_task_progressbar_has_an_accessible_name():
    """role="progressbar" with only aria-valuenow/min/max exposes no name to a
    screen reader (axe: aria-progressbar-name)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="taskProgressBar"' in html
    bar = html.split('id="taskProgressBar"')[1].split(">")[0]
    assert "aria-label=" in bar


def test_mobile_layout_stretches_children_to_the_viewport():
    """.ce-layout uses align-items:flex-start so the sticky sidebar does not
    stretch in the row layout. When the media query flips it to a column, that
    same value sizes children to their content width instead of the container,
    so the chart card rendered at 423px inside a 342px column and the figure was
    drawn wider than a 390px screen."""
    html = TEMPLATE.read_text(encoding="utf-8")
    mobile = html.split("@media (max-width: 768px)")[1].split("</style>")[0]
    assert "align-items: stretch;" in mobile
    assert ".ce-main {" in mobile


def test_raw_db_enums_are_localised_in_series_labels():
    """Series values arrive as raw enum members (ACTIVE, INJURY, PRESENT) while
    TRANSLATIONS is keyed on Title Case, so they fell through getLocalized and an
    Arabic-first UI showed English identifiers as legend and axis labels."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "const ENUM_TRANSLATIONS = {" in html
    assert "ENUM_TRANSLATIONS[String(key).toUpperCase()]" in html
    for member in ("ACTIVE", "PENDING_REVIEW", "PRESENT", "INJURY", "OTHER", "WAITLISTED"):
        assert f'"{member}":' in html, member


def test_enrollment_labels_match_the_dashboard_i18n_wording():
    """The explorer and the dashboard must name the same enrollment status the
    same way, so the Arabic here tracks dashboard.enrollment_* in the i18n JSON."""
    import json

    html = TEMPLATE.read_text(encoding="utf-8")
    ar = json.loads((ROOT / "static" / "i18n" / "admin_ar.json").read_text(encoding="utf-8"))
    dash = ar["dashboard"]
    for member, key in [
        ("ACTIVE", "enrollment_active"),
        ("PENDING_REVIEW", "enrollment_pending_review"),
        ("WAITLISTED", "enrollment_waitlisted"),
        ("WITHDRAWN", "enrollment_withdrawn"),
    ]:
        assert f'"{dash[key]}"' in html, f"{member} should use {dash[key]!r}"


def test_kpi_cards_are_real_buttons_not_faux_ones():
    """The five KPI strip cards were div[role="button"][tabindex="0"] wired
    with onclick only.

    That combination is focusable and announces itself as a button, so a
    keyboard user reaches it and hears "button" -- then Enter and Space do
    nothing, because a div has no default activation behaviour and the page's
    four keydown listeners covered table sort headers, the two date inputs and
    a Ctrl+Enter shortcut, never these cards. WCAG 2.1.1 (Keyboard).

    A real <button> gets Enter and Space activation from the browser, which is
    why this asserts the element type rather than asserting that some keydown
    handler exists: a handler is a thing to forget, the element type is not.
    """
    html = TEMPLATE.read_text(encoding="utf-8")

    assert '<div class="ce-kpi-strip__card"' not in html, (
        "KPI cards must not be divs; a div cannot be activated by keyboard"
    )
    assert html.count('<button type="button" class="ce-kpi-strip__card"') == 5

    # role/tabindex are redundant on a real button and were only there to prop
    # up the div. Their presence would mean the conversion was half-done.
    for card in re.findall(r'<button[^>]*class="ce-kpi-strip__card"[^>]*>', html):
        assert 'role="button"' not in card, f"redundant role on a button: {card}"
        assert "tabindex=" not in card, f"redundant tabindex on a button: {card}"
        assert "onclick=" not in card, f"card should be wired by delegation: {card}"
        assert "data-source=" in card and "aria-label=" in card

    # Wired by delegation, so the strip can re-render without losing handlers.
    assert "getElementById('kpiStrip')?.addEventListener('click'" in html
    assert ".closest('.ce-kpi-strip__card[data-source]')" in html


def test_kpi_card_button_defaults_are_reset():
    """A <button> centres its text and uses the UA font; the div did neither.
    Without this reset the conversion silently restyles the strip."""
    html = TEMPLATE.read_text(encoding="utf-8")
    rule = re.search(
        r"\.ce-kpi-strip__card\s*\{(?P<body>[^}]*appearance[^}]*)\}", html
    )
    assert rule, "expected a reset rule for the button-based card"
    body = rule.group("body")
    for prop in ("appearance", "font: inherit", "text-align: start", "margin: 0"):
        assert prop in body, f"missing {prop} in the button reset"
