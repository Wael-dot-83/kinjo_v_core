"""Every API call a template or JS file makes must resolve to a registered route.

This is the automated form of an audit that keeps finding the same class of bug: a
frontend call whose URL no longer matches the backend, failing silently because the
caller's `catch` renders an empty state instead of an error. Found this way:

* `/api/governorates/{gov}/cities` — never registered; the enrollment
  governorate→district dropdown silently rendered no options (the route is
  `/districts`, a leftover of the city→district migration).
* `GET /api/attendance/absence-requests` and
  `POST /api/attendance/absence-requests/{id}/cancel` — only *create* lives under
  the `/api/attendance/` prefix, so listing and cancelling 404'd.
* `GET /api/daily-reports/submitted` — never registered; it binds to
  `/api/daily-reports/{report_id}` (an int param) and 422s.
* `POST /api/incidents/create` — never registered; creation is `POST /api/incidents`.

Matching is **method-aware** and **param-type-aware**, because a path-only check is
too weak to pin these: `/api/incidents/create` "matches" `/api/incidents/{id}` if you
ignore methods, and `/api/daily-reports/submitted` "matches"
`/api/daily-reports/{report_id}` unless you know `report_id` is an int.
`test_resolver_rejects_the_paths_this_file_was_written_to_catch` pins that strength,
so the checker cannot quietly decay into a tautology.
"""
from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, Mount

from main import app

# Known-dead paths whose backend was never implemented: they cannot be repointed,
# they need building. Each needs a reason so this cannot become a dumping ground.
KNOWN_UNRESOLVED = {
    ("GET", "/api/kindergartens/{}/services"): "services CRUD never implemented (templates/kindergartens/view.html)",
    ("POST", "/api/kindergartens/{}/services"): "services CRUD never implemented",
    ("PUT", "/api/kindergartens/{}/services/{}"): "services CRUD never implemented",
    ("DELETE", "/api/kindergartens/{}/services/{}"): "services CRUD never implemented",
    ("POST", "/api/kindergartens/{}/archive"): "archive endpoint never implemented",
    ("POST", "/api/notifications/{}/read"): "single mark-read never implemented; only /read-all exists",
    ("POST", "/api/daily-reports/manager/create-and-send"): "manager create-and-send never implemented (templates/reports/form.html)",
    ("GET", "/api/supervisor/present-children"): "superseded by /api/supervisor/attendance/status; caller is dead code",
    ("GET", "/api/manager/accounts"): "uncalled dead method in kinjo-api.js",
    ("GET", "/api/manager/alerts"): "uncalled dead method in kinjo-api.js",
    ("GET", "/api/manager/reports/submitted"): "uncalled dead method in kinjo-api.js",
    ("POST", "/api/manager/reports/{}/approve"): "uncalled dead method in kinjo-api.js",
    ("POST", "/api/manager/reports/{}/reject"): "uncalled dead method in kinjo-api.js",
    ("GET", "/api/manager/supervisors/stats"): "uncalled dead method in kinjo-api.js",
    ("GET", "/api/analytics/list-dimensions"): "advanced_analytics.js — orphaned template, no route renders it",
    ("GET", "/api/analytics/predictive"): "advanced_analytics.js — orphaned template",
    ("GET", "/api/analytics/scatter"): "advanced_analytics.js — orphaned template",
    ("GET", "/api/analytics/demographics"): "advanced_analytics.js — orphaned template",
    ("GET", "/api/analytics/government-report"): "advanced_analytics.js — orphaned template",
}

_SCAN_DIRS = (Path("templates"), Path("static/js"))
_API_CALL_RE = re.compile(r"""["'`](/api/[^"'`?\s]*)""")
# `api.post("/x")` / `this.get("/x")` — the verb precedes the URL.
_VERB_CALL_RE = re.compile(r"""\.(get|post|put|patch|delete)\(\s*["'`](/api/[^"'`?\s]*)""")


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}".replace("//", "/")


def _walk(router, prefix: str = ""):
    """FastAPI defers `include_router`, so nested routes hide behind opaque
    `_IncludedRouter` nodes: a flat `app.routes` scan sees ~27 of ~711 paths."""
    for route in getattr(router, "routes", []):
        if isinstance(route, Mount):
            continue
        if type(route).__name__ == "_IncludedRouter":
            ctx = getattr(route, "include_context", None)
            if ctx:
                yield from _walk(ctx.included_router, _join(prefix, ctx.prefix or ""))
            continue
        if isinstance(route, APIRoute):
            yield _join(prefix, route.path), route


def _param_types(route: APIRoute) -> dict:
    try:
        hints = typing.get_type_hints(route.endpoint)
    except Exception:
        return {}
    return hints


def _route_index():
    """(METHOD) -> list of (segments, param-name-per-segment, endpoint hints)."""
    index: dict[str, list] = {}
    for path, route in _walk(app):
        segments = path.strip("/").split("/")
        hints = _param_types(route)
        for method in route.methods or []:
            index.setdefault(method, []).append((segments, hints))
    return index


def _normalise(call: str) -> str:
    call = re.sub(r"\$\{[^}]*\}", "{}", call)
    call = re.sub(r"\{\{.*?\}\}", "{}", call)
    call = re.sub(r"\{[^{}]*\}", "{}", call)
    call = re.sub(r"'\s*\+\s*[^+]+\+\s*'", "{}", call)
    call = re.sub(r"\{+$", "{}", call)
    call = call.rstrip("/") or "/"
    return re.sub(r"/\d+(?=/|$)", "/{}", call)


