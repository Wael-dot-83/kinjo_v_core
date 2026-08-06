"""A manager may read child records only for their own kindergarten (SEC).

Two endpoints returned another kindergarten's child records to any manager:

  GET /api/children/{child_id}/observations   (api/children.py)
      Branched on PARENT and SUPERVISOR and had no MANAGER branch at all, so a
      manager fell through to the unfiltered query.

  GET /api/children/{child_id}/portfolio      (api/portfolio.py)
      Branched on PARENT, then `else: # Staff can see all portfolios` — which
      is exactly what it did, across tenants.

Reproduced against the development dataset before the fix: manager1, bound to
kindergarten 1, read all four developmental observations for child 7 (enrolled
in kindergarten 3) including assessment text and mastery level, plus that
child's named portfolio entry.

Why these tests are endpoint-level rather than unit tests on ManagerScope: the
guard was not wrong, it was *absent*. tests/test_manager_scope.py exercises
ManagerScope directly and passed throughout, because neither endpoint ever
called it. Only a request through the app catches a missing call.

A third endpoint, GET /api/children/{child_id}/health-alerts, already scoped
correctly but refused with 403 "Child not in your kindergarten scope" — which
still confirms the child exists in another kindergarten, so IDs could be walked
to map a rival tenant's roll. Same existence-leak class, so it was conformed to
the 404 policy rather than left as a documented exception. All three are pinned
here together and cannot drift apart again.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from conftest import bearer_headers

# Every child-scoped read, and the one refusal they all share.
#
# 404 is the house policy: api/children.py::_authorize_child_access states it
# ("Staff lookups deliberately return 404 outside their kindergarten so numeric
# child IDs cannot be used to discover another tenant's records") and
# dependencies.ManagerScope repeats it ("404, not 403 — do not reveal that
# another tenant's resource exists").
#
# health-alerts previously answered 403 "Child not in your kindergarten scope".
# Its scope check was correct; the refusal was not — that wording confirms the
# child exists in another kindergarten, so IDs could still be walked to map a
# rival tenant's roll. Same existence-leak class as the two missing guards, now
# conformed to the same policy.
#
# Kept as one list so the three cannot drift apart again: a future endpoint that
# stops refusing, or refuses differently, fails here.
CHILD_SCOPED_PATHS = [
    "/api/children/{child_id}/observations",
    "/api/children/{child_id}/portfolio",
    "/api/children/{child_id}/health-alerts",
]
OUT_OF_SCOPE_STATUS = 404


@pytest.fixture
def foreign_child(test_db, manager_user, parent_user):
    """A child with an ACTIVE enrolment in a kindergarten the manager does not own.

    Built rather than skipped-if-absent: the vulnerability only exists for a
    child who really is enrolled somewhere else, so a skip would leave it
    unexercised while the suite still reported green.
    """
    other_kg = models.Kindergarten(
        name_ar="حضانة مستأجر آخر",
        governorate="Irbid",
        district="قصبة إربد",
        area="منطقة",
        address_line="شارع 3",
        contact_phone="+962790000003",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(other_kg)
    test_db.commit()
    test_db.refresh(other_kg)
    assert other_kg.id != manager_user.kindergarten_id

    child = models.Child(
        parent_id=parent_user.parent_profile.id,
        first_name="رهف",
        last_name="المستأجر",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 4),
        father_name="والد رهف",
        mother_first_name="سميرة",
        mother_last_name="المستأجر",
        mother_nationality="Jordanian",
        mother_national_id="1122334455",
        media_consent=False,
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=other_kg.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add(enrollment)
    test_db.commit()

    return child


@pytest.mark.parametrize("path", CHILD_SCOPED_PATHS)
def test_manager_cannot_read_foreign_child_records(
    client, manager_token, foreign_child, path
):
    """Refused — and refused as 404, so the child is indistinguishable from one
    that does not exist. A 403 here would still be an existence oracle."""
    resp = client.get(
        path.format(child_id=foreign_child.id), headers=bearer_headers(manager_token)
    )
    assert resp.status_code == OUT_OF_SCOPE_STATUS, (
        f"{path} returned {resp.status_code} for a child in another kindergarten; "
        f"body={resp.text[:300]}"
    )


def test_out_of_scope_is_indistinguishable_from_absent(
    client, manager_token, foreign_child
):
    """The whole point of 404: an existing-but-foreign child and a child that was
    never created must produce byte-identical answers."""
    absent_id = 999_999
    for path in CHILD_SCOPED_PATHS:
        foreign = client.get(
            path.format(child_id=foreign_child.id), headers=bearer_headers(manager_token)
        )
        absent = client.get(
            path.format(child_id=absent_id), headers=bearer_headers(manager_token)
        )
        assert foreign.status_code == absent.status_code, (
            f"{path}: foreign child gave {foreign.status_code} but absent child gave "
            f"{absent.status_code} — the difference is an enumeration oracle"
        )
        assert foreign.text == absent.text, (
            f"{path}: response bodies differ between a foreign and an absent child; "
            f"foreign={foreign.text[:150]} absent={absent.text[:150]}"
        )


@pytest.mark.parametrize("path", CHILD_SCOPED_PATHS)
def test_manager_can_still_read_own_child_records(
    client, manager_token, sample_child, active_enrollment, path
):
    """The fix must not close the door on the manager's own kindergarten."""
    resp = client.get(
        path.format(child_id=sample_child.id), headers=bearer_headers(manager_token)
    )
    assert resp.status_code == 200, (
        f"{path} returned {resp.status_code} for a child in the manager's OWN "
        f"kindergarten; body={resp.text[:300]}"
    )


@pytest.mark.parametrize("path", CHILD_SCOPED_PATHS)
def test_admin_is_not_restricted_by_kindergarten(
    client, admin_token, foreign_child, path
):
    """Admins are deliberately unscoped; the fix must not have caught them."""
    resp = client.get(
        path.format(child_id=foreign_child.id), headers=bearer_headers(admin_token)
    )
    assert resp.status_code == 200, (
        f"{path} returned {resp.status_code} for an ADMIN; admins are network-wide. "
        f"body={resp.text[:300]}"
    )


def test_observations_body_carries_no_foreign_records(
    client, manager_token, foreign_child, test_db, supervisor_user
):
    """Belt and braces: a status code alone would still pass if the endpoint
    answered 403 but leaked a body. Give the foreign child a real observation
    first, so an unscoped query would have something to leak."""
    obs = models.Observation(
        child_id=foreign_child.id,
        domain=models.LearningDomain.PHYSICAL,
        observation_text="يتقن العد حتى 20 بثقة",
        mastery_level=models.MasteryLevel.ON_TRACK,
        observed_by=supervisor_user.id,
        observed_at=datetime.now(timezone.utc),
    )
    test_db.add(obs)
    test_db.commit()

    resp = client.get(
        f"/api/children/{foreign_child.id}/observations",
        headers=bearer_headers(manager_token),
    )
    assert resp.status_code == 404
    assert "يتقن العد" not in resp.text
