"""
Regression tests for the parent module.

Covers:
- Report visibility (parents see only SENT_TO_PARENT, not DRAFTs)
- Enrollment submission RBAC (supervisor cannot submit on parent's behalf)
- Input validation returns 422 for malformed dates
- Soft-deleted children and enrollments are hidden from parent list views
- Parent profile round-trip (parent_type persists via PUT /api/users/me)
- Frontend pages render 200 for authenticated parents
"""
from datetime import date, datetime, timezone

import models
from auth import get_password_hash


# ── helpers ───────────────────────────────────────────────────────────────────

def _parent_profile(db, user):
    return db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == user.id
    ).one()


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


def _create_report(db, child, submitter, status, notes="report note", kindergarten_id=None, report_date=None):
    report = models.DailyReport(
        child_id=child.id,
        kindergarten_id=kindergarten_id or submitter.kindergarten_id,
        date=report_date or date.today(),
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


def _valid_enrollment_payload(kindergarten_id, last_name="Al-Rashid", **overrides):
    """Build a valid enrollment payload.  last_name must match the submitting parent's profile."""
    payload = {
        "first_name": "Clean",
        "last_name": last_name,
        "gender": "FEMALE",
        "date_of_birth": "2023-01-01",
        "kindergarten_id": kindergarten_id,
        "father_name": "Ahmad Al-Rashid",
        "mother_first_name": "Mother",
        "mother_last_name": "User",
        "mother_nationality": "Jordanian",
        "mother_national_id": "MOTHER-1000",
    }
    payload.update(overrides)
    return payload


# ── tests ─────────────────────────────────────────────────────────────────────

def test_parent_sees_sent_to_parent_reports_and_not_drafts(
    client, test_db, parent_user, auth_headers_parent, supervisor_user, sample_kindergarten
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile)
    sent = _create_report(
        test_db, child, supervisor_user,
        models.DailyReportStatus.SENT_TO_PARENT,
        notes="sent visible note",
        kindergarten_id=sample_kindergarten.id,
        report_date=date(2024, 1, 1),
    )
    draft = _create_report(
        test_db, child, supervisor_user,
        models.DailyReportStatus.DRAFT,
        notes="draft hidden note",
        kindergarten_id=sample_kindergarten.id,
        report_date=date(2024, 1, 2),
    )

    child_resp = client.get(f"/api/daily-reports/child/{child.id}", headers=auth_headers_parent)
    assert child_resp.status_code == 200
    child_ids = {item["id"] for item in child_resp.json()["reports"]}
    assert sent.id in child_ids
    assert draft.id not in child_ids


def test_parent_report_page_renders_sent_report(
    client, test_db, parent_user, auth_headers_parent, supervisor_user, sample_kindergarten
):
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="PageChild")
    sent = _create_report(
        test_db, child, supervisor_user,
        models.DailyReportStatus.SENT_TO_PARENT,
        notes="sent page note",
        kindergarten_id=sample_kindergarten.id,
    )

    sent_resp = client.get(f"/reports/{sent.id}", headers=auth_headers_parent)
    assert sent_resp.status_code == 200


def test_non_parent_cannot_submit_parent_enrollment(
    client, test_db, parent_user, auth_headers_supervisor, sample_kindergarten
):
    """Supervisor must receive 403 when trying to submit a parent's enrollment."""
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="SubmitChild")
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)

    resp = client.post(
        f"/api/enrollment/{enrollment.id}/submit",
        headers=auth_headers_supervisor,
    )
    assert resp.status_code == 403

    test_db.refresh(enrollment)
    assert enrollment.status == models.EnrollmentStatus.DRAFT


def test_enrollment_apply_rejects_malformed_date(
    client, auth_headers_parent, sample_kindergarten
):
    """A malformed date_of_birth returns 422 (Pydantic validation)."""
    payload = _valid_enrollment_payload(
        sample_kindergarten.id,
        date_of_birth="not-a-date",
        mother_national_id="MOTHER-5000",
    )
    resp = client.post("/api/enrollment/apply", headers=auth_headers_parent, json=payload)
    assert resp.status_code == 422


