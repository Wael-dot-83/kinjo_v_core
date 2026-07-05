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
    """#rolesFilter (decorative, always-checked-and-disabled Managers/
    Supervisors/Parents checkboxes) had no visibility toggling at all --
    it stayed visible for every target mode, including ALL_MANAGERS/
    ALL_SUPERVISORS/ALL_PARENTS/ALL_USERS, where showing all three roles
    checked is actively misleading since getTargetData() only hardcodes
    that role triple for GOVERNORATE/KINDERGARTENS modes."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="rolesFilter" class="mb-3 d-none"' in html
    assert "rolesFilter.classList.add('d-none')" in html
    # Must be revealed only for the two modes whose getTargetData() actually
    # uses the hardcoded role triple this filter describes.
    gov_branch = html[html.index("if (mode === 'GOVERNORATE')"):html.index("} else if (mode === 'KINDERGARTENS')")]
    kg_branch = html[html.index("} else if (mode === 'KINDERGARTENS')"):html.index("async function loadKindergartens")]
    assert "rolesFilter.classList.remove('d-none')" in gov_branch
    assert "rolesFilter.classList.remove('d-none')" in kg_branch


def test_action_icons_are_marked_decorative():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<i class="bi bi-eye me-2" aria-hidden="true"></i>' in html
    assert '<i class="bi bi-send me-2" aria-hidden="true"></i>' in html
    assert '<i class="bi bi-person text-secondary me-1" aria-hidden="true"></i>' in html
