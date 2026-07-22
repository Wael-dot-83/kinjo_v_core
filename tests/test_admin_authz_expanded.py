"""Expanded runtime authorization sweep for the /api/admin surface.

test_admin_authz_sweep.py proves every /api/admin (method, path) rejects an
anonymous caller and an authenticated PARENT. This module extends that proof to
the other non-admin principals the launch review requires:

  * SUPERVISOR  — classroom-scoped; must never reach an admin API operation.
  * an INVALID bearer token (well-formed header, bogus token).
  * a MALFORMED Authorization header (``Bearer`` with no token).

Manager coverage is intentionally NOT a blanket assertion here: a few admin-
prefixed analytics/charts routes deliberately allow a manager
(``require_admin_or_manager``), so a blanket "manager is denied everywhere"
assertion would false-fail. Manager scope isolation is proven separately by
tests/test_manager_scope*.py.

Like the base sweep, reaching a route only requires building the path from its
template; a 401/403 must be decided before the handler looks anything up, so
filling ``{id}`` with an absent value is fine for an authorization assertion.
"""
from __future__ import annotations

import os
import secrets
import sys

import pytest

# Reuse the base sweep's _IncludedRouter walker and admin-surface enumeration.
sys.path.insert(0, os.path.dirname(__file__))
from test_admin_authz_sweep import ADMIN_PAIRS, PUBLIC_ADMIN_ROUTES, _call


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_supervisor(client, supervisor_token, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(client, method, path, {"Authorization": f"Bearer {supervisor_token}"})
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path} answered a SUPERVISOR with {resp.status_code} — "
        f"privilege escalation onto the admin surface. Body: {resp.text[:300]}"
    )


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_invalid_token(client, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(
        client, method, path, {"Authorization": "Bearer " + secrets.token_hex(24)}
    )
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path} accepted an INVALID bearer token with {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )


@pytest.mark.parametrize("method,path", ADMIN_PAIRS, ids=lambda v: str(v))
def test_admin_route_rejects_malformed_auth_header(client, method, path):
    if (method, path) in PUBLIC_ADMIN_ROUTES:
        pytest.skip(PUBLIC_ADMIN_ROUTES[(method, path)])
    resp = _call(client, method, path, {"Authorization": "Bearer"})
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path} accepted a MALFORMED Authorization header with "
        f"{resp.status_code}. Body: {resp.text[:300]}"
    )