def test_enrollment_apply_accepts_valid_payload(
    client, auth_headers_parent, sample_kindergarten
):
    """A well-formed enrollment payload returns 201."""
    payload = _valid_enrollment_payload(
        sample_kindergarten.id,
        mother_national_id="MOTHER-6000",
    )
    resp = client.post("/api/enrollment/apply", headers=auth_headers_parent, json=payload)
    assert resp.status_code == 201


def test_parent_lists_hide_soft_deleted_children_and_enrollments(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    profile = _parent_profile(test_db, parent_user)
    active_child = _create_child(test_db, profile, first_name="ActiveKid")
    deleted_child = _create_child(test_db, profile, first_name="DeletedKid", deleted=True)

    active_enrollment = models.EnrollmentApplication(
        child_id=active_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    # Use deleted_child for the enrollment that should be hidden
    deleted_child_enrollment = models.EnrollmentApplication(
        child_id=deleted_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.DRAFT,
        source="online",
    )
    test_db.add_all([active_enrollment, deleted_child_enrollment])
    test_db.commit()

    children_resp = client.get("/api/parent/children", headers=auth_headers_parent)
    assert children_resp.status_code == 200
    child_names = {child["first_name"] for child in children_resp.json()["children"]}
    assert "ActiveKid" in child_names
    assert "DeletedKid" not in child_names

    enrollments_resp = client.get("/api/parent/enrollments", headers=auth_headers_parent)
    assert enrollments_resp.status_code == 200
    enrollment_ids = {item["id"] for item in enrollments_resp.json()["enrollments"]}
    assert active_enrollment.id in enrollment_ids
    assert deleted_child_enrollment.id not in enrollment_ids

    dashboard_resp = client.get("/api/parent/dashboard", headers=auth_headers_parent)
    assert dashboard_resp.status_code == 200
    assert {child["first_name"] for child in dashboard_resp.json()["children"]} == {"ActiveKid"}

    selector_resp = client.get("/api/parent/children-list", headers=auth_headers_parent)
    assert selector_resp.status_code == 200
    assert {child["name"] for child in selector_resp.json()["children"]} == {"ActiveKid One"}


def test_passport_only_parent_can_apply_for_enrollment(
    client, test_db, sample_kindergarten
):
    """A parent identified only by passport (no national ID) can still apply."""
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
        relationship_to_child="father",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Area",
        home_address_line="Address",
        correspondence_preference=True,
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
        last_name="Parent",  # matches passport parent profile's last_name
        mother_national_id="MOTHER-3000",
    )
    resp = client.post("/api/enrollment/apply", headers=headers, json=payload)
    assert resp.status_code == 201


def test_parent_profile_parent_type_round_trip(
    client, test_db, parent_user, auth_headers_parent
):
    """parent_type persists through PUT /api/users/me."""
    payload = {
        "first_name": "Updated",
        "last_name": "Parent",
        "parent_type": "MOTHER",
        "nationality": "Non-Jordanian",
        "national_id": "9876543210",
    }
    update_resp = client.put("/api/users/me", headers=auth_headers_parent, json=payload)
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body.get("parent_type") == "MOTHER"
    assert body.get("nationality") == "Non-Jordanian"

    profile = _parent_profile(test_db, parent_user)
    test_db.refresh(profile)
    assert profile.parent_type == "MOTHER"


def test_parent_frontend_pages_return_200(client, auth_headers_parent):
    """All core parent-facing pages render without error."""
    pages = [
        "/parent/dashboard",
        "/parent/children",
        "/parent/attendance",
        "/parent/enrollments",
        "/parent/profile",
        "/my-reports",
        "/profile",
        "/absence-requests",
    ]
    for path in pages:
        resp = client.get(path, headers=auth_headers_parent)
        assert resp.status_code == 200, f"Expected 200 for {path}, got {resp.status_code}"


def test_parent_shared_assets_are_served(client, auth_headers_parent):
    """The shared parent JS helper and extracted profile CSS are reachable."""
    for path in (
        "/static/js/parent-common.js",
        "/static/css/parent-profile.css",
    ):
        resp = client.get(path, headers=auth_headers_parent)
        assert resp.status_code == 200, f"Expected 200 for {path}, got {resp.status_code}"


def test_parent_pages_reference_shared_helpers(client, auth_headers_parent):
    """Parent pages load parent-common.js and no longer inline the old helpers."""
    pages = ["/parent/children", "/parent/attendance", "/parent/enrollments", "/parent/profile"]
    for path in pages:
        html = client.get(path, headers=auth_headers_parent).text
        assert "/static/js/parent-common.js" in html, f"{path} missing parent-common.js"
        assert "function getHeaders()" not in html, f"{path} still inlines getHeaders"


def test_enrollment_items_expose_bilingual_status_labels(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    """status_ar and status_en come from the backend single source (additive)."""
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="LabelKid")
    test_db.add(
        models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
        )
    )
    test_db.commit()

    children_resp = client.get("/api/parent/children", headers=auth_headers_parent)
    assert children_resp.status_code == 200
    enrollment = children_resp.json()["children"][0]["enrollments"][0]
    assert enrollment["status_ar"] == "نشط"
    assert enrollment["status_en"] == "Active"

    enrollments_resp = client.get("/api/parent/enrollments", headers=auth_headers_parent)
    assert enrollments_resp.status_code == 200
    item = enrollments_resp.json()["enrollments"][0]
    assert item["status_ar"] == "نشط"
    assert item["status_en"] == "Active"


