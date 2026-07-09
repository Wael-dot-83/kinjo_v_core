from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_TEMPLATE = ROOT / "templates" / "admin" / "messages" / "list.html"
# The legacy frontend route bodies now live in the compat module that
# frontend.py re-exports (`from scripts.compat.frontend_orig import *`).
FRONTEND_PY = ROOT / "scripts" / "compat" / "frontend_orig.py"


def test_table_has_caption_and_column_scope():
    """The sent-messages table had no <caption> and no scope="col" on any
    of its 5 <th> elements."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 5


def test_view_button_is_wired_to_a_detail_modal():
    """The "View" button had no onclick/href/data-* attributes and no JS
    file was loaded for this page at all -- it was a completely
    non-functional dead control on every row."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert 'data-bs-target="#messageDetailModal"' in html
    assert 'id="messageDetailModal"' in html
    assert "show.bs.modal" in html


def test_view_button_has_per_message_accessible_name():
    """Every row's View button previously had the identical accessible
    name ("View"/"عرض") with no way to distinguish which message it
    opens."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "aria-label=\"{% if ui_lang == 'en' %}View message: {{ message.subject }}" in html


def test_status_badge_reflects_real_queue_status_not_hardcoded():
    """The status column was hardcoded to always render "Sent"/"مرسلة"
    regardless of the message's actual queue_status (DRAFT, QUEUED,
    SCHEDULED, SENT, FAILED, CANCELLED per models.MessageQueueStatus) --
    a failed or still-queued message displayed as already sent."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "message.queue_status" in html
    for status in ["FAILED", "QUEUED", "SCHEDULED", "DRAFT", "CANCELLED"]:
        assert status in html


def test_route_passes_queue_status_and_body_to_template():
    """frontend.py's admin_messages_list route built the template context
    without queue_status or message_body at all, so the template had no
    way to show real status or message content even if it wanted to."""
    content = FRONTEND_PY.read_text(encoding="utf-8")
    assert '"queue_status": msg.queue_status.value if msg.queue_status else "SENT"' in content
    assert '"message_body": msg.message_body' in content


def test_modal_uses_textcontent_not_innerhtml():
    """The modal-population script must assign message data via
    textContent, not innerHTML, since message subject/body is
    admin-authored free text and must not be interpretable as markup."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    script_start = html.index("show.bs.modal")
    script = html[script_start:]
    assert ".innerHTML" not in script
    assert script.count(".textContent =") >= 6
