from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "daily_reports.html"


def test_chart_data_reads_real_backend_field_names():
    """The two report-detail doughnut charts read metrics.by_type/
    metrics.by_severity, which don't exist on the real response --
    report_service.py's generate_incident_report() returns
    incidents_by_type/incidents_by_severity. Both charts silently never
    rendered on any report, with no console error and no visible
    fallback message (typeLabels.length/sevLabels.length were always 0)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "metrics.by_type" not in html
    assert "metrics.incidents_by_type" in html
    assert "metrics.by_severity" not in html
    assert "metrics.incidents_by_severity" in html


def test_kindergarten_and_governorate_filters_are_populated_and_toggled():
    """#kindergartenFilter/#governorateFilter were hardcoded disabled with
    only a placeholder option and no populate function or scope-change
    listener at all -- choosing "Specific Kindergarten" or "Governorate"
    in the Scope dropdown did nothing, so those two filters could never
    actually be set despite the UI implying they could."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "async function loadGovernorates()" in html
    assert "async function loadKindergartens()" in html
    assert "getElementById('scopeFilter').addEventListener('change'" in html
    assert "kgFilter.disabled = scope !== 'KINDERGARTEN';" in html
    assert "govFilter.disabled = scope !== 'GOVERNORATE';" in html


def test_no_fictitious_tailwind_classes_remain():
    """This page was authored with Tailwind utility classes (bg-surface-
    container/50, text-on-surface-variant, font-label-sm, rounded-2xl,
    shadow-[...], grid grid-cols-1 md:grid-cols-2, etc.) on a site that
    only loads Bootstrap 5.3 -- none of these classes have any CSS
    definition anywhere, confirmed via repo-wide grep against static/css."""
    html = TEMPLATE.read_text(encoding="utf-8")
    for fictitious in (
        "text-on-surface", "bg-surface-container", "font-label",
        "text-body-md", "text-label-sm", "border-white/", "rounded-2xl",
        "rounded-xl", "relative z-10", "group-hover", "grid-cols",
        "w-full", "shadow-[",
    ):
        assert fictitious not in html, f"fictitious class residue: {fictitious}"


def test_per_kindergarten_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('<th scope="col">') == 2


def test_modal_divs_are_balanced():
    """The outer .modal wrapper (id="reportModal") was missing its closing
    </div> -- only .modal-dialog and .modal-content were closed."""
    html = TEMPLATE.read_text(encoding="utf-8")
    import re
    opens = len(re.findall(r"<div\b", html))
    closes = len(re.findall(r"</div>", html))
    assert opens == closes, f"unbalanced divs: {opens} opens vs {closes} closes"
