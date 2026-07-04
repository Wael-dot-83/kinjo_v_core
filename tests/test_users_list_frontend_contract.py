import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USERS_LIST_TEMPLATE = ROOT / "templates" / "admin" / "users" / "list.html"


def test_load_users_sends_backend_recognized_pagination_params():
    """GET /api/admin/users only ever understood page/page_size (see
    admin_endpoints.py::list_users) — it has no "limit" parameter. The
    frontend sent { limit: 100 }, which FastAPI silently ignores, so every
    load fell back to the endpoint's real default (page=1, page_size=25)
    with no way to reach anything past the first 25 users and no
    indication that results were being truncated."""
    source = USERS_LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "const params = { page: currentPage, page_size: PAGE_SIZE };" in source
    assert "const params = { limit: 100 };" not in source


def test_pagination_nav_is_populated_from_the_api_response():
    """<nav id="pagination"> has existed since this page was built but was
    never populated by any script, even though the endpoint has always
    returned a full pagination object (page/page_size/total/total_pages/
    has_next/has_prev)."""
    source = USERS_LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "function renderPaginationControls()" in source
    assert "lastPagination = users.pagination || null;" in source
    assert "renderPaginationControls();" in source
    # Filter/search changes must restart at page 1 since the old page number
    # may no longer exist in the new, differently-sized result set.
    assert "const reloadFromPage1 = () => { currentPage = 1; loadUsers(); };" in source


def test_row_action_buttons_have_per_user_accessible_names():
    """Edit/Reset password/Delete buttons used a generic title ("Edit",
    "Delete") identical across every row despite safeUsername already being
    computed and used elsewhere on the same card (the select checkbox) — a
    screen reader user tabbing through many rows heard "Edit... Edit...
    Edit..." with no way to tell rows apart."""
    source = USERS_LIST_TEMPLATE.read_text(encoding="utf-8")
    for expected in (
        "title=\"${T('تعديل بيانات المستخدم', 'Edit user')} ${safeUsername}\"",
        "title=\"${T('إعادة تعيين كلمة مرور', 'Reset password for')} ${safeUsername}\"",
        "title=\"${T('حذف المستخدم', 'Delete user')} ${safeUsername}\"",
    ):
        assert expected in source, f"missing per-user accessible name: {expected}"


def test_sort_button_exposes_direction_to_assistive_tech():
    """The sort direction indicator (expand_less/expand_more icon glyph) was
    aria-hidden, so a screen-reader user got zero feedback that clicking
    toggled ascending/descending — only the visible icon shape changed."""
    source = USERS_LIST_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r'id="sortDateBtn"\s*\n?\s*aria-label=', source)
    assert "sortBtn.setAttribute('aria-label'" in source


def test_csv_preview_table_has_caption_and_column_scope():
    """The dynamically-built CSV import preview table had <th> with no
    scope="col" and no <caption> at all."""
    source = USERS_LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "<caption class=\"visually-hidden\">" in source
    assert 'scope="col"' in source