def _second_kindergarten(test_db):
    kg = models.Kindergarten(
        name_ar="حضانة النور",
        name_en="Noor Kindergarten",
        license_number="LIC-2026-002",
        governorate="Amman",
        district="Amman",
        area="Khalda",
        address_line="45 Side Street",
        contact_phone="+962797654321",
        contact_email="contact@noor.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


def test_dashboard_returns_all_enrollments_for_child_with_multiple(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    """A child holding two in-flight enrollments exposes both on the dashboard.

    Regression: the dashboard previously collapsed enrollments into a
    single-entry dict keyed by child_id, silently dropping all but the last
    enrollment per child.
    """
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="MultiEnroll")
    kg2 = _second_kindergarten(test_db)

    active = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
        source="online",
    )
    waitlisted = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg2.id,
        status=models.EnrollmentStatus.WAITLISTED,
        source="online",
    )
    test_db.add_all([active, waitlisted])
    test_db.commit()
    test_db.refresh(active)
    test_db.refresh(waitlisted)

    resp = client.get("/api/parent/dashboard", headers=auth_headers_parent)
    assert resp.status_code == 200
    children = resp.json()["children"]
    assert len(children) == 1
    child_data = children[0]

    enrollment_ids = {e["id"] for e in child_data["enrollments"]}
    assert enrollment_ids == {active.id, waitlisted.id}
    assert {e["status"] for e in child_data["enrollments"]} == {"ACTIVE", "WAITLISTED"}

    assert child_data["enrollment"]["status"] == "ACTIVE"
    assert child_data["enrollment"]["kindergarten_id"] == sample_kindergarten.id


def test_parent_login_frequency_no_data(test_db):
    """With no parents the metric reports no_data instead of a fabricated value."""
    from parent_engagement_service import parent_engagement_service

    result = parent_engagement_service.parent_login_frequency(test_db)
    assert result["total_parents"] == 0
    assert result["active_parents"] == 0
    assert result["total_logins"] == 0
    assert result["avg_logins_per_parent"] == 0.0
    assert result["classification"] == "no_data"


def test_parent_login_frequency_populated(client, test_db, parent_user):
    """A real login produces a real metric instead of the old 'unknown' stub."""
    from parent_engagement_service import parent_engagement_service

    login = client.post(
        "/token",
        data={"username": parent_user.username, "password": "Parent123!"},
    )
    assert login.status_code == 200

    result = parent_engagement_service.parent_login_frequency(test_db)
    assert result["total_parents"] == 1
    assert result["active_parents"] == 1
    assert result["total_logins"] >= 1
    assert result["avg_logins_per_parent"] >= 1.0
    assert result["classification"] in ("high", "moderate", "low")
    assert result["classification"] != "unknown"


