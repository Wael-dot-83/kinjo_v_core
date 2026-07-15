"""Every API path called by a template or JS file must resolve to a registered route.

This is the automated form of an audit that keeps finding the same class of bug:
a frontend call whose URL no longer matches the backend, failing silently because
the caller's `catch` renders an empty state instead of an error. Found this way:

* `/api/governorates/{gov}/cities` — never registered; the enrollment
  governorate→district dropdown silently rendered no options (the backend route
  is `/districts`, a leftover of the city→district migration).
* `/api/attendance/absence-requests` (GET) and
  `/api/attendance/absence-requests/{id}/cancel` — only the *create* endpoint
  lives under the `/api/attendance/` prefix, so listing and cancelling 404'd.

`KNOWN_UNRESOLVED` records paths that are deliberately not registered yet, so this
test states the gap instead of hiding it. Entries must carry a reason.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.routing import Mount

from main import app

# Paths that are known-dead and tracked elsewhere; each needs a reason so the list
# cannot quietly become a dumping ground. These belong to features whose backend
# was never implemented — repointing them is not possible, they need building.
KNOWN_UNRESOLVED = {
    "/api/kindergartens/{id}/services": "services CRUD never implemented (templates/kindergartens/view.html)",
    "/api/kindergartens/{id}/archive": "archive endpoint never implemented (templates/kindergartens/view.html)",
    "/api/notifications/{id}/read": "single mark-read never implemented; only /read-all exists",
    "/api/daily-reports/manager/create-and-send": "manager create-and-send never implemented",
    "/api/supervisor/present-children": "superseded by /api/supervisor/attendance/status; caller is dead code",
    "/api/manager/accounts": "uncalled dead method in kinjo-api.js",
    "/api/manager/alerts": "uncalled dead method in kinjo-api.js",
    "/api/manager/reports/submitted": "uncalled dead method in kinjo-api.js",
    "/api/manager/reports/{id}/approve": "uncalled dead method in kinjo-api.js",
    "/api/manager/reports/{id}/reject": "uncalled dead method in kinjo-api.js",
    "/api/analytics/list-dimensions": "advanced_analytics.js — orphaned template, no route renders it",
    "/api/analytics/predictive": "advanced_analytics.js — orphaned template",
    "/api/analytics/scatter": "advanced_analytics.js — orphaned template",
    "/api/analytics/demographics": "advanced_analytics.js — orphaned template",
    "/api/analytics/government-report": "advanced_analytics.js — orphaned template",
}

# Scanned sources. Templates and JS are where frontend→backend drift shows up.
_SCAN_DIRS = (Path("templates"), Path("static/js"))

# `/api/...` inside a quoted string or template literal, up to the quote or a
# query string. Captures interpolations as `{...}` so they normalise to params.
_API_CALL_RE = re.compile(r"""["'`](/api/[^"'`?\s]*)""")


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}".replace("//", "/")


def _walk(router, prefix: str = ""):
    """FastAPI defers `include_router`, so nested routes live behind opaque
    `_IncludedRouter` nodes and never appear in a flat `app.routes` scan."""
    for route in getattr(router, "routes", []):
        if isinstance(route, Mount):
            continue
        if type(route).__name__ == "_IncludedRouter":
            ctx = getattr(route, "include_context", None)
            if ctx:
                yield from _walk(ctx.included_router, _join(prefix, ctx.prefix or ""))
            continue
        if hasattr(route, "path"):
            yield _join(prefix, route.path)


def _registered_patterns() -> set[str]:
    """Registered paths with their params normalised to `{}`."""
    return {re.sub(r"\{[^}]+\}", "{}", p) for p in _walk(app)}


def _normalise(call: str) -> str:
    """Normalise a called URL so it can be compared to a route pattern."""
    # `${...}` / `{{ ... }}` / `{...}` / `' + x + '` interpolations become a param.
    call = re.sub(r"\$\{[^}]*\}", "{}", call)
    call = re.sub(r"\{\{.*?\}\}", "{}", call)
    call = re.sub(r"\{[^{}]*\}", "{}", call)
    call = re.sub(r"'\s*\+\s*[^+]+\+\s*'", "{}", call)
    # A dangling `{{` from a split Jinja expression leaves an unusable segment.
    call = re.sub(r"\{+$", "{}", call)
    call = call.rstrip("/") or "/"
    return re.sub(r"/\d+(?=/|$)", "/{}", call)


def _segments_match(call: str, pattern: str) -> bool:
    """Segment-wise match, where `{}` on either side is a wildcard.

    A param on the pattern side accepts any literal:
    `/api/analytics/rankings/governance_score` must match
    `/api/analytics/rankings/{metric}` — comparing whole strings would call a
    live route dead. A param on the *call* side is equally a wildcard: the URL
    `/api/absence-requests/${id}/${action}` is built at runtime and legitimately
    resolves to the `/approve` and `/reject` routes.
    """
    call_parts, pat_parts = call.strip("/").split("/"), pattern.strip("/").split("/")
    if len(call_parts) != len(pat_parts):
        return False
    return all(p == "{}" or c == "{}" or p == c for c, p in zip(call_parts, pat_parts))


def _iter_calls():
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".html", ".js"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                for match in _API_CALL_RE.finditer(line):
                    yield path, lineno, match.group(1)


def _resolves(call: str, patterns: set[str]) -> bool:
    norm = _normalise(call)
    if any(_segments_match(norm, p) for p in patterns):
        return True
    # A call may be a base constant that gets a suffix appended at runtime.
    return any(p.startswith(norm + "/") for p in patterns)


def _allowlisted(call: str) -> bool:
    norm = _normalise(call)
    return any(
        _segments_match(norm, _normalise(k)) or norm.startswith(_normalise(k) + "/")
        for k in KNOWN_UNRESOLVED
    )


@pytest.fixture(scope="module")
def patterns():
    return _registered_patterns()


def test_route_walker_sees_the_whole_app(patterns):
    """Guards the walker itself: a flat `app.routes` scan sees only ~27 paths, so a
    naive audit reports 'no problems' while missing 95% of the app."""
    assert len(patterns) > 500, (
        f"only {len(patterns)} routes discovered — the _IncludedRouter walk is broken, "
        "so every other check in this file would silently pass"
    )


def test_every_frontend_api_call_resolves_to_a_registered_route(patterns):
    unresolved = {}
    for path, lineno, call in _iter_calls():
        if _resolves(call, patterns):
            continue
        if _allowlisted(call):
            continue
        unresolved.setdefault(_normalise(call), []).append(f"{path.as_posix()}:{lineno}")

    assert not unresolved, "frontend calls that no registered route can answer:\n" + "\n".join(
        f"  {call}\n    called from: {', '.join(sites)}" for call, sites in sorted(unresolved.items())
    )


def test_known_unresolved_entries_are_still_unresolved(patterns):
    """Stops the allowlist from outliving the gap: once a route is implemented, its
    entry must be removed or it silently exempts a live path from the check."""
    now_resolved = [
        call
        for call in KNOWN_UNRESOLVED
        if any(_segments_match(_normalise(call), p) for p in patterns)
    ]
    assert not now_resolved, (
        "these paths are now registered — remove them from KNOWN_UNRESOLVED: "
        f"{now_resolved}"
    )
