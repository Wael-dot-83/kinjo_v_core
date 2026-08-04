"""Tenant scoping on every analytics endpoint taking a caller-supplied kindergarten_id (SEC-05).

The gap analysis reported that "a manager could potentially access network-wide
analytics data" through the analytics explorer drilldowns. Static review did not
reproduce it:

  * `analytics_explorer.py:55` declares the router as
    `APIRouter(..., dependencies=[Depends(require_admin)])`, so no non-admin reaches
    any explorer route at all;
  * every `analytics_service.py` route accepting `kindergarten_id` is guarded by
    `validators.validate_admin_role`, `_ensure_admin_only`, a `_scope*` helper, or an
    inline role check.

Reading code is not proof, so this module *drives* each endpoint as every role. It
exists to keep the property true rather than to demonstrate a live defect: these
endpoints are network-wide analytics and must stay admin-only, and a future author
adding one without a guard should fail here.

Covered per endpoint: admin (allowed), manager own-tenant, manager foreign-tenant,
supervisor foreign-tenant, absent target, parent, anonymous.
"""
from __future__ import annotations

import pytest

import models
from conftest import bearer_headers

# Mounted at prefix="/api" over APIRouter(prefix="/analytics") — main.py:1188.
ANALYTICS_BASE = "/api/analytics"

# Endpoints whose kindergarten_id arrives in the path.
PATH_PARAM_ENDPOINTS = [
    f"{ANALYTICS_BASE}/benchmarks/{{kg}}",
    f"{ANALYTICS_BASE}/recommendations/{{kg}}",
]

# Three endpoints are multi-role by design: a manager or an assigned supervisor may
# read them, scoped to their own kindergarten. They are therefore *not* covered by the
# "non-admin is refused" assertions — their contract is that the caller-supplied
# kindergarten_id must never widen what a scoped caller sees, which
# test_scoped_caller_cannot_influence_result_via_parameter pins directly.
MULTI_ROLE_ENDPOINTS = [
    f"{ANALYTICS_BASE}/kpi",
    f"{ANALYTICS_BASE}/attendance",
    f"{ANALYTICS_BASE}/dashboard",
]

# Endpoints whose kindergarten_id arrives as a query parameter.
QUERY_PARAM_ENDPOINTS = [
    f"{ANALYTICS_BASE}/enrollments/summary",
    f"{ANALYTICS_BASE}/registration/analytics",
    f"{ANALYTICS_BASE}/registration/drilldown",
    f"{ANALYTICS_BASE}/attendance/summary",
    f"{ANALYTICS_BASE}/daily-reports/summary",
    f"{ANALYTICS_BASE}/safety/summary",
    f"{ANALYTICS_BASE}/staffing/summary",
    f"{ANALYTICS_BASE}/attendance/by-class",
    f"{ANALYTICS_BASE}/attendance/chronic-absence",
    f"{ANALYTICS_BASE}/daily-reports/supervisor-performance",
    f"{ANALYTICS_BASE}/enrollment/trends",
]

EXPLORER_ENDPOINTS = ["/api/admin/analytics/explorer/answer"]

ALL_QUERY = QUERY_PARAM_ENDPOINTS + EXPLORER_ENDPOINTS
ABSENT_KG_ID = 999_999

# A non-admin must never receive data. 401/403 are correct refusals; 404 is the
# canonical cross-tenant answer. 422 means the request never reached the guard
# (a required parameter was rejected first), which is also not a data leak.
REFUSED = {401, 403, 404, 422}


def _other_kindergarten(db, owner_kg_id) -> int:
    row = (
        db.query(models.Kindergarten.id)
        .filter(models.Kindergarten.id != owner_kg_id)
        .filter(models.Kindergarten.deleted_at.is_(None))
        .first()
    )
    if row:
        return row[0]
    other = models.Kindergarten(
        name_ar="حضانة مستأجر آخر",
        governorate="Irbid",
        district="قصبة إربد",
        area="منطقة",
        address_line="شارع 2",
        contact_phone="+962790000003",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    return other.id


# ---------------------------------------------------------------------------
# Query-parameter endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ALL_QUERY)
def test_manager_foreign_tenant_is_refused(client, manager_token, manager_user, test_db, path):
    other = _other_kindergarten(test_db, manager_user.kindergarten_id)
    resp = client.get(path, params={"kindergarten_id": other},
                      headers=bearer_headers(manager_token))
    assert resp.status_code in REFUSED, (
        f"{path} returned {resp.status_code} to a manager for kindergarten {other}"
    )


@pytest.mark.parametrize("path", ALL_QUERY)
def test_manager_own_tenant_is_still_refused_for_network_analytics(
    client, manager_token, manager_user, path
):
    """These are network-wide analytics, so admin-only is the intended contract —
    a manager is refused even for their own kindergarten."""
    resp = client.get(path, params={"kindergarten_id": manager_user.kindergarten_id},
                      headers=bearer_headers(manager_token))
    assert resp.status_code in REFUSED


@pytest.mark.parametrize("path", ALL_QUERY)
def test_supervisor_foreign_tenant_is_refused(
    client, supervisor_token, supervisor_user, test_db, path
):
    other = _other_kindergarten(test_db, supervisor_user.kindergarten_id)
    resp = client.get(path, params={"kindergarten_id": other},
                      headers=bearer_headers(supervisor_token))
    assert resp.status_code in REFUSED


@pytest.mark.parametrize("path", ALL_QUERY)
def test_absent_target_is_refused_for_non_admin(client, manager_token, path):
    resp = client.get(path, params={"kindergarten_id": ABSENT_KG_ID},
                      headers=bearer_headers(manager_token))
    assert resp.status_code in REFUSED


@pytest.mark.parametrize("path", ALL_QUERY)
def test_parent_is_refused(client, parent_token, path):
    resp = client.get(path, params={"kindergarten_id": 1},
                      headers=bearer_headers(parent_token))
    assert resp.status_code in REFUSED


@pytest.mark.parametrize("path", ALL_QUERY)
def test_anonymous_is_refused(client, path):
    resp = client.get(path, params={"kindergarten_id": 1})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Multi-role endpoints: scoped, not refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MULTI_ROLE_ENDPOINTS)
