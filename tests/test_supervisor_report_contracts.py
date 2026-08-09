"""Contracts that the supervisor daily-reporting UI depends on.

Two regressions are pinned here, both of which took the feature down completely
while every existing test stayed green.

1. date_of_birth omitted from the supervisor children endpoints.

   templates/reports/form.html filters the child list through
   ChildAgeValidator.isEligible(child.date_of_birth) as an age-policy safety
   net. The endpoints did not serialise the field, so the predicate was falsy
   for every row, the picker rendered "no children available", and a supervisor
   could not file a daily report at all. Nothing failed loudly: an empty list is
   indistinguishable from an empty class.

2. The child-detail serialiser reading columns that do not exist.

   get_supervisor_child_details returned report.meals / .sleep / .behavior /
   .general_notes. DailyReport has none of them, so the endpoint raised
   AttributeError and answered 500 — for the supervisor's OWN children, not just
   out-of-scope ones. Meals are four booleans and sleep is a start/end pair.

The second test is a model-contract test on purpose: it asserts against
DailyReport's real columns rather than against a response body, so schema drift
cannot quietly recreate the failure.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import inspect as sa_inspect

import models
from conftest import bearer_headers

# Fields the daily-report picker and the class roster both read off each child.
# date_of_birth is the one that took the feature down; the others are what the
# roster renders a row from.
REQUIRED_CHILD_FIELDS = {"id", "first_name", "last_name", "date_of_birth", "class_id", "class_name"}

SUPERVISOR_CHILD_LIST_ENDPOINTS = [
    "/api/supervisor/children",
    "/api/supervisor/children/detailed",
]


@pytest.fixture
def supervisor_with_class(test_db, supervisor_user, sample_class, sample_child, sample_kindergarten):
    """A supervisor assigned to a class that actually contains a child.

    get_supervisor_child_ids walks assignment -> class -> active enrolment, so
    all three links have to exist or the endpoints legitimately return [] and the
    test would pass for the wrong reason.
    """
    assignment = models.SupervisorAssignment(
        supervisor_id=supervisor_user.id,
        class_id=sample_class.id,
        start_date=date.today() - timedelta(days=30),
        end_date=None,
        is_primary=True,
    )
    test_db.add(assignment)

    enrollment = models.EnrollmentApplication(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=sample_class.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add(enrollment)
    test_db.commit()
    return supervisor_user


@pytest.mark.parametrize("path", SUPERVISOR_CHILD_LIST_ENDPOINTS)
def test_supervisor_children_expose_date_of_birth(
    client, supervisor_token, supervisor_with_class, path
):
    """Remove date_of_birth again and this fails instead of the UI silently emptying."""
    resp = client.get(path, headers=bearer_headers(supervisor_token))
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:200]}"

    children = resp.json()["children"]
    assert children, (
        f"{path} returned no children for a supervisor who is assigned to a class "
        "containing an actively enrolled child — the fixture, not the endpoint, may be wrong"
    )

    for child in children:
        missing = REQUIRED_CHILD_FIELDS - set(child)
        assert not missing, f"{path} child {child.get('id')} is missing {sorted(missing)}"
        assert child["date_of_birth"], (
            f"{path} child {child.get('id')} has a null date_of_birth; the client age "
            "filter treats that as ineligible and drops the row"
        )


def test_child_detail_serialiser_only_reads_real_daily_report_columns():
    """Every DailyReport attribute the child-detail endpoint touches must exist.

    Asserted against the mapper rather than a live response so this fails at the
    moment a column is renamed, not only when someone happens to call the route.
    """
    columns = {c.key for c in sa_inspect(models.DailyReport).mapper.column_attrs}

    # Exactly what routers/supervisor.py::get_supervisor_child_details reads.
    read_by_serialiser = {
        "id", "date", "arrival_time", "leave_time", "mood",
        "breakfast", "snack", "milk", "lunch",
        "nap_start", "nap_end", "nap_duration_minutes",
        "activities", "health_notes", "notes", "status",
    }
    missing = read_by_serialiser - columns
    assert not missing, (
        f"get_supervisor_child_details reads DailyReport columns that do not exist: "
        f"{sorted(missing)} — this is the shape of the bug that made it answer 500"
    )

    # The obsolete names the broken version used, kept explicit so a future schema
    # change that introduces one of them is a deliberate decision.
    # class_id is intentionally present: it is the immutable class snapshot
    # used to authorize reports after a child changes class.
    never_existed = {"meals", "sleep", "behavior", "general_notes", "supervisor_id"}
    resurrected = never_existed & columns
    assert not resurrected, (
        f"DailyReport now has {sorted(resurrected)}; the supervisor serialiser and the "
        "removed POST endpoint assumed these existed. Revisit both before relying on them."
    )
