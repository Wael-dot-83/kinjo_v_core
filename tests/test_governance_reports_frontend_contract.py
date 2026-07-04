import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_TEMPLATE = ROOT / "templates" / "admin" / "governance_reports.html"
GOVERNANCE_JS = ROOT / "static" / "js" / "admin_governance.js"


def test_no_fictitious_cyberlume_classes_remain():
    """Every card container (12 occurrences), the refresh button, and both
    data tables on this page used an invented "cyberlume" class prefix that
    was never defined in any CSS file in the repository (confirmed via
    git log --all -S over every .css file). Cards had zero real Bootstrap
    class alongside it, so they rendered with no background/border/shadow
    at all; the refresh button had no real Bootstrap variant class, so it
    rendered with a transparent background."""
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert "cyberlume" not in html
    # Cards must use the real, defined admin-card class instead
    assert html.count('class="admin-card') >= 10
    assert 'class="btn btn-primary btn-sm"' in html


def test_no_undefined_tailwind_position_classes_remain():
    """Three chart-wrapper divs used Tailwind's "relative z-10" utility
    syntax; Tailwind is never loaded on this page or in admin_base.html, so
    neither class did anything — Chart.js's documented responsive-sizing
    pattern requires a positioned parent, which these divs never had."""
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert "relative z-10" not in html
    assert html.count("position-relative") >= 3


def test_row_grids_have_bootstrap_column_classes():
    """Two <div class="row"> containers (the 4 KPI cards, and the funnel
    chart / time metrics pair) had bare <div> children with no col-*
    class. Bootstrap's .row is display:flex with negative margins expecting
    .col children for width/padding — bare divs don't distribute into the
    intended grid and have no responsive stacking breakpoint."""
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert html.count('<div class="col-6 col-md-3">') == 4
    assert html.count('<div class="col-md-6">') >= 2


def test_charts_have_accessible_text_alternatives():
    """funnelChart and trendChart <canvas> elements had no role="img" and no
    aria-label — bare canvases with no text alternative, a regression
    against the pattern already established on the analytics dashboard and
    daily-reports pages in this same codebase."""
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r'<canvas id="funnelChart"[^>]*role="img"[^>]*aria-label="', html)
    assert re.search(r'<canvas id="trendChart"[^>]*role="img"[^>]*aria-label="', html)


def test_both_tables_have_caption_and_column_scope():
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert html.count('<caption class="visually-hidden">') == 2
    assert html.count('scope="col"') == 20  # 15 leaderboard + 5 reminders columns


def test_reminder_button_has_per_kindergarten_accessible_name():
    """The icon-only leaderboard reminder button already had
    data-target-name available but its title was a static, non-row-specific
    string ("Send reminder") repeated identically for every kindergarten."""
    js = GOVERNANCE_JS.read_text(encoding="utf-8")
    assert "${governanceText('إرسال تذكير إلى', 'Send reminder to')} ${kgName}" in js


def test_reminders_pagination_uses_backend_support_instead_of_hardcoded_page():
    """GET /api/admin/governance/reminders has always supported page/page_size
    and returned {total, page, page_size, items}, but the frontend called it
    with a hardcoded page=1&page_size=10 on every refresh and never read
    `total` — only the 10 most recent reminders were ever visible with no
    indication more existed, the same bug class as the Users page's dead
    pagination."""
    js = GOVERNANCE_JS.read_text(encoding="utf-8")
    assert "governanceFetch(`/api/admin/governance/reminders?page=${remindersPage}&page_size=${REMINDERS_PAGE_SIZE}`)" in js
    assert "function renderRemindersPagination()" in js
    assert "remindersTotal = reminders.total || 0;" in js

    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="remindersPagination"' in html
