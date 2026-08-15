"""I-9: static/css/print.css is wired into the manager layout as a print-only sheet.

Asserts the reference exists exactly once, is `media="print"` (inert on screen),
never leaks to screen media, and that wiring it did not drop the screen stylesheets.
"""
import re

import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MANAGER_BASE = _ROOT / "templates" / "manager_base.html"
_PRINT_CSS = _ROOT / "static" / "css" / "print.css"

# The href must be allowed to carry a ?v= cache-buster. Anchoring on
# `print.css"` matched only an unversioned URL, so adding the version query
# every static asset needs made this regex find zero links -- which failed the
# count assertion and, worse, silently emptied the loop in
# test_print_css_never_loaded_as_screen_stylesheet, turning a real guarantee
# into a test that passes over nothing.
_PRINT_LINK = re.compile(r'<link[^>]*href="[^"]*print\.css(?:\?[^"]*)?"[^>]*>')


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
    links = _PRINT_LINK.findall(_manager_base_html())
    # Without this the test passes when the regex matches nothing at all, which
    # is exactly how it stayed green while the count assertion above was failing.
    assert links, "no print.css <link> found -- this test would prove nothing"
    for link in links:
        assert 'media="print"' in link


def test_manager_screen_stylesheets_still_present():
    # Regression: wiring the print sheet must not remove the screen CSS.
    html = _manager_base_html()
    assert "/static/css/kinjo.css" in html
    assert "/static/css/manager_design.css" in html


# ---------------------------------------------------------------------------
# Control cases for the matcher itself.
#
# Widening a regex to tolerate ?v= risks widening it into something that
# matches anything, or that quietly matches nothing -- and a matcher that
# matches nothing takes every findall() loop above down with it silently. The
# tests above run against one real template, so they cannot distinguish "the
# contract holds" from "the matcher stopped working". These drive the same
# matcher over synthetic HTML with the defects deliberately present, and
# assert it still reports them.
# ---------------------------------------------------------------------------

_LINK_VERSIONED = '<link rel="stylesheet" href="/static/css/print.css?v=1.0" media="print" />'
_LINK_BARE = '<link rel="stylesheet" href="/static/css/print.css" media="print" />'
_LINK_OTHER_QUERY = '<link rel="stylesheet" href="/static/css/print.css?v=9.9&x=1" media="print" />'
_LINK_SCREEN = '<link rel="stylesheet" href="/static/css/print.css?v=1.0" />'
_LINK_UNRELATED = '<link rel="stylesheet" href="/static/css/kinjo.css?v=2.0" />'


def test_matcher_accepts_any_cache_key_not_just_the_current_one():
    """The contract is about print.css being wired print-only, not about the
    version it is pinned at today. Coupling to ?v=1.0 would re-break this on
    the next bump."""
    for html in (_LINK_VERSIONED, _LINK_BARE, _LINK_OTHER_QUERY):
        assert len(_PRINT_LINK.findall(html)) == 1, f"should match: {html}"


def test_matcher_does_not_match_unrelated_stylesheets():
    """Guards the opposite failure: a regex loose enough to match anything
    would make every assertion above meaningless."""
    assert _PRINT_LINK.findall(_LINK_UNRELATED) == []


def test_contract_fails_when_the_link_is_absent():
    """The vacuous-pass hole: zero matches must not read as success."""
    links = _PRINT_LINK.findall(f"<head>{_LINK_UNRELATED}</head>")
    assert links == []
    # This is the assertion test_print_css_never_loaded_as_screen_stylesheet
    # gained; without it that test iterates an empty list and reports green.
    with pytest.raises(AssertionError):
        assert links, "no print.css <link> found -- this test would prove nothing"


def test_contract_fails_when_print_css_is_loaded_for_screen():
    """A print.css link with no media="print" leaks print rules onto screen --
    the defect this module exists to catch."""
    links = _PRINT_LINK.findall(f"<head>{_LINK_SCREEN}</head>")
    assert len(links) == 1, "the screen-media link must still be detected"
    assert 'media="print"' not in links[0]


def test_contract_fails_when_print_css_is_linked_twice():
    """Duplicate wiring must still break the exactly-once assertion."""
    assert len(_PRINT_LINK.findall(_LINK_VERSIONED + _LINK_BARE)) == 2
