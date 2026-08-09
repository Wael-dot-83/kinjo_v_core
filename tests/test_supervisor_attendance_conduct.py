"""Tests for Supervisor Attendance Conduct & Endpoints.

Verifies:
1. GET /supervisor/attendance HTML page loads with 200 for supervisors and redirects non-supervisors.
2. GET /api/supervisor/attendance returns children, status badges, and statistics.
3. GET /api/supervisor/attendance/summary & /status endpoints.
4. POST /api/supervisor/attendance supports:
   - check_in / present
   - check_out / checked_out
   - mark_absent / absent
   - late with late_reason
5. Scope enforcement: supervisors cannot record attendance for children outside assigned classes.
6. Role enforcement: non-supervisors receive 403.
"""
from datetime import date, timedelta
import pytest
import models
from conftest import bearer_headers


def _setup_supervisor_class_and_child(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    sample_child.mother_first_name = sample_child.mother_first_name or "أمي"
    sample_child.mother_last_name = sample_child.mother_last_name or "اختبار"
    sample_child.mother_nationality = sample_child.mother_nationality or "Jordanian"
    sample_child.father_name = sample_child.father_name or "أبي"
    if not sample_child.date_of_birth:
        sample_child.date_of_birth = date.today() - timedelta(days=365 * 3)
    test_db.commit()

    enrollment = test_db.query(models.EnrollmentApplication).filter_by(child_id=sample_child.id).first()
    if not enrollment:
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()
    else:
        enrollment.status = models.EnrollmentStatus.ACTIVE
        test_db.commit()

    assignment = test_db.query(models.SupervisorAssignment).filter_by(
        supervisor_id=supervisor_user.id,
        class_id=sample_class.id
    ).first()
    if not assignment:
        assignment = models.SupervisorAssignment(
            supervisor_id=supervisor_user.id,
            class_id=sample_class.id,
            start_date=date.today() - timedelta(days=10),
            end_date=None,
            is_primary=True,
        )
        test_db.add(assignment)
        test_db.commit()


def test_supervisor_attendance_page_access(client, supervisor_user, parent_user):
    from main import app
    from scripts.compat.frontend_orig import get_current_user_or_redirect

    # HTML page accessible by supervisor
    app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
    try:
        res = client.get("/supervisor/attendance")
        assert res.status_code == 200
        assert "تسجيل الحضور" in res.text or "Attendance" in res.text
    finally:
        app.dependency_overrides.clear()

    # Non-supervisor is redirected
    app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
    try:
        res_parent = client.get("/supervisor/attendance", follow_redirects=False)
        assert res_parent.status_code in (302, 303, 307, 403)
    finally:
        app.dependency_overrides.clear()


def test_get_supervisor_attendance_api(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _setup_supervisor_class_and_child(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    res = client.get("/api/supervisor/attendance", headers=bearer_headers(supervisor_token))
    assert res.status_code == 200
    data = res.json()
    assert "children" in data
    assert "present" in data
    assert "absent" in data
    assert "total" in data

    children_ids = [c["id"] for c in data["children"]]
    assert sample_child.id in children_ids


def test_supervisor_attendance_summary_and_status(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _setup_supervisor_class_and_child(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    res_sum = client.get("/api/supervisor/attendance/summary", headers=bearer_headers(supervisor_token))
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert "present" in sum_data
    assert "absent" in sum_data

    res_st = client.get("/api/supervisor/attendance/status", headers=bearer_headers(supervisor_token))
    assert res_st.status_code == 200
    st_data = res_st.json()
    assert "children" in st_data


def test_supervisor_attendance_checkin_checkout_conduct(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _setup_supervisor_class_and_child(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    # Clean existing logs for child today
    from routers.supervisor import _ksa_now
    today_val = _ksa_now().date()
    test_db.query(models.AttendanceLog).filter_by(child_id=sample_child.id, date=today_val).delete()
    test_db.commit()

    # 1. Check in
    payload_in = {
        "child_id": sample_child.id,
        "action": "check_in"
    }
    res_in = client.post("/api/supervisor/attendance", json=payload_in, headers=bearer_headers(supervisor_token))
    assert res_in.status_code == 200, res_in.text
    in_data = res_in.json()
    assert in_data["attendance_status"] == "present"
    assert in_data["check_in_time"] is not None

    # 2. Check out
    payload_out = {
        "child_id": sample_child.id,
        "action": "check_out"
    }
    res_out = client.post("/api/supervisor/attendance", json=payload_out, headers=bearer_headers(supervisor_token))
    assert res_out.status_code == 200, res_out.text
    out_data = res_out.json()
    assert out_data["attendance_status"] == "checked_out"
    assert out_data["check_out_time"] is not None


def test_supervisor_attendance_mark_absent_and_late(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _setup_supervisor_class_and_child(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    from routers.supervisor import _ksa_now
    today_val = _ksa_now().date()
    test_db.query(models.AttendanceLog).filter_by(child_id=sample_child.id, date=today_val).delete()
    test_db.commit()

    # 1. Mark Absent
    payload_absent = {
        "child_id": sample_child.id,
        "action": "mark_absent"
    }
    res_absent = client.post("/api/supervisor/attendance", json=payload_absent, headers=bearer_headers(supervisor_token))
    assert res_absent.status_code == 200, res_absent.text
    assert res_absent.json()["attendance_status"] == "absent"

    # 2. Mark Late with reason
    payload_late = {
        "child_id": sample_child.id,
        "action": "late",
        "late_reason": "Traffic delay"
    }
    res_late = client.post("/api/supervisor/attendance", json=payload_late, headers=bearer_headers(supervisor_token))
    assert res_late.status_code == 200, res_late.text
    late_data = res_late.json()
    assert late_data["attendance_status"] == "late"
    assert late_data["late_reason"] == "Traffic delay"


def test_supervisor_attendance_scope_refusal(client, supervisor_token, test_db, sample_kindergarten, parent_user):
    # Create child outside supervisor's assigned class
    other_class = models.Class(
        name_ar="شعبة غير مسندة",
        name_en="Unassigned Class",
        class_code="UNASSIGNED-01",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        kindergarten_id=sample_kindergarten.id
    )
    test_db.add(other_class)
    test_db.commit()

    foreign_child = models.Child(
        parent_id=parent_user.id,
        first_name="أجنبي",
        last_name="طفل",
        mother_first_name="أمي",
        mother_last_name="أجنبية",
        mother_nationality="Jordanian",
        father_name="أب",
        gender="MALE",
        date_of_birth=date.today() - timedelta(days=365*3)
    )
    test_db.add(foreign_child)
    test_db.commit()

    foreign_enrollment = models.EnrollmentApplication(
        child_id=foreign_child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=other_class.id,
        status=models.EnrollmentStatus.ACTIVE
    )
    test_db.add(foreign_enrollment)
    test_db.commit()

    # Attempt to record attendance for out-of-scope child
    payload = {
        "child_id": foreign_child.id,
        "action": "check_in"
    }
    res = client.post("/api/supervisor/attendance", json=payload, headers=bearer_headers(supervisor_token))
    assert res.status_code == 403