def _segment_ok(call_seg: str, route_seg: str, hints: dict) -> bool:
    if not (route_seg.startswith("{") and route_seg.endswith("}")):
        return call_seg == route_seg or call_seg == "{}"
    if call_seg == "{}":
        return True  # runtime interpolation: could be anything
    # A literal in a param slot only resolves if the param's type can accept it.
    name = route_seg[1:-1].split(":")[0]
    declared = hints.get(name)
    if declared is int and not call_seg.lstrip("-").isdigit():
        return False
    return True


def _resolves(method, call: str, index) -> bool:
    """`method=None` means the call site's verb could not be determined, so the path
    must resolve under *some* method."""
    norm = _normalise(call)
    call_parts = norm.strip("/").split("/")
    methods = [method] if method else list(index)
    for m in methods:
        for segments, hints in index.get(m, []):
            if len(segments) != len(call_parts):
                continue
            if all(_segment_ok(c, r, hints) for c, r in zip(call_parts, segments)):
                return True
    # A base constant that gets a suffix appended at runtime.
    return any(
        len(segments) > len(call_parts)
        and all(_segment_ok(c, r, hints) for c, r in zip(call_parts, segments))
        for m in methods
        for segments, hints in index.get(m, [])
    )


def _method_for(window: str, url: str):
    """The call site's HTTP method, or None when it cannot be determined.

    Returning None (rather than assuming GET) matters: many `/api/...` strings are
    config constants or base URLs with no verb attached — e.g. auth.js's endpoint
    map — and defaulting those to GET reports live POST-only routes as dead.
    """
    verb = _VERB_CALL_RE.search(window)
    if verb and verb.group(2) == url:
        return verb.group(1).upper()
    explicit = re.search(r"""method:\s*['"](\w+)['"]""", window)
    if explicit:
        return explicit.group(1).upper()
    return None


def _iter_calls():
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".html", ".js"} or not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for lineno, line in enumerate(lines, 1):
                for match in _API_CALL_RE.finditer(line):
                    url = match.group(1)
                    # `method:` often sits on a later line of the same call.
                    window = "\n".join(lines[lineno - 1: lineno + 3])
                    yield path, lineno, url, _method_for(window, url)


@pytest.fixture(scope="module")
def index():
    return _route_index()


def test_route_walker_sees_the_whole_app(index):
    """Guards the walker: a flat `app.routes` scan sees ~27 paths, so a naive audit
    reports 'all clean' while missing 95% of the app."""
    total = sum(len(v) for v in index.values())
    assert total > 500, (
        f"only {total} (method,path) pairs discovered — the _IncludedRouter walk is "
        "broken, so every other check in this file would silently pass"
    )


def test_resolver_rejects_the_paths_this_file_was_written_to_catch(index):
    """Non-vacuity guard. A path-only, method-blind resolver passes 3 of these 4 —
    it would let a revert of the fixes sail through CI. If this test ever fails, the
    checker has decayed and the assertions below are worthless."""
    historical_bugs = [
        ("GET", "/api/governorates/{}/cities"),        # no such route at all
        ("POST", "/api/attendance/absence-requests/{}/cancel"),  # only create is under that prefix
        ("GET", "/api/daily-reports/submitted"),       # binds {report_id:int}; needs the type check
        ("POST", "/api/incidents/create"),             # /api/incidents/{id} is PUT-only; needs the method check
        ("DELETE", "/api/kindergartens/{}"),           # only GET is registered there; deletion is under /api/admin
    ]
    # Deliberately NOT asserted: `GET /api/attendance/absence-requests` genuinely
    # resolves — to `GET /api/attendance/{target_date}`. It was still a bug (the
    # wrong endpoint answers it, then 422s on the date), but it is a
    # wrong-endpoint hit, not an unroutable path, and this checker only proves the
    # latter. Claiming otherwise would overstate what it verifies.
    still_resolving = [
        f"{m} {p}" for m, p in historical_bugs if _resolves(m, p, index)
    ]
    assert not still_resolving, (
        "the resolver considers these dead paths valid, so it cannot catch the bugs "
        f"this file exists to prevent: {still_resolving}"
    )


def test_every_frontend_api_call_resolves_to_a_registered_route(index):
    unresolved = {}
    for path, lineno, call, method in _iter_calls():
        if _resolves(method, call, index):
            continue
        key = (method, _normalise(call))
        # An undetermined verb matches any allowlisted method for the same path.
        if any(
            _normalise(k[1]) == key[1] and (method is None or k[0] == method)
            for k in KNOWN_UNRESOLVED
        ):
            continue
        unresolved.setdefault(key, []).append(f"{path.as_posix()}:{lineno}")

    assert not unresolved, "frontend calls that no registered route can answer:\n" + "\n".join(
        f"  {m or 'ANY'} {c}\n    called from: {', '.join(sites)}"
        for (m, c), sites in sorted(unresolved.items(), key=lambda kv: (kv[0][1], kv[0][0] or ""))
    )


def test_known_unresolved_entries_are_still_unresolved(index):
    """Stops the allowlist outliving the gap: once a route exists, its entry must go
    or it silently exempts a live path from the check."""
    now_resolved = [f"{m} {p}" for (m, p) in KNOWN_UNRESOLVED if _resolves(m, p, index)]
    assert not now_resolved, (
        f"these paths are now registered — remove them from KNOWN_UNRESOLVED: {now_resolved}"
    )