def test_scoped_caller_cannot_influence_result_via_parameter(
    client, manager_token, manager_user, test_db, path
):
    """A manager may read these, but only their own kindergarten.

    Asserting a status code is not enough here: two of these endpoints answer 200 to
    a foreign kindergarten_id because they silently substitute the caller's own scope.
    That is safe, but only if the substitution really happens — so compare the payload
    for own / foreign / absent targets. If the parameter can change what comes back,
    it is an access-control hole regardless of the status code.
    """
    other = _other_kindergarten(test_db, manager_user.kindergarten_id)
    headers = bearer_headers(manager_token)

    own = client.get(path, params={"kindergarten_id": manager_user.kindergarten_id},
                     headers=headers)
    foreign = client.get(path, params={"kindergarten_id": other}, headers=headers)
    absent = client.get(path, params={"kindergarten_id": ABSENT_KG_ID}, headers=headers)

    assert own.status_code == 200, f"{path} denied a manager their own kindergarten"

    for label, resp in (("foreign", foreign), ("absent", absent)):
        if resp.status_code == 200:
            assert resp.json() == own.json(), (
                f"{path} returned different data for a {label} kindergarten_id — the "
                "parameter is widening a scoped caller's view"
            )
        else:
            assert resp.status_code in REFUSED, (
                f"{path} answered {resp.status_code} for a {label} target"
            )


@pytest.mark.parametrize("path", MULTI_ROLE_ENDPOINTS)
def test_multi_role_endpoints_refuse_unscoped_callers(client, parent_token, path):
    """A parent has an empty allow-list. Empty must mean 'no access', not
    'unrestricted' — the fail-open that let a parent read any kindergarten's KPIs."""
    resp = client.get(path, params={"kindergarten_id": 1},
                      headers=bearer_headers(parent_token))
    assert resp.status_code in REFUSED, (
        f"{path} served a parent (status {resp.status_code}); an empty scope must deny"
    )


@pytest.mark.parametrize("path", MULTI_ROLE_ENDPOINTS)
def test_multi_role_endpoints_reject_anonymous(client, path):
    resp = client.get(path, params={"kindergarten_id": 1})
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize("path", MULTI_ROLE_ENDPOINTS)
def test_multi_role_endpoints_allow_admin(client, admin_token, sample_kindergarten, path):
    resp = client.get(path, params={"kindergarten_id": sample_kindergarten.id},
                      headers=bearer_headers(admin_token))
    assert resp.status_code not in (401, 403)


@pytest.mark.parametrize("path", ALL_QUERY)
def test_admin_retains_access(client, admin_token, sample_kindergarten, path):
    """The guards must not have been tightened into denying admins."""
    resp = client.get(path, params={"kindergarten_id": sample_kindergarten.id},
                      headers=bearer_headers(admin_token))
    assert resp.status_code not in (401, 403), (
        f"{path} denied an admin ({resp.status_code}) — the scope guard is too strict"
    )


# ---------------------------------------------------------------------------
# Path-parameter endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template", PATH_PARAM_ENDPOINTS)
def test_path_param_endpoints_refuse_non_admin(
    client, manager_token, supervisor_token, parent_token,
    manager_user, test_db, template
):
    other = _other_kindergarten(test_db, manager_user.kindergarten_id)
    for token, label in (
        (manager_token, "manager"),
        (supervisor_token, "supervisor"),
        (parent_token, "parent"),
    ):
        for kg in (other, manager_user.kindergarten_id, ABSENT_KG_ID):
            resp = client.get(template.format(kg=kg), headers=bearer_headers(token))
            assert resp.status_code in REFUSED, (
                f"{template.format(kg=kg)} returned {resp.status_code} to {label}"
            )


@pytest.mark.parametrize("template", PATH_PARAM_ENDPOINTS)
def test_path_param_endpoints_allow_admin(client, admin_token, sample_kindergarten, template):
    resp = client.get(template.format(kg=sample_kindergarten.id),
                      headers=bearer_headers(admin_token))
    assert resp.status_code not in (401, 403)


@pytest.mark.parametrize("template", PATH_PARAM_ENDPOINTS)
def test_path_param_endpoints_reject_anonymous(client, template):
    resp = client.get(template.format(kg=1))
    assert resp.status_code in (401, 403)
