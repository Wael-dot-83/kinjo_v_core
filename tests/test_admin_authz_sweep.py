"""Every /api/admin route must reject a non-admin caller.

Static inspection cannot settle this: the codebase guards admin access three
different ways — a `require_admin`/`RoleChecker` dependency, a `role_checker`
dependency, and a bare in-body `_ensure_admin(current_user)` call
(classification_service.py:84). A dependency-only audit reports the third form as
unguarded and a body-only audit reports the first two as unguarded, so both produce
false alarms. Actually calling each route is the only honest check.

This sweep drives every registered `/api/admin` (method, path) pair twice — once with
no credentials and once as an authenticated PARENT — and asserts every answer is an
explicit authorization failure (401 or 403).

The PARENT case sends a valid CSRF pair alongside the bearer token so the request
always clears the CSRF gate and the status can only come from authorization —
an earlier form of this sweep accepted any non-2xx, which let the CSRF middleware's
400 mask 43 of 45 state-changing routes before `require_admin` was ever consulted
(report 22 §3). Authorization coverage is only real if the answer is 401/403.

Note on what a pass means: reaching a route requires the path to be built from the
route template, so `{id}` params are filled with a value that is almost certainly
absent. That is fine for authorization: a 403/401 must be decided *before* the
handler looks anything up. A 404 would be a leak of existence, so it is treated as a
failure for unauthenticated callers only where the route is admin-only by definition.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, Mount

from conftest import csrf_pair
from main import app

# Public-by-design admin-prefixed endpoints. Password reset must work for a user who
# cannot log in, so it cannot require auth. Each entry needs a reason.
PUBLIC_ADMIN_ROUTES = {
    ("POST", "/api/admin/password-reset-request"): "pre-auth by design: user cannot log in yet",
    ("POST", "/api/admin/password-reset-confirm"): "pre-auth by design: consumes an emailed token",
}

# Routes whose handlers validate the payload BEFORE checking the role: a caller
# sending an empty body gets 422 from pydantic before the in-handler admin check
# can answer 403. That is genuine production behaviour for every caller, not an
# authz gap — but the sweep can only observe the role check if the request
# survives validation, so these routes get a minimally valid payload.
_KG_CREATE = {
    "name_ar": "حضانة الفحص",
    "governorate": "Amman",
    "district": "قصبة عمان",
    "area": "الدوار الأول",
    "address_line": "شارع الفحص 1",
    "contact_phone": "+962790000000",
}
VALIDATE_FIRST_PAYLOADS = {
    ("GET", "/api/admin/classification/detail"): {
        "params": {"entity_type": "KINDERGARTEN", "entity_id": 1}
    },
    ("PATCH", "/api/admin/kindergartens/{kindergarten_id}/freeze"): {
        "json": {"reason": "sweep probe"}
    },
    ("POST", "/api/admin/kindergartens"): {"json": dict(_KG_CREATE)},
    ("POST", "/api/admin/kindergartens/with-manager"): {
        "json": {
            "kindergarten": dict(_KG_CREATE),
            "manager": {
                "full_name": "Sweep Probe",
                "phone_number": "+962790000001",
                "username": "sweep_probe_mgr",
                "password": "Sweep123!",
            },
        }
    },
    ("POST", "/api/admin/kindergartens/{kindergarten_id}/assign-manager"): {
        "json": {"user_id": 999999}
    },
}

# Routes guarded by something other than the admin role, with the status a
# non-admin caller legitimately receives. exit-impersonation requires an active
# impersonation ticket — which only an impersonating admin possesses — so a
# PARENT gets 400 ("Not currently impersonating") before any data is touched.
TICKET_GUARDED_ROUTES = {
    ("POST", "/api/admin/exit-impersonation"): 400,
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
    override = VALIDATE_FIRST_PAYLOADS.get((method, path), {})
    kwargs = {"json": override.get("json", {})}
    if "params" in override:
        kwargs["params"] = override["params"]
    return client.request(method, _fill(path), headers=headers, **kwargs)


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_anonymous(client, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(client, method, path, {})
    assert resp.status_code in (401, 403), (
        f"{method} {path} answered an ANONYMOUS caller with {resp.status_code} — "
        f"expected an explicit auth failure (401/403). Body: {resp.text[:300]}"
    )


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_parent(client, parent_token, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    # Valid CSRF pair included so the status reflects authorization, never the
    # CSRF gate (report 22 §3: 400s once masked 43 of 45 state-changing routes).
    headers = {"Authorization": f"Bearer {parent_token}", **csrf_pair()}
    resp = _call(client, method, path, headers)
    ticket_guarded = TICKET_GUARDED_ROUTES.get((method, path))
    if ticket_guarded is not None:
        assert resp.status_code == ticket_guarded, (
            f"{method} {path} is ticket-guarded: expected {ticket_guarded} for a "
            f"caller without the ticket, got {resp.status_code}. Body: {resp.text[:300]}"
        )
        return
    assert resp.status_code in (401, 403), (
        f"{method} {path} answered an authenticated PARENT with {resp.status_code} — "
        f"expected an explicit authorization failure (401/403); anything else "
        f"means the route either leaked data or was never reached by the auth "
        f"check. Body: {resp.text[:300]}"
    )
