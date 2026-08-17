"""
Accessibility HTML audit: no duplicate IDs, every input has a label.
Scans rendered HTML from the test client for admin pages.
"""
import re
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r'\bid=["\']([^"\']+)["\']', re.IGNORECASE)
_INPUT_ID_RE = re.compile(
    r'<(input|select|textarea)[^>]*\bid=["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
_LABEL_FOR_RE = re.compile(r'<label[^>]*\bfor=["\']([^"\']+)["\']', re.IGNORECASE)
_ARIA_LABELLEDBY_RE = re.compile(r'\baria-labelledby=["\']([^"\']+)["\']', re.IGNORECASE)
_ARIA_LABEL_RE = re.compile(r'\baria-label=["\'][^"\']+["\']', re.IGNORECASE)
_NESTED_LABEL_RE = re.compile(
    r'<label\b[^>]*>.*?<(input|select|textarea)\b',
    re.IGNORECASE | re.DOTALL,
)


_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _rendered_markup(html: str) -> str:
    """The markup a browser actually builds a DOM from.

    Inline <script> bodies and HTML comments are not DOM elements, and scanning
    them produced false positives that made this test untrustworthy: client-side
    templates yielded ids of `${c.id}` and `${user.id}`, and a JS comment that
    merely mentioned `<nav id="pagination">` was counted as a second element with
    that id. Every one of those was reported as a duplicate-id failure against a
    page that had none.
    """
    return _HTML_COMMENT_RE.sub("", _SCRIPT_RE.sub("", html))


def _collect_ids(html: str) -> list[str]:
    return _ID_RE.findall(_rendered_markup(html))


def _duplicate_ids(html: str) -> list[str]:
    counts = Counter(_collect_ids(html))
    return [id_ for id_, n in counts.items() if n > 1]


def _unlabelled_inputs(html: str) -> list[str]:
    """Return IDs of inputs that have no <label for=>, no aria-label,
    no aria-labelledby, and are not nested inside a <label>."""
    html = _rendered_markup(html)
    label_targets = set(_LABEL_FOR_RE.findall(html))
    labelledby_targets = set(_ARIA_LABELLEDBY_RE.findall(html))
    nested_re = _NESTED_LABEL_RE

    # Build rough map of input id → surrounding HTML context (±200 chars)
    unlabelled = []
    for m in _INPUT_ID_RE.finditer(html):
        tag, id_ = m.group(1), m.group(2)
        tag_end_idx = html.find(">", m.start())
        whole_tag = html[m.start(): tag_end_idx] if tag_end_idx != -1 else m.group(0)
        # A hidden input is not a control anyone can see or focus, so it has
        # nothing to label. Requiring one produced noise, not accessibility.
        if re.search(r'type\s*=\s*["\']hidden["\']', whole_tag, re.IGNORECASE):
            continue
        if id_ in label_targets:
            continue
        if id_ in labelledby_targets:
            continue
        start = max(0, m.start() - 200)
        ctx = html[start : m.end() + 100]
        if nested_re.search(ctx):
            continue
        # Scan the whole tag (up to '>'), not just the regex match, so an
        # aria-label written after the id attribute is still detected.
        tag_end = html.find(">", m.start())
        full_tag = html[m.start() : tag_end] if tag_end != -1 else m.group(0)
        if _ARIA_LABEL_RE.search(full_tag):
            continue
        unlabelled.append(id_)
    return unlabelled


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def admin_client(admin_token):
    """TestClient authenticated as admin."""
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set("kinjo_token", admin_token)
        yield c


# ---------------------------------------------------------------------------
# Tests: duplicate IDs
# ---------------------------------------------------------------------------

# Every admin page route that renders without a path parameter.
#
# This list held three entries while the admin shipped thirty-five such pages,
# so the guarantee covered under a tenth of the surface it appeared to cover.
# The markup turned out to be in good shape when the rest was audited by hand --
# which is the argument for checking it automatically rather than the argument
# against. Each test skips a route that 404s or redirects, so adding a page here
# costs nothing when the route is unavailable in the test environment.
ADMIN_PAGES_NO_DUP_ID = [
    "/admin/alerts",
    "/admin/analytics",
    "/admin/analytics/charts",
    "/admin/analytics/daily-reports",
    "/admin/analytics/dashboard",
    "/admin/analytics/decision-support",
    "/admin/analytics/reports",
    "/admin/audit-logs",
    "/admin/classification",
    "/admin/contact-messages",
    "/admin/daily-reports-organization",
    "/admin/dashboard",
    "/admin/governance-reports",
    "/admin/governance/reminders",
    "/admin/heatmap",
    "/admin/help",
    "/admin/impersonate",
    "/admin/import-kindergartens",
    "/admin/import-logs",
    "/admin/imported-kindergartens",
    "/admin/kg-overview",
    "/admin/kindergartens",
    "/admin/kindergartens/new",
    "/admin/kpi",
    "/admin/messages",
    "/admin/messages/compose",
    "/admin/observability",
    "/admin/profile",
    "/admin/reports/incidents",
    "/admin/reports/incidents/generate",
    "/admin/safety-analytics",
    "/admin/settings",
    "/admin/users",
    "/admin/users/create",
    "/admin/users/import",
]


@pytest.mark.parametrize("path", ADMIN_PAGES_NO_DUP_ID)
def test_no_duplicate_ids(admin_client, path):
    """Every rendered admin page must have globally unique element IDs."""
    r = admin_client.get(path)
    if r.status_code in (404, 307):
        pytest.skip(f"{path} not available ({r.status_code})")
    html = r.text
    dupes = _duplicate_ids(html)
    assert not dupes, f"{path} has duplicate IDs: {dupes}"


# ---------------------------------------------------------------------------
# Tests: label associations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ADMIN_PAGES_NO_DUP_ID)
def test_inputs_have_labels(admin_client, path):
    """Every <input>/<select>/<textarea> must be associated with a <label>."""
    r = admin_client.get(path)
    if r.status_code in (404, 307):
        pytest.skip(f"{path} not available ({r.status_code})")
    html = r.text
    unlabelled = _unlabelled_inputs(html)
    assert not unlabelled, (
        f"{path} has inputs without label associations: {unlabelled}"
    )


# ---------------------------------------------------------------------------
# Tests: DOCTYPE and html[lang]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ADMIN_PAGES_NO_DUP_ID)
def test_doctype_present(admin_client, path):
    r = admin_client.get(path)
    if r.status_code in (404, 307):
        pytest.skip(f"{path} not available ({r.status_code})")
    assert r.text.lstrip().lower().startswith("<!doctype html"), (
        f"{path} page source does not start with <!DOCTYPE html>"
    )


@pytest.mark.parametrize("path", ADMIN_PAGES_NO_DUP_ID)
def test_html_lang_attribute(admin_client, path):
    r = admin_client.get(path)
    if r.status_code in (404, 307):
        pytest.skip(f"{path} not available ({r.status_code})")
    assert re.search(r'<html[^>]+lang=["\'][a-z]{2}', r.text, re.IGNORECASE), (
        f"{path}: <html> element missing lang attribute"
    )
