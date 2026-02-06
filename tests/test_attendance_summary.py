from datetime import date

import pytest

import models
from dependencies import get_current_user
from main import app

pytestmark = [pytest.mark.integration, pytest.mark.p0]


def _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user):
    parent_profile = test_db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == parent_user.id
    ).first()
    child = models.Child(
        parent_id=parent_profile.id,
        first_name="Test",
        last_name="Child",
        gender=models.Gender.MALE,
        date_of_birth=date(2021, 1, 1),
        father_name="Father",
        mother_first_name="Mother",
        mother_last_name="Last",
        mother_nationality="Jordanian",
        media_consent=False,
        correspondence_flag=True,
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=sample_class.id,
        status=models.EnrollmentStatus.ACTIVE,
        source="WEB",
    )
    test_db.add(enrollment)

    attendance = models.AttendanceLog(
        child_id=child.id,
        class_id=sample_class.id,
        date=date.today(),
        status=models.AttendanceStatus.PRESENT,
        recorded_by=supervisor_user.id,
    )
    test_db.add(attendance)
    test_db.commit()

    return child


def test_get_attendance_summary_default_date(client, test_db, sample_kindergarten, sample_class, parent_user, supervisor_user):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: supervisor_user
    response = client.get("/api/attendance")
    assert response.status_code == 200
    data = response.json()
    assert data["total_children"] >= 1
    assert data["present_children"] >= 1
    assert data["attendance_rate"] >= 0
    app.dependency_overrides.clear()


def test_get_attendance_summary_today(client, test_db, sample_kindergarten, sample_class, parent_user, supervisor_user):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: supervisor_user
    response = client.get("/api/attendance/today")
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == date.today().isoformat()
    app.dependency_overrides.clear()


def test_get_attendance_summary_by_date(client, test_db, sample_kindergarten, sample_class, parent_user, supervisor_user):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: supervisor_user
    target_date = date.today().isoformat()
    response = client.get(f"/api/attendance/{target_date}")
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == target_date
    app.dependency_overrides.clear()
