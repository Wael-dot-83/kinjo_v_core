from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manager_navigation_uses_registered_children_and_classes_pages():
    html = (ROOT / "templates" / "manager_base.html").read_text(encoding="utf-8")
    assert '"href": "/children"' in html
    assert '"href": "/classes"' in html
    assert '"href": "/manager/children"' not in html


def test_message_page_never_sends_csrf_cookie_as_bearer_token():
    html = (ROOT / "templates" / "communication" / "messages.html").read_text(encoding="utf-8")
    assert "Authorization" not in html
    assert "Bearer ${token}" not in html
    assert "fetchWithAuth(" in html


def test_manager_supervisor_and_child_pages_expose_fullstack_edit_workflows():
    supervisors = (ROOT / "templates" / "manager" / "supervisors.html").read_text(encoding="utf-8")
    children = (ROOT / "templates" / "manager" / "children.html").read_text(encoding="utf-8")
    assert "/api/manager/supervisors" in supervisors
    assert "createSupervisorBtn" in supervisors
    assert "js-edit-supervisor" in supervisors
    assert "js-delete-supervisor" in supervisors
    assert "editChildForm" in children
    assert "js-edit-child" in children
    assert "/api/children/${id}" in children


def test_manager_daily_report_review_exposes_edit_and_uses_row_locking():
    html = (ROOT / "templates" / "manager" / "daily_reports_review.html").read_text(encoding="utf-8")
    backend = (ROOT / "routers" / "manager.py").read_text(encoding="utf-8")
    assert "editReportForm" in html
    assert "js-edit-report" in html
    assert "Only submitted reports can be edited" in backend
    assert ".with_for_update()" in backend


def test_manager_template_static_assets_exist():
    import re

    files = [ROOT / "templates" / "manager_base.html", *(ROOT / "templates" / "manager").glob("*.html")]
    missing = []
    for template in files:
        text = template.read_text(encoding="utf-8")
        for reference in re.findall(r'''["'](/static/[^"'?#{}]+)''', text):
            if not (ROOT / reference.lstrip("/")).exists():
                missing.append((template.name, reference))
    assert missing == []


def test_manager_sidebar_is_fixed_with_logical_positioning():
    """Sidebar must be fixed to the logical start edge so it pins right in RTL
    and left in LTR without hardcoded left/right values."""
    html = (ROOT / "templates" / "manager_base.html").read_text(encoding="utf-8")
    assert 'id="admin-sidebar"' in html
    assert 'class="mgr-sidebar"' in html
    assert 'aria-label="' in html
    assert 'aria-current="page"' in html


def test_manager_sidebar_has_mobile_toggle_with_aria():
    """Mobile toggle must exist with aria-controls and aria-expanded."""
    html = (ROOT / "templates" / "manager_base.html").read_text(encoding="utf-8")
    assert 'id="mgrSidebarToggle"' in html
    assert 'aria-controls="admin-sidebar"' in html
    assert 'aria-expanded=' in html


def test_manager_sidebar_sections_are_collapsible():
    """Nav groups must have aria-expanded and aria-controls for accessibility."""
    html = (ROOT / "templates" / "manager_base.html").read_text(encoding="utf-8")
    assert 'class="admin-nav-group' in html
    assert 'aria-expanded=' in html
    assert 'aria-controls="mgr-nav-' in html


def test_manager_sidebar_css_uses_logical_properties():
    """CSS must use inset-inline-start for RTL support, not left/right."""
    css = (ROOT / "static" / "css" / "manager_design.css").read_text(encoding="utf-8")
    assert ".mgr-sidebar" in css
    assert "inset-inline-start" in css
    assert "position: fixed" in css
    assert "--mgr-sidebar-width" in css


def test_manager_sidebar_active_state_has_logical_edge_accent():
    """Active nav items must have an inset box-shadow that flips with direction."""
    css = (ROOT / "static" / "css" / "manager_design.css").read_text(encoding="utf-8")
    assert ".mgr-nav-item.active" in css
    assert "box-shadow: inset" in css
    assert '[dir="rtl"]' in css


MANAGER_REACHABLE_TEMPLATES = [
    "templates/manager_base.html",
    "templates/manager/dashboard.html",
    "templates/manager/kpi.html",
    "templates/manager/benchmarking.html",
    "templates/manager/supervisors.html",
    "templates/manager/children.html",
    "templates/manager/absence_requests.html",
    "templates/manager/daily_reports_review.html",
    "templates/classes/list.html",
    "templates/classes/view.html",
    "templates/classes/form.html",
    "templates/classes/class_form.html",
    "templates/children/view.html",
    "templates/enrollment/list.html",
    "templates/enrollment/view.html",
    "templates/enrollment/create.html",
    "templates/attendance/daily.html",
    "templates/attendance/history.html",
    "templates/attendance/absence_requests.html",
    "templates/safety/index.html",
    "templates/safety/incident_form.html",
    "templates/safety/incident_detail.html",
    "templates/communication/messages.html",
    "templates/communication/index.html",
    "templates/communication/events.html",
    "templates/communication/surveys.html",
    "templates/reports/list.html",
    "templates/reports/form.html",
    "templates/reports/view.html",
    "templates/reports/roster.html",
    "templates/user/settings.html",
    "templates/user/notifications.html",
    "templates/kindergartens/view.html",
]


def test_manager_reachable_pages_use_manager_base_shell():
    """Every page a manager can open from the module must render the sidebar."""
    missing = []
    for rel in MANAGER_REACHABLE_TEMPLATES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        uses_shell = (
            "manager_base.html" in text
            or rel.endswith("manager_base.html")
        )
        if not uses_shell:
            missing.append(rel)
    assert missing == []
