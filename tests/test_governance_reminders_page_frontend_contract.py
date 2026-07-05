from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "governance_reminders.html"


def test_dead_breadcrumb_block_removed():
    """14th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_kindergarten_column_relabeled_to_type():
    """The 4th table column was labeled "Kindergarten"/"الحضانة" but the
    row-rendering code has always displayed r.reminder_type (e.g.
    "low_submission_rate"), never a kindergarten name -- relabeled the
    header to match what's actually shown instead of misleading admins
    about what the column represents."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "en' %}Kindergarten{% else %}" not in html
    assert "الحضانة{% endif %}</th>" not in html
    assert "en' %}Type{% else %}" in html
    assert "النوع{% endif %}</th>" in html


def test_governorate_and_missing_reports_read_real_data():
    """Both columns were hardcoded to a literal em-dash placeholder in the
    row-rendering code -- the list endpoint never returned a governorate
    field, and missing-report counts were never computed from the
    per-kindergarten metrics snapshot already stored in payload."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "escHtml(r.governorate || '—')" in html
    assert "function missingReportsFor(r)" in html
    assert "escHtml(missingReportsFor(r))" in html


def test_pagination_is_wired_to_backend_total():
    """GET /api/admin/governance/reminders has always supported page/
    page_size and returned {total, page, page_size, items}, but this page
    called it with no params at all and never read total -- reminders
    beyond the default page size were permanently invisible with no
    indication more existed (matches the already-fixed pagination bug on
    the sister governance-reports page, never ported to this dedicated
    page)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "let logsPage = 1;" in html
    assert "let logsTotal = 0;" in html
    assert "page=${logsPage}&page_size=${LOGS_PAGE_SIZE}" in html
    assert "logsTotal = data.total || 0;" in html
    assert "function renderLogsPagination()" in html


def test_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('<th scope="col"') == 6
