"""Roster batch filing: transaction semantics and the authorisation matrix.

POST /api/daily-reports/batch lets a supervisor file a whole class in one
request. Two properties have to hold together, and they pull in opposite
directions:

  * a class is not all-or-nothing — one absent child, one duplicate, or one
    incomplete profile must not stop the rest of the class being filed; and
  * being a batch must not relax authorisation — every child still passes the
    same gates as the single-create endpoint.

Both paths share api.daily_reports_routes._authorize_report_for_child, so the
gates are asserted once against the helper and once through each endpoint, which
is what stops them drifting apart. routers/supervisor.py previously carried a
hand-written second creation path that drifted so far it constructed DailyReport
with columns the model never had.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import models
from conftest import bearer_headers

ABSENT_CHILD_ID = 999_999


def _child(db, parent_profile_id, first="طفل", last="اختبار"):
    child = models.Child(
        parent_id=parent_profile_id,
        first_name=first,
        last_name=last,
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="والد",
        mother_first_name="أم",
        mother_last_name="اختبار",
        mother_nationality="Jordanian",
        mother_national_id="1122334455",
        media_consent=True,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


def _enrol(db, child, kindergarten_id, class_id, status=models.EnrollmentStatus.ACTIVE):
    e = models.EnrollmentApplication(
        child_id=child.id, kindergarten_id=kindergarten_id, class_id=class_id, status=status
    )
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def roster_world(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child, parent_user):
    """Supervisor owns sample_class; three other children sit just outside it.

    own            -> assigned class, ACTIVE enrolment          (must succeed)
    other_class    -> same kindergarten, a class not assigned   (must be refused)
    other_kg       -> a different kindergarten entirely         (must be refused)
    """
    test_db.add(models.SupervisorAssignment(
        supervisor_id=supervisor_user.id,
        class_id=sample_class.id,
        start_date=date.today() - timedelta(days=30),
        end_date=None,
        is_primary=True,
    ))
    _enrol(test_db, sample_child, sample_kindergarten.id, sample_class.id)

    other_class = models.Class(
        kindergarten_id=sample_kindergarten.id,
        name_ar="الصف ب", name_en="Class B",
        class_code="B001", age_group="AGE_1_2",
        min_age_months=24, max_age_months=48, capacity_total=20, is_active=True,
    )
    test_db.add(other_class)
    test_db.commit()
    test_db.refresh(other_class)
    child_other_class = _child(test_db, parent_user.parent_profile.id, first="خارج")
    _enrol(test_db, child_other_class, sample_kindergarten.id, other_class.id)

    other_kg = models.Kindergarten(
        name_ar="حضانة أخرى", governorate="Irbid", district="قصبة إربد", area="منطقة",
        address_line="شارع 9", contact_phone="+962790000009",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(other_kg)
    test_db.commit()
    test_db.refresh(other_kg)
    foreign_class = models.Class(
        kindergarten_id=other_kg.id, name_ar="صف بعيد", name_en="Far Class",
        class_code="F001", age_group="AGE_1_2",
        min_age_months=24, max_age_months=48, capacity_total=20, is_active=True,
    )
    test_db.add(foreign_class)
    test_db.commit()
    test_db.refresh(foreign_class)
    child_other_kg = _child(test_db, parent_user.parent_profile.id, first="بعيد")
    _enrol(test_db, child_other_kg, other_kg.id, foreign_class.id)

    test_db.commit()
    return {
        "own": sample_child.id,
        "other_class": child_other_class.id,
        "other_kg": child_other_kg.id,
        "absent": ABSENT_CHILD_ID,
    }


def _payload(children, on=None):
    return {
        "date": (on or date.today()).isoformat(),
        "arrival_time": "08:00",
        "leave_time": "13:00",
        "breakfast": True,
        "lunch": True,
        "snack": False,
        "children": children,
    }


def _by_child(body):
    return {r["child_id"]: r for r in body["results"]}


# ---------------------------------------------------------------- batch shape


def test_mixed_batch_files_the_valid_child_and_refuses_the_rest(
    client, supervisor_token, roster_world, test_db
):
    """The full mix in one request: valid, duplicate, absent, other class,
    other kindergarten, skipped. One request, six independent verdicts."""
    w = roster_world
    # Pre-file the duplicate case so it is genuinely a duplicate.
    first = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([{"child_id": w["own"], "mood": "happy"}]),
    )
    assert first.status_code == 207, first.text
    assert _by_child(first.json())[w["own"]]["status"] == "created"

    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([
            {"child_id": w["own"], "mood": "normal"},          # duplicate now
            {"child_id": w["other_class"], "mood": "happy"},   # same KG, not my class
            {"child_id": w["other_kg"], "mood": "happy"},      # different KG
            {"child_id": w["absent"], "mood": "happy"},        # does not exist
            {"child_id": w["own"], "skip": True},              # explicit skip
        ]),
    )
    assert resp.status_code == 207, resp.text
    body = resp.json()

    # Every child is individually identifiable in the response.
    assert len(body["results"]) == 5
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert body["failed"] == 4

    codes = [r.get("code") for r in body["results"] if r["status"] == "failed"]
    assert 409 in codes, f"duplicate not reported as 409: {body['results']}"
    # Out-of-scope children answer 404, identical to a child that does not
    # exist; 403 here would be an existence oracle.
    assert codes.count(404) == 3, f"expected 3x404 (other class, other KG, absent): {body['results']}"
    assert 403 not in codes, f"a scope refusal leaked as 403: {body['results']}"

    # Nothing from the refused children reached the database.
    for key in ("other_class", "other_kg", "absent"):
        assert not test_db.query(models.DailyReport).filter(
            models.DailyReport.child_id == w[key]
        ).count(), f"a report was written for {key} despite being refused"


def test_one_failure_does_not_roll_back_its_siblings(
    client, supervisor_token, roster_world, test_db
):
    """The SAVEPOINT guarantee: a refused child must not cost the class."""
    w = roster_world
    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([
            {"child_id": w["other_kg"], "mood": "happy"},  # fails first
            {"child_id": w["own"], "mood": "happy"},       # must still be written
        ]),
    )
    assert resp.status_code == 207
    assert resp.json()["created"] == 1
    assert test_db.query(models.DailyReport).filter(
        models.DailyReport.child_id == w["own"]
    ).count() == 1, "the valid sibling was rolled back by the failure before it"


def test_retry_is_safe_and_idempotent_per_child(client, supervisor_token, roster_world, test_db):
    """Re-sending the same roster must not duplicate or 500 — it reports 409s."""
    w = roster_world
    payload = _payload([{"child_id": w["own"], "mood": "happy"}])
    a = client.post("/api/daily-reports/batch", headers=bearer_headers(supervisor_token), json=payload)
    b = client.post("/api/daily-reports/batch", headers=bearer_headers(supervisor_token), json=payload)
    assert a.json()["created"] == 1
    assert b.json()["created"] == 0
    assert _by_child(b.json())[w["own"]]["code"] == 409
    assert test_db.query(models.DailyReport).filter(
        models.DailyReport.child_id == w["own"]
    ).count() == 1, "retry created a second report for the same child and date"


def test_shared_values_apply_and_per_child_overrides_win(
    client, supervisor_token, roster_world, test_db
):
    """Shared arrival/leave/meals inherit; a row that sets its own wins."""
    w = roster_world
    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([{
            "child_id": w["own"], "mood": "tired",
            "leave_time": "11:30", "notes": "غادر مبكراً",
        }]),
    )
    assert resp.json()["created"] == 1
    report = test_db.query(models.DailyReport).filter(
        models.DailyReport.child_id == w["own"]
    ).one()
    assert report.arrival_time == "08:00", "shared arrival was not inherited"
    assert report.leave_time == "11:30", "per-child leave_time did not override the shared value"
    assert report.breakfast is True and report.snack is False, "shared meals were not inherited"
    assert report.mood == "tired"
    assert report.notes == "غادر مبكراً"
    assert report.status == models.DailyReportStatus.DRAFT, "batch must file drafts, not submissions"


def test_batch_size_is_bounded(client, supervisor_token, roster_world):
    """An oversized request is rejected by validation, not attempted."""
    w = roster_world
    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([{"child_id": w["own"]} for _ in range(61)]),
    )
    assert resp.status_code == 422, f"expected the 60-child cap to reject this, got {resp.status_code}"


def test_future_dates_are_refused(client, supervisor_token, roster_world):
    w = roster_world
    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([{"child_id": w["own"]}], on=date.today() + timedelta(days=1)),
    )
    assert resp.status_code == 422


# ------------------------------------------------------- authorisation matrix


@pytest.mark.parametrize("target,expected", [
    ("own", "created"),
    ("other_class", "failed"),
    ("other_kg", "failed"),
    ("absent", "failed"),
])
def test_supervisor_scope_matrix_batch(client, supervisor_token, roster_world, target, expected):
    w = roster_world
    resp = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(supervisor_token),
        json=_payload([{"child_id": w[target], "mood": "happy"}]),
    )
    assert resp.status_code == 207
    assert _by_child(resp.json())[w[target]]["status"] == expected


@pytest.mark.parametrize("target,expected_status", [
    ("own", 201),
    ("other_class", 404),
    ("other_kg", 404),
    ("absent", 404),
])
def test_supervisor_scope_matrix_single(client, supervisor_token, roster_world, target, expected_status):
    """The single-create path must answer the same way the batch does."""
    w = roster_world
    resp = client.post(
        "/api/daily-reports/create",
        headers=bearer_headers(supervisor_token),
        json={
            "child_id": w[target], "date": date.today().isoformat(),
            "arrival_time": "08:00", "leave_time": "13:00",
        },
    )
    assert resp.status_code == expected_status, resp.text


@pytest.mark.parametrize("role_token,role_name", [
    ("manager_token", "MANAGER"),
    ("admin_token", "ADMIN"),
    ("parent_token", "PARENT"),
])
def test_non_supervisor_roles_cannot_file_reports(
    client, request, roster_world, role_token, role_name
):
    """Both creation paths are supervisor-only by policy.

    Managers review and send reports to parents; parents must never gain staff
    privileges.

    ADMIN denial is a ratified product decision (2026-08-07), not an oversight,
    and this is therefore a POLICY test rather than an incidental assertion: a
    daily observational record must remain attributable to the staff role
    responsible for the child. Admins inspect, audit, correct through explicit
    administrative workflows, or impersonate where supported. Authoring through
    the supervisor endpoint would weaken provenance and drain the audit trail of
    meaning.

    If this assertion ever fails, the question is "did someone change the
    policy?", not "how do we make admins work again?".
    """
    token = request.getfixturevalue(role_token)
    w = roster_world
    batch = client.post(
        "/api/daily-reports/batch",
        headers=bearer_headers(token),
        json=_payload([{"child_id": w["own"], "mood": "happy"}]),
    )
    single = client.post(
        "/api/daily-reports/create",
        headers=bearer_headers(token),
        json={
            "child_id": w["own"], "date": date.today().isoformat(),
            "arrival_time": "08:00", "leave_time": "13:00",
        },
    )
    assert batch.status_code == 403, f"{role_name} was allowed into the batch endpoint"
    assert single.status_code == 403, f"{role_name} was allowed into the single-create endpoint"


def test_both_paths_use_the_same_authorisation_helper():
    """Guard against a third creation path being hand-written again."""
    import inspect

    from api import daily_reports_routes as mod

    for fn in (mod.create_daily_report, mod.create_daily_reports_batch):
        src = inspect.getsource(fn)
        assert "_authorize_report_for_child" in src, (
            f"{fn.__name__} does not call the shared authorisation helper; the gates "
            "will drift the way routers/supervisor.py's removed endpoint did"
        )


def test_out_of_scope_is_indistinguishable_from_absent(client, supervisor_token, roster_world):
    """Scope refusals must be byte-identical to a nonexistent child.

    Includes the case that used to leak: the class-assignment gate ran after the
    duplicate check, so a foreign-class child who already had a report answered
    409 — revealing both that the child existed and that someone had reported on
    them — before the assignment gate was reached.
    """
    w = roster_world
    absent = client.post(
        "/api/daily-reports/create",
        headers=bearer_headers(supervisor_token),
        json={"child_id": w["absent"], "date": date.today().isoformat(),
              "arrival_time": "08:00", "leave_time": "13:00"},
    )
    for key in ("other_class", "other_kg"):
        resp = client.post(
            "/api/daily-reports/create",
            headers=bearer_headers(supervisor_token),
            json={"child_id": w[key], "date": date.today().isoformat(),
                  "arrival_time": "08:00", "leave_time": "13:00"},
        )
        assert resp.status_code == absent.status_code, (
            f"{key} answered {resp.status_code} but an absent child answers "
            f"{absent.status_code} — the difference is an enumeration oracle"
        )
        assert resp.json() == absent.json(), (
            f"{key} body differs from the absent-child body: "
            f"{resp.text[:120]} vs {absent.text[:120]}"
        )


def test_foreign_child_with_an_existing_report_still_answers_not_found(
    client, supervisor_token, roster_world, test_db, supervisor_user
):
    """The exact ordering regression.

    The duplicate check used to run before the class-assignment gate, so a child
    outside the supervisor's class who already had a report answered 409 — which
    reveals the child exists AND that somebody reported on them. Written straight
    to the database because the API will not create it.
    """
    w = roster_world
    test_db.add(models.DailyReport(
        child_id=w["other_kg"],
        kindergarten_id=test_db.query(models.EnrollmentApplication)
            .filter(models.EnrollmentApplication.child_id == w["other_kg"]).one().kindergarten_id,
        date=date.today(),
        status=models.DailyReportStatus.DRAFT,
        submitted_by=supervisor_user.id,
        arrival_time="08:00", leave_time="13:00",
    ))
    test_db.commit()

    resp = client.post(
        "/api/daily-reports/create",
        headers=bearer_headers(supervisor_token),
        json={"child_id": w["other_kg"], "date": date.today().isoformat(),
              "arrival_time": "08:00", "leave_time": "13:00"},
    )
    assert resp.status_code == 404, (
        f"expected 404, got {resp.status_code} ({resp.text[:120]}) — the duplicate "
        "check is running before the scope gates again"
    )
    assert "already exists" not in resp.text
