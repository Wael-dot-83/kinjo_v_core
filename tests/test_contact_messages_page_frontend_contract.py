from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "contact_messages.html"


def test_table_has_caption_and_column_scope():
    """The contact-messages table had no <caption> and no scope="col" on
    any of its 7 <th> elements."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 7


def test_nullable_phone_and_subject_do_not_render_as_literal_none():
    """ContactMessage.phone and .subject are both nullable columns with no
    Jinja `finalize` configured anywhere in the app, so {{ msg.phone }}
    rendered the literal string "None" for messages submitted without a
    phone number, and {{ msg.subject }} did the same for a blank subject
    (both in the table row and the modal title)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{{ msg.phone or '—' }}" in html
    assert "{{ msg.subject or '—' }}" in html


def test_view_modal_has_dialog_aria_semantics():
    """The view-message modal had no aria-labelledby/aria-modal/role at
    all, unlike this codebase's own established modal pattern (e.g.
    templates/admin/impersonate.html)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'aria-labelledby="msgModalLabel{{ msg.id }}"' in html
    assert 'aria-modal="true"' in html
    assert 'role="dialog"' in html
    assert 'id="msgModalLabel{{ msg.id }}"' in html


def test_row_action_buttons_have_per_message_accessible_names():
    """The resolve/view buttons relied on an identical `title` for every
    row ("Close message"/"View message"), giving every row's controls the
    same accessible name with no way to tell which message they act on."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "aria-label=\"{% if ui_lang == 'en' %}Close message from {{ msg.name }}" in html
    assert "aria-label=\"{% if ui_lang == 'en' %}View message from {{ msg.name }}" in html


def test_pagination_links_urlencode_the_search_query():
    """Pagination hrefs interpolated filters.q directly into the URL
    without encoding, so a search term containing "&", "#", or "%"
    corrupted the resulting query string when a pagination link was
    clicked."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{{ (filters.q or '') | urlencode }}" in html
    assert "{{ (filters.status_filter or '') | urlencode }}" in html


def test_resolve_error_handler_reads_the_real_error_schema():
    """The resolve action's error handler read payload.detail, but this
    endpoint's errors are all APIError-typed and serialize to
    {"error": {"code", "message", ...}} via api_error_handler -- there is
    no top-level `detail` key, so admins always saw the generic fallback
    message regardless of the real failure reason."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "payload.error?.message" in html
