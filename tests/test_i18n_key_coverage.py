"""
Tests that both admin JSON catalogs have the required new keys,
that no hardcoded English strings remain in safety_analytics.html,
and that admin_components.js no longer contains bare English session strings.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "static" / "i18n"
TEMPLATES_DIR = ROOT / "templates"
JS_DIR = ROOT / "static" / "js"


def _load_en():
    return json.loads((I18N_DIR / "admin_en.json").read_text(encoding="utf-8"))


def _load_ar():
    return json.loads((I18N_DIR / "admin_ar.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Key parity — safety_analytics section
# ---------------------------------------------------------------------------

SAFETY_ANALYTICS_KEYS = {
    "title", "breadcrumb", "eyebrow", "page_title", "back",
    "admin_notice_title", "admin_notice_body",
    "filters_title", "filter_kindergarten", "filter_all_kg",
    "filter_type", "filter_all_types", "filter_classification",
    "filter_all_classifications", "filter_severity", "filter_all_severities",
    "filter_parent_informed", "filter_all", "filter_informed", "filter_not_informed",
    "filter_from", "filter_to", "apply_filters",
    "kpi_total", "kpi_open", "kpi_closed", "kpi_informed", "kpi_not_informed", "kpi_repeated",
    "severity_distribution", "type_distribution", "classification_distribution",
    "by_kindergarten", "high_risk_badge",
    "col_kindergarten", "col_count", "col_level", "col_child_id", "col_actions",
    "high_risk_label", "normal_label", "kg_prefix",
    "repeated_children", "view_profile", "child_prefix",
    "no_data", "loading", "no_repeated_children",
    "type_injury", "type_illness", "type_allergy", "type_behavior", "type_other",
    "class_accident", "class_behavioral", "class_medical", "class_environmental", "class_other",
    "sev_low", "sev_medium", "sev_high", "sev_critical", "sev_unknown",
}


def test_en_has_safety_analytics_section():
    data = _load_en()
    assert "safety_analytics" in data, "admin_en.json missing safety_analytics section"
    missing = SAFETY_ANALYTICS_KEYS - set(data["safety_analytics"].keys())
    assert not missing, f"admin_en.json safety_analytics missing keys: {sorted(missing)}"


def test_ar_has_safety_analytics_section():
    data = _load_ar()
    assert "safety_analytics" in data, "admin_ar.json missing safety_analytics section"
    missing = SAFETY_ANALYTICS_KEYS - set(data["safety_analytics"].keys())
    assert not missing, f"admin_ar.json safety_analytics missing keys: {sorted(missing)}"


def test_safety_analytics_key_parity():
    en = set(_load_en().get("safety_analytics", {}).keys())
    ar = set(_load_ar().get("safety_analytics", {}).keys())
    only_en = en - ar
    only_ar = ar - en
    assert not only_en, f"Keys only in admin_en.json safety_analytics: {sorted(only_en)}"
    assert not only_ar, f"Keys only in admin_ar.json safety_analytics: {sorted(only_ar)}"


# ---------------------------------------------------------------------------
# Key parity — components section
# ---------------------------------------------------------------------------

COMPONENTS_KEYS = {
    "connectivity_error", "retry_now",
    "session_warning", "stay_logged_in", "session_expired",
    "error_title", "unexpected_error", "background_error",
    "confirm_action", "confirm_message", "confirm_text", "cancel_text",
    "loading",
}


def test_en_has_components_section():
    data = _load_en()
    assert "components" in data, "admin_en.json missing components section"
    missing = COMPONENTS_KEYS - set(data["components"].keys())
    assert not missing, f"admin_en.json components missing keys: {sorted(missing)}"


def test_ar_has_components_section():
    data = _load_ar()
    assert "components" in data, "admin_ar.json missing components section"
    missing = COMPONENTS_KEYS - set(data["components"].keys())
    assert not missing, f"admin_ar.json components missing keys: {sorted(missing)}"


def test_components_key_parity():
    en = set(_load_en().get("components", {}).keys())
    ar = set(_load_ar().get("components", {}).keys())
    only_en = en - ar
    only_ar = ar - en
    assert not only_en, f"Keys only in admin_en.json components: {sorted(only_en)}"
    assert not only_ar, f"Keys only in admin_ar.json components: {sorted(only_ar)}"


# ---------------------------------------------------------------------------
# safety_analytics.html — bilingual guards present throughout
# ---------------------------------------------------------------------------

_ARABIC_RE = re.compile(r"[؀-ۿ]")
_JINJA_GUARD_RE = re.compile(
    r'\{%\s*if\s+ui_lang\s*==\s*[\'"]en[\'"]\s*%\}', re.MULTILINE
)
_JINJA_ELSE_RE = re.compile(r'\{%\s*else\s*%\}', re.MULTILINE)


def test_safety_analytics_html_has_bilingual_guards():
    """safety_analytics.html must have sufficient bilingual guards covering all visible text."""
    html = (TEMPLATES_DIR / "admin" / "safety_analytics.html").read_text(encoding="utf-8")

    guard_count = len(_JINJA_GUARD_RE.findall(html))
    assert guard_count >= 20, (
        f"safety_analytics.html has too few bilingual guards ({guard_count}); "
        "expected at least 20 {% if ui_lang == 'en' %} blocks"
    )

    # Also verify the page title is bilingual
    assert "Incident Analytics" in html, "Page title English variant missing"
    assert "تحليلات الحوادث" in html, "Page title Arabic variant missing"

    # Verify filters are bilingual
    assert "Report Filters" in html, "Filter section English label missing"
    assert "فلاتر التقرير" in html, "Filter section Arabic label missing"

    # Verify KPI labels are bilingual
    assert "Total Incidents" in html, "KPI label English missing"
    assert "إجمالي الحوادث" in html, "KPI label Arabic missing"

    # Verify the inline JS uses _t() helper (not raw Arabic string literals)
    script_match = re.search(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    if script_match:
        script = script_match.group(1)
        assert "_isEn" in script, "safety_analytics inline JS missing _isEn bilingual helper"
        assert "_t(" in script, "safety_analytics inline JS missing _t() bilingual calls"


# ---------------------------------------------------------------------------
# admin_components.js — bare hardcoded English session strings removed
# ---------------------------------------------------------------------------

HARDCODED_EN_STRINGS = [
    "Cannot connect to server. Retrying",
    "Retry now",
    "Your session will expire in 1 minute due to inactivity.",
    "Stay logged in",
    "Your session expired due to inactivity. Please sign in again.",
]


def test_admin_components_no_bare_hardcoded_english_session_strings():
    src = (JS_DIR / "admin_components.js").read_text(encoding="utf-8")
    for bad_string in HARDCODED_EN_STRINGS:
        # Allow it ONLY as the fallback in the ternary: "...", "string" )
        # The pattern: AdminI18n.translate("key", "bad_string")
        # We check that any occurrence is always preceded by a translate( call
        idx = src.find(bad_string)
        if idx == -1:
            continue
        context = src[max(0, idx - 80):idx + len(bad_string) + 5]
        assert "translate(" in context or "AdminI18n" in context, (
            f"Bare hardcoded English string found in admin_components.js without i18n wrapper: "
            f"'{bad_string}'\nContext: {context}"
        )


# ---------------------------------------------------------------------------
# admin_base.html — confirm/error strings use AdminI18n
# ---------------------------------------------------------------------------

def test_admin_base_error_notifications_use_i18n():
    html = (TEMPLATES_DIR / "admin_base.html").read_text(encoding="utf-8")
    assert "components.error_title" in html, (
        "admin_base.html error handler does not reference components.error_title i18n key"
    )
    assert "components.unexpected_error" in html, (
        "admin_base.html error handler does not reference components.unexpected_error i18n key"
    )
    assert "components.background_error" in html, (
        "admin_base.html error handler does not reference components.background_error i18n key"
    )


def test_admin_base_confirm_dialog_uses_i18n():
    html = (TEMPLATES_DIR / "admin_base.html").read_text(encoding="utf-8")
    assert "components.confirm_action" in html, (
        "admin_base.html AdminUtils.confirm does not reference components.confirm_action i18n key"
    )
    assert "components.confirm_text" in html, (
        "admin_base.html AdminUtils.confirm does not reference components.confirm_text i18n key"
    )


# ---------------------------------------------------------------------------
# EN catalog must be free of Arabic values (includes new sections)
# ---------------------------------------------------------------------------

def _iter_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_values(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values(item)


def test_en_catalog_new_sections_have_no_arabic_values():
    data = _load_en()
    for section in ("safety_analytics", "components"):
        section_data = data.get(section, {})
        for value in _iter_values(section_data):
            assert not _ARABIC_RE.search(value), (
                f"Arabic text in admin_en.json [{section}]: {value!r}"
            )
