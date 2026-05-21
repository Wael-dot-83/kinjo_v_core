from datetime import date, datetime, timezone

import models
from auth import get_password_hash


def _parent_profile(db, user):
    return db.query(models.ParentProfile).filter(models.ParentProfile.user_id == user.id).one()


def _create_child(db, profile, first_name="Child", last_name="One", deleted=False):
    child = models.Child(
        parent_id=profile.id,
        first_name=first_name,
        last_name=last_name,
        gender=models.Gender.FEMALE,
        date_of_birth=date(2023, 1, 1),
        father_name="Parent User",
        mother_first_name="Mother",
        mother_last_name="User",
        mother_nationality="Jordanian",
        mother_national_id=f"MID-{first_name}-{last_name}",
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


def _create_report(db, child, submitter, status, notes="report note"):
    report = models.DailyReport(
        child_id=child.id,
        date=date.today(),
        status=status,
        submitted_by=submitter.id,
        submitted_at=datetime.now(timezone.utc),
        arrival_time="08:00",
        leave_time="14:00",
        breakfast=True,
        snack=True,
        milk=False,
        lunch=True,
        notes=notes,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _valid_enrollment_payload(kindergarten_id, **overrides):
    payload = {
        "first_name": "Clean",
        "last_name": "Child",
        "gender": "FEMALE",
        "date_of_birth": "2023-01-01",
        "kindergarten_id": kindergarten_id,
        "mother_first_name": "Mother",
        "mother_last_name": "User",
        "mother_nationality": "Jordanian",
        "mother_national_id": "MOTHER-1000",
    }
    payload.update(overrides)
    return payload


def test_parent_sees_sent_to_parent_reports_and_not_drafts(
    client, test_db, parent_user, auth_headers_parent, supervisor_user
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile)
    sent = _create_report(
        test_db,
        child,
        supervisor_user,
        models.DailyReportStatus.SENT_TO_PARENT,
        notes="sent visible note",
    )
    draft = _create_report(
        test_db,
        child,
        supervisor_user,
        models.DailyReportStatus.DRAFT,
        notes="draft hidden note",
    )

    child_resp = client.get(f"/api/daily-reports/child/{child.id}", headers=auth_headers_parent)
    assert child_resp.status_code == 200
    child_ids = {item["id"] for item in child_resp.json()["reports"]}
    assert sent.id in child_ids
    assert draft.id not in child_ids

    list_resp = client.get("/api/reports?shared_with_parent=true", headers=auth_headers_parent)
    assert list_resp.status_code == 200
    list_ids = {item["id"] for item in list_resp.json()["reports"]}
    assert sent.id in list_ids
    assert draft.id not in list_ids


def test_parent_report_type_filter_matches_supported_progress_reports(
    client, test_db, parent_user, auth_headers_parent, supervisor_user
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile)
    sent = _create_report(
        test_db,
        child,
        supervisor_user,
        models.DailyReportStatus.SENT_TO_PARENT,
        notes="progress report",
    )

    progress_resp = client.get(
        "/api/reports?shared_with_parent=true&report_type=PROGRESS",
        headers=auth_headers_parent,
    )
    assert progress_resp.status_code == 200
    assert sent.id in {item["id"] for item in progress_resp.json()["reports"]}

    behavior_resp = client.get(
        "/api/reports?shared_with_parent=true&report_type=BEHAVIOR",
        headers=auth_headers_parent,
    )
    assert behavior_resp.status_code == 200
    assert behavior_resp.json()["reports"] == []


def test_parent_report_page_renders_only_released_reports(
    client, test_db, parent_user, auth_headers_parent, supervisor_user
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile)
    sent = _create_report(
        test_db,
        child,
        supervisor_user,
        models.DailyReportStatus.SENT_TO_PARENT,
        notes="sent page note",
    )
    draft = _create_report(
        test_db,
        child,
        supervisor_user,
        models.DailyReportStatus.DRAFT,
        notes="draft page note",
    )

    sent_resp = client.get(f"/reports/{sent.id}", headers=auth_headers_parent)
    assert sent_resp.status_code == 200
    assert "sent page note" in sent_resp.text

    draft_resp = client.get(f"/reports/{draft.id}", headers=auth_headers_parent)
    assert draft_resp.status_code == 404


def test_non_parent_cannot_submit_parent_enrollment(
    client, test_db, parent_user, auth_headers_supervisor, sample_kindergarten
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile)
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)

    resp = client.post(f"/api/enrollment/{enrollment.id}/submit", headers=auth_headers_supervisor)
    assert resp.status_code == 403

    test_db.refresh(enrollment)
    assert enrollment.status == models.EnrollmentStatus.DRAFT


def test_parent_inputs_return_400_instead_of_500(
    client, auth_headers_parent, sample_kindergarten
):
    attendance_resp = client.get(
        "/api/parent/attendance?year=10000&month=1",
        headers=auth_headers_parent,
    )
    assert attendance_resp.status_code == 400

    payload = _valid_enrollment_payload(
        sample_kindergarten.id,
        date_of_birth="not-a-date",
    )
    enrollment_resp = client.post(
        "/api/enrollment/apply",
        headers=auth_headers_parent,
        json=payload,
    )
    assert enrollment_resp.status_code == 400


def test_enrollment_sanitizes_child_fields_before_parent_rendering(
    client, auth_headers_parent, sample_kindergarten
):
    payload = _valid_enrollment_payload(
        sample_kindergarten.id,
        first_name="Safe<img src=x onerror=alert(1)>",
        mother_national_id="MOTHER-2000",
    )
    create_resp = client.post("/api/enrollment/apply", headers=auth_headers_parent, json=payload)
    assert create_resp.status_code == 201

    children_resp = client.get("/api/parent/children", headers=auth_headers_parent)
    assert children_resp.status_code == 200
    names = [child["full_name_ar"] for child in children_resp.json()["children"]]
    assert any(name.startswith("Safe ") for name in names)
    assert all("<" not in name and "onerror" not in name for name in names)


def test_parent_lists_hide_soft_deleted_children_and_enrollments(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    profile = _parent_profile(test_db, parent_user)
    active_child = _create_child(test_db, profile, first_name="Active")
    deleted_child = _create_child(test_db, profile, first_name="Deleted", deleted=True)
    active_enrollment = models.EnrollmentApplication(
        child_id=active_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    deleted_enrollment = models.EnrollmentApplication(
        child_id=active_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
        deleted_at=datetime.now(timezone.utc),
    )
    deleted_child_enrollment = models.EnrollmentApplication(
        child_id=deleted_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    test_db.add_all([active_enrollment, deleted_enrollment, deleted_child_enrollment])
    test_db.commit()

    children_resp = client.get("/api/parent/children", headers=auth_headers_parent)
    assert children_resp.status_code == 200
    child_names = {child["first_name"] for child in children_resp.json()["children"]}
    assert "Active" in child_names
    assert "Deleted" not in child_names

    enrollments_resp = client.get("/api/parent/enrollments", headers=auth_headers_parent)
    assert enrollments_resp.status_code == 200
    enrollment_ids = {item["id"] for item in enrollments_resp.json()["enrollments"]}
    assert active_enrollment.id in enrollment_ids
    assert deleted_enrollment.id not in enrollment_ids
    assert deleted_child_enrollment.id not in enrollment_ids


def test_passport_only_parent_can_apply_for_enrollment(
    client, test_db, sample_kindergarten
):
    user = models.User(
        username="passport-parent@example.com",
        email="passport-parent@example.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    profile = models.ParentProfile(
        user_id=user.id,
        first_name="Passport",
        last_name="Parent",
        phone_number="+962799900001",
        gender=models.Gender.MALE,
        nationality="Non-Jordanian",
        passport_number="P1234567",
        parent_type="FATHER",
        home_governorate="Amman",
        home_city="Amman",
        home_area="Area",
        home_address_line="Address",
    )
    test_db.add(profile)
    test_db.commit()

    token_resp = client.post(
        "/token",
        data={"username": user.username, "password": "Parent123!"},
    )
    assert token_resp.status_code == 200
    headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

    payload = _valid_enrollment_payload(
        sample_kindergarten.id,
        mother_national_id="MOTHER-3000",
    )
    resp = client.post("/api/enrollment/apply", headers=headers, json=payload)
    assert resp.status_code == 201


def test_parent_profile_identity_fields_round_trip(
    client, test_db, parent_user, auth_headers_parent
):
    payload = {
        "first_name": "Updated",
        "last_name": "Parent",
        "email": parent_user.email,
        "phone": "+962791234567",
        "parent_type": "MOTHER",
        "nationality": "Non-Jordanian",
        "national_id": "9876543210",
        "passport_number": "PX-987654",
    }
    update_resp = client.put("/api/users/me", headers=auth_headers_parent, json=payload)
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["parent_type"] == "MOTHER"
    assert body["nationality"] == "Non-Jordanian"
    assert body["national_id"] == "9876543210"
    assert body["passport_number"] == "PX-987654"

    profile = _parent_profile(test_db, parent_user)
    test_db.refresh(profile)
    assert profile.parent_type == "MOTHER"
    assert profile.passport_number == "PX-987654"


def test_parent_frontend_pages_render_with_authenticated_parent(
    client, auth_headers_parent
):
    for path in [
        "/parent/dashboard",
        "/parent/children",
        "/parent/attendance",
        "/parent/enrollments",
        "/my-reports",
        "/profile",
        "/attendance/absence-requests",
        "/enrollments/create",
    ]:
        resp = client.get(path, headers=auth_headers_parent)
        assert resp.status_code == 200, path
