"""Every /api/admin route must reject a non-admin caller.

Static inspection cannot settle this: the codebase guards admin access three
different ways — a `require_admin`/`RoleChecker` dependency, a `role_checker`
dependency, and a bare in-body `_ensure_admin(current_user)` call
(classification_service.py:84). A dependency-only audit reports the third form as
unguarded and a body-only audit reports the first two as unguarded, so both produce
false alarms. Actually calling each route is the only honest check.

This sweep drives every registered `/api/admin` (method, path) pair twice — once with
no credentials and once as an authenticated PARENT — and asserts neither is ever
answered with 2xx.

Note on what a pass means: reaching a route requires the path to be built from the
route template, so `{id}` params are filled with a value that is almost certainly
absent. That is fine for authorization: a 403/401 must be decided *before* the
handler looks anything up. A 404 would be a leak of existence, so it is treated as a
failure for unauthenticated callers only where the route is admin-only by definition.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, Mount

from main import app

# Public-by-design admin-prefixed endpoints. Password reset must work for a user who
# cannot log in, so it cannot require auth. Each entry needs a reason.
PUBLIC_ADMIN_ROUTES = {
    ("POST", "/api/admin/password-reset-request"): "pre-auth by design: user cannot log in yet",
    ("POST", "/api/admin/password-reset-confirm"): "pre-auth by design: consumes an emailed token",
}


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}".replace("//", "/")


def _walk(router, prefix: str = ""):
    """FastAPI defers include_router behind opaque `_IncludedRouter` nodes; a flat
    `app.routes` scan sees ~27 of ~698 pairs."""
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


def _fill(path: str) -> str:
    """Substitute a concrete value for each path param."""
    out = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            out.append("999999")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def _admin_pairs():
    seen = []
    for path, route in _walk(app):
        if not path.startswith("/api/admin"):
            continue
        for method in sorted(route.methods or []):
            if method in ("HEAD", "OPTIONS"):
                continue
            seen.append((method, path))
    return sorted(set(seen))


ADMIN_PAIRS = _admin_pairs()


def test_sweep_actually_found_the_admin_surface():
    """Non-vacuity guard: if the walker breaks, every assertion below passes trivially."""
    assert len(ADMIN_PAIRS) > 100, (
        f"only {len(ADMIN_PAIRS)} admin (method,path) pairs discovered — the "
        "_IncludedRouter walk is broken, so this sweep would silently verify nothing"
    )


def _call(client, method: str, path: str, headers: dict):
    return client.request(method, _fill(path), headers=headers, json={})


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_anonymous(client, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(client, method, path, {})
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path} answered an ANONYMOUS caller with {resp.status_code} — "
        f"admin data reachable without credentials. Body: {resp.text[:300]}"
    )


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_parent(client, parent_token, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(client, method, path, {"Authorization": f"Bearer {parent_token}"})
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path} answered an authenticated PARENT with {resp.status_code} — "
        f"privilege escalation. Body: {resp.text[:300]}"
    )
