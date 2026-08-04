"""I-9: static/css/print.css is wired into the manager layout as a print-only sheet.

Asserts the reference exists exactly once, is `media="print"` (inert on screen),
never leaks to screen media, and that wiring it did not drop the screen stylesheets.
"""
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MANAGER_BASE = _ROOT / "templates" / "manager_base.html"
_PRINT_CSS = _ROOT / "static" / "css" / "print.css"

_PRINT_LINK = re.compile(r'<link[^>]*href="[^"]*print\.css"[^>]*>')


def _manager_base_html() -> str:
    return _MANAGER_BASE.read_text(encoding="utf-8")


def test_print_css_file_exists_and_non_empty():
    assert _PRINT_CSS.is_file()
    assert _PRINT_CSS.stat().st_size > 0


def test_manager_base_links_print_css_exactly_once():
    links = _PRINT_LINK.findall(_manager_base_html())
    assert len(links) == 1, f"expected exactly one print.css <link>, found {len(links)}: {links}"


def test_print_css_link_is_print_media_only():
    link = _PRINT_LINK.search(_manager_base_html()).group(0)
    assert 'media="print"' in link, f"print.css must be media=print, got: {link}"


def test_print_css_never_loaded_as_screen_stylesheet():
    # Any print.css link must carry media="print" (else its print rules leak to screen).
    for link in _PRINT_LINK.findall(_manager_base_html()):
        assert 'media="print"' in link


def test_manager_screen_stylesheets_still_present():
    # Regression: wiring the print sheet must not remove the screen CSS.
    html = _manager_base_html()
    assert "/static/css/kinjo.css" in html
    assert "/static/css/manager_design.css" in html
