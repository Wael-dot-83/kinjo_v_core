import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KG_OVERVIEW_TEMPLATE = ROOT / "templates" / "admin" / "kg_overview.html"
KG_OVERVIEW_JS = ROOT / "static" / "js" / "kg_overview.js"
KG_OVERVIEW_CSS = ROOT / "static" / "css" / "kg_overview.css"


def test_kinjo_lang_assignment_is_not_html_escaped():
    """window.KINJO_LANG = {{ '"en"' if ... else '"ar"' }} was silently
    HTML-entity-escaped by Jinja2's autoescape into
    `window.KINJO_LANG = &#34;ar&#34;;` — literal HTML entities inside a
    <script> block are not decoded, so this was a hard JavaScript syntax
    error ("Unexpected token '&'") on every single load of this page,
    confirmed via a live pageerror listener. Because it's a *separate*
    <script> tag from kg_overview.js, the deferred external script still
    ran — but window.KINJO_LANG was left undefined, and this file's own
    `window.KINJO_LANG || 'ar'` fallback pattern meant English-mode users
    silently got Arabic-formatted content everywhere on this page."""
    html = KG_OVERVIEW_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"window\.KINJO_LANG = (.+?);", html)
    assert match, "could not find the KINJO_LANG assignment"
    assert "| safe" in match.group(1)


def test_kg_overview_occupancy_reads_the_real_backend_field():
    """mapOverviewPayload read kg.occupancy_rate, which the backend
    (GET /api/admin/kg-overview) has never sent — only capacity_utilization,
    an already-computed real percentage. occupancy was always 0, so
    `capacity` always fell through to `children` itself, making every
    kindergarten's occupancy display compute as children/children = 100%
    regardless of real enrollment vs. real capacity."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "Number(kg.capacity_utilization ?? kg.occupancy_rate ?? 0)" in js


def test_kpi_card_hide_toggle_has_a_matching_css_rule():
    """kg_overview.js toggles .ko-hidden on .ko-kpi-card elements from the
    "Customize Components" drawer, but the only .ko-hidden rule in the
    stylesheet was scoped to .ko-data-panel — toggling a KPI off was a
    silent no-op, the card never actually disappeared."""
    css = KG_OVERVIEW_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.ko-kpi-card\.ko-hidden\s*\{\s*display:\s*none;\s*\}", css)


def test_pagination_button_css_variables_are_defined():
    """.ko-pg-btn:hover/.active referenced --ko-primary and --ko-surface-alt,
    neither of which was ever defined anywhere — the active/hover page
    indicator rendered with no background or border color at all."""
    css = KG_OVERVIEW_CSS.read_text(encoding="utf-8")
    assert "var(--ko-primary)" not in css
    assert "var(--ko-surface-alt)" not in css
    assert "var(--ko-blue)" in css


def test_table_has_caption_and_keyboard_accessible_sortable_headers():
    """The kindergarten table had no <caption>, no scope="col", and its
    sortable <th> elements only responded to mouse click (no tabindex, no
    keydown, no aria-sort) — keyboard users could not sort it at all, and
    the `th` argument passed into #sortTable was never actually used."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "<caption class=\"visually-hidden\">" in js
    assert 'scope="col"' in js
    assert 'tabindex="0"' in js
    assert 'aria-sort="none"' in js
    assert "th.addEventListener('keydown'" in js
    assert "th.setAttribute('aria-sort'" in js


def test_kg_rows_and_cards_are_keyboard_operable():
    """Table rows and card-grid items only opened the detail panel via a
    mouse click handler — no tabindex, no role, no keydown — despite the
    KPI cards on this exact same page already correctly implementing
    role="button" tabindex="0" plus an Enter/Space handler."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert js.count('role="button" tabindex="0"') >= 2  # kpi cards + kg cards
    assert re.search(r'ko-kg-card"[^`]*role="button" tabindex="0"', js)
    assert "row.addEventListener('keydown'" in js
    assert "card.addEventListener('keydown'" in js


def test_period_change_triggers_a_real_data_refetch():
    """Clicking a period button (Today/Week/Month) used to call
    #onFilterChange(), which only re-rendered already-fetched data and never
    called #loadOverviewData() again — even though `period` genuinely
    changes the server-side attendance date window. The new period had no
    visible effect until the next manual refresh or 60s auto-poll."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "this.#onPeriodChange();" in js
    assert "async #onPeriodChange()" in js
    match = re.search(r"async #onPeriodChange\(\)\s*\{(?P<body>.*?)\n  \}", js, re.DOTALL)
    assert match
    assert "#loadOverviewData()" in match.group("body")


def test_alert_action_buttons_have_per_alert_accessible_names():
    """View/Dismiss buttons in the Smart Alerts list had no aria-label at
    all — just generic visible text ("View"/"Dismiss") identical across
    every alert, despite the alert's own title and kindergarten name
    already being available at render time."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "aria-label=\"${isAr ? 'عرض' : 'View'} — ${koEscape(a.title)}" in js
    assert "aria-label=\"${isAr ? 'تجاهل' : 'Dismiss'} — ${koEscape(a.title)}" in js


def test_no_duplicate_manage_kindergartens_button_in_template():
    """A stray centered `btn btn-primary btn-lg` "Manage Kindergartens"
    button was rendered in the middle of the page, duplicating the toolbar
    quick-action of the same name. The template must not reintroduce it —
    the single Manage-KGs action lives in the JS quick-action bar."""
    html = KG_OVERVIEW_TEMPLATE.read_text(encoding="utf-8")
    assert "btn btn-primary btn-lg" not in html
    assert "Manage Kindergartens" not in html
    assert "إدارة الحضانات" not in html


def test_manage_kg_quick_action_links_to_management_page():
    """The "Manage KGs / إدارة الحضانات" quick action pointed at
    /admin/heatmap instead of the kindergarten management page."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "/admin/heatmap" not in js
    assert "href:'/admin/kindergartens'" in js


def test_overview_section_header_is_not_a_duplicate_of_page_title():
    """The JS-rendered section header repeated the page H1
    ("نظرة عامة على الحضانات"), showing the same title twice. It must be a
    distinct label."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "نظرة عامة على الحضانات" not in js
    assert "أداء الحضانات" in js


def test_add_child_button_removed_from_admin_quick_actions():
    """The 'Add Child' / 'إضافة طفل' action has been removed from the admin overview page."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "إضافة طفل" not in js
    assert "/enroll" not in js

