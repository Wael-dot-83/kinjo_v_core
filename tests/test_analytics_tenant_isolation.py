"""Tenant isolation on the predictive/trend analytics endpoints (SEC-01).

Two defects are pinned here.

1. **Enumeration via status code.** dependencies.py's canonical guard answers a
   cross-tenant target with 404 — "do not reveal that another tenant's resource
   exists" — but these endpoints answered 403, so a scoped user could tell an
   existing kindergarten from a non-existent one by the code alone.

2. **Supervisor bypass.** The guard read

       if role not in [ADMIN, SUPERVISOR] and user.kindergarten_id != kindergarten_id

   which exempts SUPERVISOR from the ownership check entirely: a supervisor could
   request predictions for *any* kindergarten. The gap analysis described only the
   manager case; this is wider.

Both are asserted for every affected endpoint rather than a representative one,
because the guard was copy-pasted six times and drifted.
"""
from __future__ import annotations

import pytest

import models
from conftest import bearer_headers

# Every endpoint that takes a caller-supplied kindergarten_id in this module.
SCOPED_ENDPOINTS = [
    "/api/analytics/predict/attendance",
    "/api/analytics/predict/incidents",
    "/api/analytics/predict/capacity",
    "/api/analytics/predict/enrollment",
    "/api/analytics/predictive-insights",
]

# An id that certainly belongs to nobody.
ABSENT_KG_ID = 999_999


def _other_kindergarten(db, owner_kg_id: int) -> int:
    """A real kindergarten id that the caller does not own.

    Created here rather than skipped when the fixture set has only one: the whole
    point of these tests is the *exists but is not yours* case, and a skip would
    leave the vulnerability unexercised while the suite still reported green.
    """
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
        contact_phone="+962790000002",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    return other.id


@pytest.mark.parametrize("path", SCOPED_ENDPOINTS)
def test_manager_cross_tenant_is_indistinguishable_from_absent(
    client, manager_token, manager_user, test_db, path
):
    """A kindergarten that exists-but-is-not-mine must look exactly like one that
    does not exist. Any difference is an enumeration oracle."""
    other = _other_kindergarten(test_db, manager_user.kindergarten_id)

    headers = bearer_headers(manager_token)
    existing = client.get(path, params={"kindergarten_id": other}, headers=headers)
    absent = client.get(path, params={"kindergarten_id": ABSENT_KG_ID}, headers=headers)

    assert existing.status_code == 404, (
        f"{path} answered {existing.status_code} for another tenant's kindergarten; "
        "403 reveals that the resource exists"
    )
    assert absent.status_code == 404
    assert existing.json() == absent.json(), (
        "response bodies differ between 'exists but not yours' and 'does not exist'"
    )


# predict/enrollment admits ADMIN and MANAGER only, so a supervisor is stopped by the
# role gate before the tenant gate is reached. That 403 is not an oracle: it is the
# same answer for every kindergarten id, including the supervisor's own — asserted by
# test_supervisor_role_denial_leaks_nothing below.
SUPERVISOR_SCOPED_ENDPOINTS = [p for p in SCOPED_ENDPOINTS if not p.endswith("/enrollment")]
SUPERVISOR_FORBIDDEN_ENDPOINTS = ["/api/analytics/predict/enrollment"]


@pytest.mark.parametrize("path", SUPERVISOR_SCOPED_ENDPOINTS)
def test_supervisor_cannot_read_another_kindergarten(
    client, supervisor_token, supervisor_user, test_db, path
):
    """SUPERVISOR was exempted from the ownership check entirely."""
    other = _other_kindergarten(test_db, supervisor_user.kindergarten_id)

    resp = client.get(
        path, params={"kindergarten_id": other}, headers=bearer_headers(supervisor_token)
    )
    assert resp.status_code == 404, (
        f"{path} let a supervisor read kindergarten {other} "
        f"(status {resp.status_code}); supervisors are scoped to their own"
    )


@pytest.mark.parametrize("path", SUPERVISOR_FORBIDDEN_ENDPOINTS)
def test_supervisor_role_denial_leaks_nothing(
    client, supervisor_token, supervisor_user, test_db, path
):
    """A role-level refusal must not vary with the target, or it becomes an oracle."""
    other = _other_kindergarten(test_db, supervisor_user.kindergarten_id)
    headers = bearer_headers(supervisor_token)

    own = client.get(
        path, params={"kindergarten_id": supervisor_user.kindergarten_id}, headers=headers
    )
    foreign = client.get(path, params={"kindergarten_id": other}, headers=headers)
    absent = client.get(path, params={"kindergarten_id": ABSENT_KG_ID}, headers=headers)

    assert own.status_code == foreign.status_code == absent.status_code == 403
    assert own.json() == foreign.json() == absent.json(), (
        "role denial differs by target, which reveals whether the target exists"
    )


@pytest.mark.parametrize("path", SCOPED_ENDPOINTS)
def test_parent_has_no_access_at_all(client, parent_token, path):
    """A parent is not a scoped analytics role; 403 is correct and leaks nothing."""
    resp = client.get(
        path, params={"kindergarten_id": 1}, headers=bearer_headers(parent_token)
    )
    assert resp.status_code in (403, 404)


@pytest.mark.parametrize("path", SCOPED_ENDPOINTS)
def test_anonymous_is_rejected(client, path):
    resp = client.get(path, params={"kindergarten_id": 1})
    assert resp.status_code in (401, 403)
