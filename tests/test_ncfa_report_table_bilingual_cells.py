"""Report tables must never render a bilingual payload as "[object Object]".

agency_reports_service returns some cells as {"ar": ..., "en": ...} pairs -- the
"Total" row label and the indicator columns. The table renderer passed those
straight to String(), which produced "[object Object]" in every affected table.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js" / "ncfa_strong_reports.js"
SERVICE = ROOT / "agency_reports_service.py"


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def test_service_really_emits_bilingual_cell_payloads():
    """Guards the premise: if the backend stops sending {ar, en} cells this test
    should be revisited rather than silently passing."""
    source = SERVICE.read_text(encoding="utf-8")
    assert '{"ar": "المجموع", "en": "Total"}' in source


def test_renderer_resolves_bilingual_values():
    js = _js()
    assert "function localizedValue" in js
    # It must consider the active language first, then fall back.
    body = js.split("function localizedValue", 1)[1].split("function ", 1)[0]
    assert "value[lang]" in body
    assert "value.ar" in body
    assert "value.en" in body


def test_create_element_cannot_stringify_an_object():
    """Belt and braces: every textContent assignment goes through the resolver,
    so no caller can leak an object into the DOM."""
    js = _js()
    assert "String(localizedValue(opts.text))" in js
    assert "node.textContent = String(opts.text)" not in js


def test_category_localisation_still_applies_to_plain_strings():
    """The bilingual resolver must not bypass the existing category label map."""
    js = _js()
    body = js.split("function localizeCategory", 1)[1].split("\n  function ", 1)[0]
    assert "pickLocale(CATEGORY_LABELS" in body


def test_asset_version_bumped_for_the_fix():
    """Static assets are served immutable for a year; without a bump the fix
    never reaches anyone who has already opened the page."""
    tpl = (ROOT / "templates" / "admin" / "agency_reports" / "agency.html").read_text(encoding="utf-8")
    assert "ncfa_strong_reports.js?v=1.3" not in tpl
    assert "admin_agency_reports.js?v=3.9" not in tpl
