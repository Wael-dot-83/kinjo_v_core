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
