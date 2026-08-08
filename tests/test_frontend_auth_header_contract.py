"""No page may send `AuthService.getToken()` as a Bearer credential.

`AuthService.getToken()` does not return the JWT. Since 5e688b7a ("harden cookies and
remove JWT from browser storage") the session lives in the HttpOnly `kinjo_session`
cookie, and `getToken()` returns the **CSRF cookie** as a truthy sentinel so that
legacy `if (getToken())` guards keep working (static/js/auth.js).

Sending that sentinel as `Authorization: Bearer <csrf>` is not merely useless — it is
actively destructive. A request that would have authenticated fine on the cookie alone
is rejected 401, and auth.js's fetch wrapper turns *any* 401 into
`window.location.href = "/login?expired=true"`. The page therefore logs the user out.

Verified in a real browser on 2026-07-16: `/kindergartens/1` issued two such calls
(`/api/classes`, `/api/users`), took two 401s, and bounced an authenticated admin to
`/login?expired=true`. The same calls with no Authorization header return 200.

Correct pattern: send no Authorization header. The cookie authenticates; auth.js's
wrapper injects `X-CSRF-Token` on unsafe methods.
"""
from __future__ import annotations

import re
from pathlib import Path

_SCAN_DIRS = (Path("templates"), Path("static/js"))
_BEARER_RE = re.compile(r"""Bearer\s*\$\{\s*(?:token|authToken|t)\s*\}|['"]Bearer\s*['"]\s*\+\s*token""")

# A second shape of the same bug, which the pattern above does not see because it
# never names a `token` variable: the header is built inline from a storage key.
#
# `kinjo_token` is dead — nothing has written it since the JWT left browser storage —
# so every one of these sent `Authorization: Bearer null`. Found by browser-driving
# the pages, not by the scanner, which is the point of keeping both checks:
# `/notifications` took a 401 and rendered no list, and `PUT /api/users/me/password`
# 401'd, so nobody could change their password. Verified 2026-07-16: the same request
# returns 200 with no header and 401 with `Bearer null`.
# Both spellings of the inline storage read. The template-literal form was missed by the
# concatenation-only version of this pattern, which left templates/supervisor/settings.html
# sitting in the tree with the bug while the ratchet reported clean — the check was
# guarding a spelling rather than a defect.
_STORAGE_BEARER_RE = re.compile(
    r"""['"]Bearer\s*['"]\s*\+\s*\(?\s*(?:local|session)Storage\.getItem"""   # 'Bearer ' + localStorage.getItem(…)
    r"""|Bearer\s*\$\{\s*\(?\s*(?:local|session)Storage\.getItem"""            # `Bearer ${localStorage.getItem(…)}`
)

# Files still carrying the bug. Each one boots the user to /login?expired=true the
# moment its call path runs. They are outside the Admin module (parent/manager/
# supervisor/communication surfaces) and each needs its own browser verification, so
# they are tracked rather than bulk-edited blind.
#
# This list may only ever SHRINK. Fixing a file and leaving it here fails the test.
KNOWN_BROKEN = {
    "templates/communication/events.html",
    "templates/communication/modals/new_event.html",
    "templates/communication/modals/new_message.html",
    "templates/communication/modals/new_survey.html",
    "templates/communication/surveys.html",
    "templates/enrollment/create.html",
    "templates/enrollment/view.html",
    "templates/kpi/dashboard.html",
    "templates/reports/form.html",
    "templates/supervisor/observations.html",
}


def _offenders() -> dict[str, list[int]]:
    """Files building a Bearer header out of a nearby `getToken()` result."""
    found: dict[str, list[int]] = {}
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".html", ".js"} or not path.is_file():
                continue
            if path.name == "auth.js":  # defines the sentinel; does not consume it
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if not _BEARER_RE.search(line):
                    continue
                window = "\n".join(lines[max(0, i - 25):i])
                if "getToken()" in window:
                    found.setdefault(path.as_posix(), []).append(i)
    return found


