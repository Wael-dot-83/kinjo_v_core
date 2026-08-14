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
    pattern requires a positioned parent, which these divs never had.

    Asserts the property that matters -- every chart canvas has a positioned
    parent -- rather than a count of `position-relative`. The count was three
    when three wrappers existed; the governance redesign moved one onto a
    non-chart panel and left #trendChart in a bare `card-body`, which the count
    could not distinguish from a legitimate layout change.
    """
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    assert "relative z-10" not in html
    for canvas_id in ("funnelChart", "trendChart"):
        m = re.search(rf'<canvas id="{canvas_id}"', html)
        assert m, f"{canvas_id} canvas not found"
        # The nearest enclosing element opened before the canvas must be positioned.
        opening = html.rfind("<div", 0, m.start())
        wrapper = html[opening:m.start()]
        assert "position-relative" in wrapper, (
            f"{canvas_id} has no positioned parent; Chart.js responsive sizing "
            f"needs one. Wrapper was: {wrapper.strip()[:120]}"
        )


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


def test_every_table_has_caption_and_column_scope():
    """One caption per table, and column headers scoped.

    Was pinned to `== 2` captions and `== 20` scope="col". The governance
    redesign split the leaderboard into prioritized and improvement tables, so
    the page legitimately has three; hardcoded totals failed on a correct
    change while saying nothing about whether the new table was accessible.
    Tie the assertion to the number of tables instead.
    """
    html = GOVERNANCE_TEMPLATE.read_text(encoding="utf-8")
    tables = html.count("<table")
    assert tables >= 2
    assert html.count('<caption class="visually-hidden">') == tables
    # Every table needs scoped column headers; 5 is the smallest table here.
    assert html.count('scope="col"') >= tables * 5


def test_reminder_button_has_per_kindergarten_accessible_name():
    """The icon-only leaderboard reminder button already had
    data-target-name available but its title was a static, non-row-specific
    string ("Send reminder") repeated identically for every kindergarten.

    Asserts the name is row-specific and bilingual, not one exact wording. The
    redesign reworded it to "Send governance reminder to", which is still
    per-row and still correct -- pinning the sentence made a copy edit look
    like an accessibility regression.
    """
    js = GOVERNANCE_JS.read_text(encoding="utf-8")
    m = re.search(r'title="\$\{governanceText\(([^)]*)\)\}\s*\$\{kgName\}"', js)
    assert m, (
        "the reminder button's title must be composed with ${kgName} so each "
        "row gets its own accessible name"
    )
    args = m.group(1)
    assert "'" in args and "," in args, f"title must be bilingual, got: {args}"


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
