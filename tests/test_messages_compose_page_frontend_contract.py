from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "messages" / "compose.html"


def test_dead_breadcrumb_block_removed():
    """8th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_governorate_checklist_has_bilingual_labels():
    """The template received both governorates (Arabic) and governorates_en
    (English) from frontend.py, but only ever looped `governorates` --
    English-mode admins saw an Arabic-only governorate checklist despite
    the backend already preparing the English label list for this exact
    purpose. Confirmed JORDAN_GOVERNORATES/JORDAN_GOVERNORATES_ENGLISH in
    config.py are positionally aligned, so a loop.index0 lookup is safe
    here (unlike a prior page's hardcoded list, which was NOT aligned)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "governorates_en" in html
    assert "governorates_en[loop.index0]" in html
    # canonical backend filter value must stay Arabic regardless of display language
    assert 'value="{{ gov }}"' in html


def test_roles_filter_hidden_by_default_and_toggled_with_relevant_modes():
    """Role selection belongs only to geographic/kindergarten targeting."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="rolesFilter" class="mb-3 d-none"' in html
    assert "rolesFilter.classList.add('d-none')" in html
    # Must be revealed only for the two modes that support a role refinement.
    gov_branch = html[html.index("if (mode === 'GOVERNORATE')"):html.index("} else if (mode === 'KINDERGARTENS')")]
    kg_branch = html[html.index("} else if (mode === 'KINDERGARTENS')"):html.index("async function loadKindergartens")]
    assert "rolesFilter.classList.remove('d-none')" in gov_branch
    assert "rolesFilter.classList.remove('d-none')" in kg_branch


def test_role_checkboxes_drive_both_preview_and_send_targeting():
    """The old UI displayed disabled role checkboxes while getTargetData()
    silently sent all three roles. The shared target builder is consumed by
    previewRecipients() and sendMessage(), so selected roles must come from
    the enabled controls and an empty selection must be rejected."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count('class="form-check-input role-checkbox"') == 3
    assert 'id="roleManager" value="MANAGER" checked disabled' not in html
    assert "document.querySelectorAll('.role-checkbox:checked')" in html
    assert ".map(c => c.value)" in html
    assert "async function previewRecipients()" in html
    assert "async function sendMessage()" in html
    assert html.count("Please select at least one role") == 2


def test_state_changing_message_request_uses_a_defined_csrf_token():
    """safeRequest referenced an undeclared csrfToken, so every POST failed
    before reaching the authenticated fetch wrapper."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "const csrfToken = csrfMeta?.content || '';" in html
    assert "if (isStateChanging && csrfToken)" in html


def test_create_message_post_is_not_retried_without_an_idempotency_key():
    """A lost response after commit must not cause a second announcement."""
    html = TEMPLATE.read_text(encoding="utf-8")
    send_block = html[html.index("await safeRequest('/api/admin/messages'"):]
    send_block = send_block[:send_block.index("await Swal.fire")]
    assert "}, 0);" in send_block


def test_action_icons_are_marked_decorative():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<i class="bi bi-eye me-2" aria-hidden="true"></i>' in html
    assert '<i class="bi bi-send me-2" aria-hidden="true"></i>' in html
    assert '<i class="bi bi-person text-secondary me-1" aria-hidden="true"></i>' in html
