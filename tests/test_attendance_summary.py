from datetime import date, timedelta

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
        date_of_birth=date.today() - timedelta(days=365 * 3),
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


def _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user):
    parent_profile = test_db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == parent_user.id
    ).first()

    second_kindergarten = models.Kindergarten(
        name_ar="روضة المستقبل",
        name_en="Future Kindergarten",
        license_number="LIC-2026-099",
        governorate="Irbid",
        city="Irbid",
        area="University Street",
        address_line="456 Second Street",
        contact_phone="+962792222222",
        contact_email="future@kg.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    test_db.add(second_kindergarten)
    test_db.commit()
    test_db.refresh(second_kindergarten)

    second_class = models.Class(
        kindergarten_id=second_kindergarten.id,
        name_ar="الصف الثاني",
        name_en="Class B",
        class_code="B001",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(second_class)
    test_db.commit()
    test_db.refresh(second_class)

    child = models.Child(
        parent_id=parent_profile.id,
        first_name="Second",
        last_name="Child",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="Father Two",
        mother_first_name="Mother",
        mother_last_name="Two",
        mother_nationality="Jordanian",
        media_consent=False,
        correspondence_flag=True,
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=second_kindergarten.id,
        class_id=second_class.id,
        status=models.EnrollmentStatus.ACTIVE,
        source="WEB",
    )
    test_db.add(enrollment)

    attendance = models.AttendanceLog(
        child_id=child.id,
        class_id=second_class.id,
        date=date.today(),
        status=models.AttendanceStatus.PRESENT,
        recorded_by=supervisor_user.id,
    )
    test_db.add(attendance)
    test_db.commit()

    return second_kindergarten


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


def test_attendance_history_summary_admin_all_kindergartens(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "all_kindergartens"
    assert data["meta"]["scope"]["kindergarten_count"] >= 2
    assert data["totals"]["present"] == 2
    assert data["totals"]["total"] == 2
    assert len(data["rows"]) == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_specific_kindergarten(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&kindergarten_id={sample_kindergarten.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "specific_kindergarten"
    assert data["meta"]["scope"]["kindergarten_id"] == sample_kindergarten.id
    assert data["totals"]["present"] == 1
    assert data["totals"]["total"] == 1
    assert len(data["rows"]) == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_filter_by_governorate(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&governorate=Irbid"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "filtered_kindergartens"
    assert data["meta"]["scope"]["kindergarten_count"] == 1
    assert data["meta"]["scope"]["filters"]["governorate"] == "Irbid"
    assert data["totals"]["present"] == 1
    assert data["totals"]["total"] == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_filter_by_kindergarten_name(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&kindergarten_name=Future"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "filtered_kindergartens"
    assert data["meta"]["scope"]["kindergarten_count"] == 1
    assert data["meta"]["scope"]["filters"]["kindergarten_name"] == "Future"
    assert data["totals"]["present"] == 1
    assert data["totals"]["total"] == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_filter_by_governorate_and_name(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&governorate=Irbid&kindergarten_name=Future"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "filtered_kindergartens"
    assert data["meta"]["scope"]["kindergarten_count"] == 1
    assert data["meta"]["scope"]["filters"]["governorate"] == "Irbid"
    assert data["meta"]["scope"]["filters"]["kindergarten_name"] == "Future"
    assert data["totals"]["present"] == 1
    assert data["totals"]["total"] == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_filter_by_child_name(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&child_name=Second Child"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "all_kindergartens"
    assert data["meta"]["scope"]["kindergarten_count"] >= 2
    assert data["meta"]["scope"]["filters"]["child_name"] == "Second Child"
    assert data["totals"]["present"] == 1
    assert data["totals"]["total"] == 1
    app.dependency_overrides.clear()


def test_attendance_history_summary_admin_specific_kindergarten_with_child_filter(
    client,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
    supervisor_user,
    admin_user,
):
    _seed_attendance(test_db, sample_kindergarten, sample_class, parent_user, supervisor_user)
    _seed_second_kindergarten_attendance(test_db, parent_user, supervisor_user)

    app.dependency_overrides[get_current_user] = lambda: admin_user
    target_date = date.today().isoformat()
    response = client.get(
        f"/api/attendance/history-summary?start_date={target_date}&end_date={target_date}&kindergarten_id={sample_kindergarten.id}&child_name=Second"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["scope"]["mode"] == "specific_kindergarten"
    assert data["meta"]["scope"]["kindergarten_id"] == sample_kindergarten.id
    assert data["meta"]["scope"]["filters"]["child_name"] == "Second"
    assert data["totals"]["present"] == 0
    assert data["totals"]["total"] == 0
    assert len(data["rows"]) == 1
    app.dependency_overrides.clear()
