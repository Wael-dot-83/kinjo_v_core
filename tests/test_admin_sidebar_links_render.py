"""Every link in the admin sidebar must actually render.

test_admin_sidebar_navigation.py asserts each sidebar href resolves to a
*registered* GET route. Registered is not rendered: /reports/analytics was a
registered route that returned 500 on every request (a duplicate Jinja context
processor omitted `impersonation`, so the banner partial raised UndefinedError).
The navigation test passed anyway, because a route can exist and still be a dead
end.

That gap matters most for exactly the change that surfaced it — promoting a page
into the sidebar takes a page nobody navigated to and puts it one click from
every admin. So assert the thing users experience: the page comes back.

Deliberately asserts `!= 500` rather than `== 200`. Some links legitimately
redirect (302) or gate by role (403); pinning 200 would encode today's auth
shape and fail for reasons unrelated to the page being broken. A 5xx is never
legitimate.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"


def _sidebar_hrefs() -> list[str]:
    source = ADMIN_BASE.read_text(encoding="utf-8")
    idx = source.index('id="admin-sidebar"')
    start = source.rindex("<aside", 0, idx)
    sidebar = source[start:source.index("</aside>", start)]
    # Strip the in-page anchor: it is a fragment of another page, not a route.
    return [h.split("#")[0] for h in re.findall(r'"href":\s*"([^"]+)"', sidebar)]


def test_the_scan_found_the_sidebar():
    """Anti-vacuity: an empty href list would make the sweep below pass on air."""
    hrefs = _sidebar_hrefs()
    assert len(hrefs) > 25, f"only {len(hrefs)} sidebar hrefs found — the parse broke"
    assert "/admin/dashboard" in hrefs


@pytest.mark.parametrize("href", _sidebar_hrefs())
def test_sidebar_link_does_not_error(client, auth_headers_admin, href):
    response = client.get(href, headers=auth_headers_admin, follow_redirects=False)
    assert response.status_code < 500, (
        f"sidebar links {href} but it returns {response.status_code}:\n"
        f"{response.text[:400]}"
    )
