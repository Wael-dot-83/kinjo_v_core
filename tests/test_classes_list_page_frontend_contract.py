from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "classes" / "list.html"
FORM_TEMPLATE = ROOT / "templates" / "classes" / "form.html"


def test_page_does_not_redeclare_global_api_singleton():
    """kinjo-api.js declares its own top-level `const api = new KinJoAPI()`
    (and window.api) as a ready-to-use global. This page (and classes/
    form.html) used to ALSO declare `const api = new KinJoAPI()` inline,
    inside {% block content %} -- which base.html renders BEFORE its own
    later <script src="kinjo-api.js"> tag. Classic <script> tags on one
    page share a single top-level lexical scope for let/const/class, so
    when kinjo-api.js's OWN script tag was later parsed and hit its
    `const api = ...` line, it threw "Identifier 'api' has already been
    declared" -- a SyntaxError that aborts that whole script file,
    including the `class KinJoAPI` declared earlier in it. Net effect:
    KinJoAPI was undefined and NOTHING on this page's JS ever ran, for
    every role, confirmed live via Playwright (typeof KinJoAPI stayed
    "undefined" even after the window 'load' event)."""
    for template in (TEMPLATE, FORM_TEMPLATE):
        html = template.read_text(encoding="utf-8")
        assert "new KinJoAPI()" not in html, template
        assert "const api" not in html, template
        assert "let api" not in html, template


def test_delete_button_branches_by_role():
    """The 'Delete' button always called DELETE /api/classes/{id}, which is
    admin-only (api/classes.py:404 rejects any non-ADMIN with 403) -- a
    manager (who can legitimately reach this shared page) got a 403 on
    every single click, even though a manager-permitted soft-deactivate
    endpoint (PUT /api/classes/{id}/deactivate, with the same active-
    enrollment guard) already existed and had an unused JS wrapper
    (api.deactivateClass) sitting in kinjo-api.js the whole time."""
    html = TEMPLATE.read_text(encoding="utf-8")
    start = html.index("async function deleteClass")
    end = html.index("</script>", start)
    block = html[start:end]
    assert "if (isAdmin) {" in block
    assert "await api.delete(`/api/classes/${id}`);" in block
    assert "await api.deactivateClass(id);" in block


def test_delete_button_label_and_icon_reflect_the_real_action_for_managers():
    """Calling it 'Delete' with a trash icon when the actual backend
    operation only deactivates (reversible, still visible in the list
    with an Inactive badge) would misrepresent what happens for a
    manager clicking it."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "isAdmin ? T('حذف', 'Delete') : T('إلغاء تفعيل', 'Deactivate')" in html
    assert "isAdmin ? 'bi-trash' : 'bi-pause-circle'" in html