def test_parent_login_frequency_scoped_by_kindergarten(
    client, test_db, parent_user, sample_kindergarten
):
    """Kindergarten scoping follows the ParentProfile -> Child -> Enrollment path."""
    from parent_engagement_service import parent_engagement_service

    login = client.post(
        "/token",
        data={"username": parent_user.username, "password": "Parent123!"},
    )
    assert login.status_code == 200

    unscoped = parent_engagement_service.parent_login_frequency(
        test_db, kindergarten_id=sample_kindergarten.id
    )
    assert unscoped["total_parents"] == 0
    assert unscoped["classification"] == "no_data"

    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="ScopedKid")
    test_db.add(
        models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
        )
    )
    test_db.commit()

    scoped = parent_engagement_service.parent_login_frequency(
        test_db, kindergarten_id=sample_kindergarten.id
    )
    assert scoped["total_parents"] == 1
    assert scoped["active_parents"] == 1
    assert scoped["total_logins"] >= 1


def test_observability_parent_engagement_has_real_login_metric(
    client, test_db, admin_token, parent_user
):
    """The admin engagement endpoint no longer surfaces a fabricated login metric."""
    login = client.post(
        "/token",
        data={"username": parent_user.username, "password": "Parent123!"},
    )
    assert login.status_code == 200

    resp = client.get(
        "/api/observability/parent-engagement",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    logins = resp.json()["parent_logins"]
    assert logins["classification"] != "unknown"
    assert logins["total_parents"] == 1
    assert logins["avg_logins_per_parent"] >= 1.0


def test_parent_enrollments_pagination_backward_compatible(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    """No pagination params -> all rows returned exactly as before (mobile-safe)."""
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="PagKid")

    kg2 = _second_kindergarten(test_db)
    for kg in (sample_kindergarten, kg2):
        test_db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg.id,
                status=models.EnrollmentStatus.DRAFT,
                source="online",
            )
        )
    test_db.commit()

    resp = client.get("/api/parent/enrollments", headers=auth_headers_parent)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["enrollments"]) == 2
    assert "pagination" not in body


def test_parent_enrollments_pagination_opt_in(
    client, test_db, parent_user, auth_headers_parent, sample_kindergarten
):
    """Explicit page/page_size -> bounded page plus pagination metadata."""
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="PagKid2")

    kgs = [sample_kindergarten, _second_kindergarten(test_db)]
    for kg in kgs:
        test_db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg.id,
                status=models.EnrollmentStatus.DRAFT,
                source="online",
            )
        )
    test_db.commit()

    resp = client.get(
        "/api/parent/enrollments?page=1&page_size=1", headers=auth_headers_parent
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["enrollments"]) == 1
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 1
    assert body["pagination"]["total_count"] == 2
    assert body["pagination"]["total_pages"] == 2


def test_parent_enrollments_pagination_rejects_oversized_page(
    client, auth_headers_parent
):
    """page_size above the 100 cap is rejected with 422."""
    resp = client.get(
        "/api/parent/enrollments?page=1&page_size=101", headers=auth_headers_parent
    )
    assert resp.status_code == 422


def test_parent_daily_reports_pagination_opt_in(
    client, test_db, parent_user, auth_headers_parent, supervisor_user, sample_kindergarten
):
    """Daily reports paginate when requested and stay full-list by default."""
    profile = _parent_profile(test_db, parent_user)
    child = _create_child(test_db, profile, first_name="ReportKid")
    for day in (1, 2, 3):
        _create_report(
            test_db, child, supervisor_user,
            models.DailyReportStatus.SENT_TO_PARENT,
            notes=f"report-{day}",
            kindergarten_id=sample_kindergarten.id,
            report_date=date(2024, 1, day),
        )

    full = client.get("/api/parent/daily-reports", headers=auth_headers_parent)
    assert full.status_code == 200
    full_body = full.json()
    assert full_body["total"] == 3
    assert len(full_body["reports"]) == 3
    assert "pagination" not in full_body

    paged = client.get(
        "/api/parent/daily-reports?page=2&page_size=2", headers=auth_headers_parent
    )
    assert paged.status_code == 200
    paged_body = paged.json()
    assert paged_body["total"] == 3
    assert len(paged_body["reports"]) == 1
    assert paged_body["pagination"]["total_pages"] == 2