def _storage_offenders() -> dict[str, list[int]]:
    """Files building a Bearer header straight from a browser-storage key."""
    found: dict[str, list[int]] = {}
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".html", ".js"} or not path.is_file():
                continue
            if path.name == "auth.js":
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if _STORAGE_BEARER_RE.search(line):
                    found.setdefault(path.as_posix(), []).append(i)
    return found


def test_scanner_is_not_vacuous():
    """If the regex or the scan dirs break, every assertion below passes trivially.

    Pinned against the real shapes the bug takes, so a decayed scanner is loud.
    """
    sample = [
        "        if (token) headers['Authorization'] = `Bearer ${token}`;",
        '        headers["Authorization"] = "Bearer " + token;',
    ]
    for s in sample:
        assert _BEARER_RE.search(s), f"scanner no longer recognises the bug shape: {s!r}"
    storage_sample = [
        "'Authorization': 'Bearer ' + (localStorage.getItem('kinjo_token') || sessionStorage.getItem('kinjo_token'))",
        "'Authorization': 'Bearer ' + sessionStorage.getItem('kinjo_token')",
        # The template-literal spelling. An earlier version of this pattern matched only
        # the concatenation form and reported the tree clean while this exact line was
        # live in templates/supervisor/settings.html.
        "{ 'Authorization': `Bearer ${localStorage.getItem('kinjo_token') || sessionStorage.getItem('kinjo_token')}` }",
    ]
    for s in storage_sample:
        assert _STORAGE_BEARER_RE.search(s), f"storage scanner no longer recognises: {s!r}"
    assert Path("templates").exists() and Path("static/js").exists(), "scan dirs missing"


def test_no_page_builds_a_bearer_header_from_browser_storage():
    """The JWT is not in browser storage, so any such header is `Bearer null`.

    This shape names no `token` variable, so the getToken() scanner above never saw it.
    It cost a real outage on two pages: `/notifications` 401'd and rendered nothing, and
    `PUT /api/users/me/password` 401'd, so no one could change their password.
    """
    offenders = _storage_offenders()
    assert not offenders, (
        "these pages build an Authorization header from a browser-storage key. The JWT "
        "lives in the HttpOnly kinjo_session cookie and is not readable from JS, so "
        f"this sends `Bearer null` and the server answers 401: {offenders}. Send no "
        "Authorization header."
    )


def test_kindergarten_view_does_not_send_the_csrf_sentinel_as_bearer():
    """The regression this file was written for: an admin opening a kindergarten got
    logged out. Verified fixed in a real browser — page stays, 401s gone."""
    offenders = _offenders()
    assert "templates/kindergartens/view.html" not in offenders, (
        "templates/kindergartens/view.html builds `Bearer ${AuthService.getToken()}` "
        f"again at lines {offenders.get('templates/kindergartens/view.html')}. That "
        "sends the CSRF sentinel as a credential; the server answers 401 and auth.js "
        "redirects to /login?expired=true, logging the admin out of the page."
    )


def test_no_new_file_starts_sending_the_sentinel_as_bearer():
    """Ratchet: the known-broken set may shrink, never grow."""
    new = set(_offenders()) - KNOWN_BROKEN
    assert not new, (
        "new file(s) send `AuthService.getToken()` as a Bearer credential — this logs "
        f"the user out when the call runs: {sorted(new)}. Send no Authorization "
        "header; the HttpOnly session cookie authenticates and auth.js injects CSRF."
    )


def test_known_broken_list_has_no_stale_entries():
    """Stops the allowlist outliving the bug: a fixed file must leave the list, or it
    silently exempts a live page from the ratchet above."""
    fixed = KNOWN_BROKEN - set(_offenders())
    assert not fixed, (
        f"these files no longer have the bug — remove them from KNOWN_BROKEN: {sorted(fixed)}"
    )
