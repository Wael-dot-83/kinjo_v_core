"""
Tests for newly implemented endpoints:
- GET  /api/supervisor/dashboard
- GET  /api/supervisor/profile
- PUT  /api/supervisor/settings
- GET  /api/manager/supervisors
- GET  /api/manager/children
- POST /api/messages/broadcast
"""
from __future__ import annotations

import uuid
from datetime import date

import models


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Supervisor Dashboard
# ===========================================================================

class TestSupervisorDashboard:
    def test_dashboard_requires_supervisor_role(self, client, manager_user, manager_token):
        r = client.get("/api/supervisor/dashboard", headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_dashboard_returns_counters(
        self,
        client,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        r = client.get("/api/supervisor/dashboard", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert "pending_reports" in data
        assert "total_children" in data
        assert data["total_children"] == 1

    def test_dashboard_pending_reports_counts_drafts(
        self,
        client,
        test_db,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        today = date.today()
        draft = models.DailyReport(
            child_id=sample_child.id,
            date=today,
            status=models.DailyReportStatus.DRAFT,
            submitted_by=supervisor_user.id,
            arrival_time="08:00",
            leave_time="14:00",
            kindergarten_id=supervisor_user.kindergarten_id,
        )
        test_db.add(draft)
        test_db.commit()

        r = client.get("/api/supervisor/dashboard", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        assert r.json()["pending_reports"] == 1

    def test_dashboard_empty_for_supervisor_with_no_assignments(
        self, client, supervisor_user, supervisor_token
    ):
        r = client.get("/api/supervisor/dashboard", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert data["total_children"] == 0
        assert data["pending_reports"] == 0


# ===========================================================================
# Supervisor Profile
# ===========================================================================

class TestSupervisorProfile:
    def test_profile_requires_supervisor_role(self, client, manager_user, manager_token):
        r = client.get("/api/supervisor/profile", headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_profile_returns_user_info(
        self,
        client,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        r = client.get("/api/supervisor/profile", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == supervisor_user.id
        assert data["username"] == supervisor_user.username
        assert data["role"] == "SUPERVISOR"
        assert data["total_children"] == 1

    def test_profile_includes_classes(
        self,
        client,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        supervisor_token,
    ):
        r = client.get("/api/supervisor/profile", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        classes = r.json().get("classes", [])
        assert any(c["id"] == sample_class.id for c in classes)

    def test_profile_includes_kindergarten_name(
        self,
        client,
        supervisor_user,
        sample_kindergarten,
        supervisor_token,
    ):
        r = client.get("/api/supervisor/profile", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert data["kindergarten_id"] == sample_kindergarten.id
        assert data["kindergarten_name_ar"] == sample_kindergarten.name_ar


# ===========================================================================
# Supervisor Settings
# ===========================================================================

class TestSupervisorSettings:
    def test_settings_requires_supervisor_role(self, client, manager_user, manager_token):
        r = client.put("/api/supervisor/settings", json={}, headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_settings_update_phone_and_email(
        self,
        client,
        test_db,
        supervisor_user,
        supervisor_token,
    ):
        payload = {"phone_number": "+962791112222", "email": "newsup@test.com"}
        r = client.put("/api/supervisor/settings", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        test_db.refresh(supervisor_user)
        assert supervisor_user.phone_number == "+962791112222"
        assert supervisor_user.email == "newsup@test.com"

    def test_settings_update_language(
        self,
        client,
        test_db,
        supervisor_user,
        supervisor_token,
    ):
        r = client.put(
            "/api/supervisor/settings",
            json={"preferred_language": "en"},
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 200
        test_db.refresh(supervisor_user)
        assert supervisor_user.preferred_language == "en"

    def test_settings_rejects_invalid_language(
        self, client, supervisor_user, supervisor_token
    ):
        r = client.put(
            "/api/supervisor/settings",
            json={"preferred_language": "fr"},
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 400

    def test_settings_null_phone_clears_field(
        self,
        client,
        test_db,
        supervisor_user,
        supervisor_token,
    ):
        # First set a value
        client.put("/api/supervisor/settings", json={"phone_number": "+962799998888"}, headers=_hdr(supervisor_token))
        # Now clear it
        r = client.put("/api/supervisor/settings", json={"phone_number": ""}, headers=_hdr(supervisor_token))
        assert r.status_code == 200
        test_db.refresh(supervisor_user)
        assert supervisor_user.phone_number is None


# ===========================================================================
# Manager Supervisors List
# ===========================================================================

class TestManagerSupervisors:
    def test_list_supervisors_requires_manager_role(
        self, client, supervisor_user, supervisor_token
    ):
        r = client.get("/api/manager/supervisors", headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_list_supervisors_returns_kg_supervisors(
        self,
        client,
        manager_user,
        supervisor_user,
        manager_token,
    ):
        r = client.get("/api/manager/supervisors", headers=_hdr(manager_token))
        assert r.status_code == 200
        data = r.json()
        assert "supervisors" in data
        ids = [s["id"] for s in data["supervisors"]]
        assert supervisor_user.id in ids

    def test_list_supervisors_excludes_other_kg(
        self,
        client,
        test_db,
        manager_user,
        supervisor_user,
        manager_token,
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى", name_en="Other KG",
            governorate="Irbid", district="Irbid", area="Center", address_line="St 1",
            contact_phone="0600000002", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        from auth import get_password_hash
        foreign_sup = models.User(
            username="foreignsup", email="fsup@other.com",
            hashed_password=get_password_hash("Pass123!"),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=other_kg.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(foreign_sup)
        test_db.commit()

        r = client.get("/api/manager/supervisors", headers=_hdr(manager_token))
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()["supervisors"]]
        assert foreign_sup.id not in ids

    def test_supervisor_has_classes_list(
        self,
        client,
        manager_user,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        manager_token,
    ):
        r = client.get("/api/manager/supervisors", headers=_hdr(manager_token))
        assert r.status_code == 200
        sups = r.json()["supervisors"]
        sup = next((s for s in sups if s["id"] == supervisor_user.id), None)
        assert sup is not None
        assert any(c["id"] == sample_class.id for c in sup.get("classes", []))


# ===========================================================================
# Manager Children List
# ===========================================================================

class TestManagerChildren:
    def test_list_children_requires_manager_role(
        self, client, supervisor_user, supervisor_token
    ):
        r = client.get("/api/manager/children", headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_list_children_returns_enrolled_children(
        self,
        client,
        manager_user,
        sample_child,
        sample_enrollment,
        manager_token,
    ):
        r = client.get("/api/manager/children", headers=_hdr(manager_token))
        assert r.status_code == 200
        data = r.json()
        assert "children" in data
        ids = [c["id"] for c in data["children"]]
        assert sample_child.id in ids

    def test_list_children_filter_by_class(
        self,
        client,
        manager_user,
        sample_child,
        sample_class,
        sample_enrollment,
        manager_token,
    ):
        r = client.get(f"/api/manager/children?class_id={sample_class.id}", headers=_hdr(manager_token))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["children"]]
        assert sample_child.id in ids

    def test_list_children_filter_other_class_returns_empty(
        self,
        client,
        test_db,
        manager_user,
        sample_kindergarten,
        sample_child,
        sample_enrollment,
        manager_token,
    ):
        other_class = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="شعبة أخرى", name_en="Other", capacity_total=10,
            min_age_months=24, max_age_months=60, is_active=True,
            class_code=str(uuid.uuid4())[:8].upper(), age_group="AGE_2_4",
        )
        test_db.add(other_class)
        test_db.commit()
        test_db.refresh(other_class)

        r = client.get(f"/api/manager/children?class_id={other_class.id}", headers=_hdr(manager_token))
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_list_children_foreign_class_rejected(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة غريبة2", name_en="Foreign KG2",
            governorate="Zarqa", district="Zarqa", area="West", address_line="St 7",
            contact_phone="0600000003", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        foreign_class = models.Class(
            kindergarten_id=other_kg.id,
            name_ar="شعبة غريبة", name_en="Foreign Class", capacity_total=10,
            min_age_months=24, max_age_months=60, is_active=True,
            class_code=str(uuid.uuid4())[:8].upper(), age_group="AGE_2_4",
        )
        test_db.add(foreign_class)
        test_db.commit()
        test_db.refresh(foreign_class)

        r = client.get(f"/api/manager/children?class_id={foreign_class.id}", headers=_hdr(manager_token))
        # 404 (not 403): a class in another kindergarten must not leak that it exists.
        assert r.status_code == 404


# ===========================================================================
# Messages Broadcast
# ===========================================================================

class TestMessagesBroadcast:
    def test_broadcast_requires_manager_role(
        self, client, supervisor_user, supervisor_token
    ):
        payload = {"body": "test", "recipients": [{"role": "all_supervisors"}]}
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_broadcast_to_specific_supervisor(
        self,
        client,
        manager_user,
        supervisor_user,
        manager_token,
    ):
        payload = {
            "subject": "تنبيه",
            "body": "يرجى مراجعة جدول الحضور",
            "recipients": [{"role": "supervisor", "id": supervisor_user.id}],
        }
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 201
        data = r.json()
        assert data["created"] == 1

    def test_broadcast_to_all_supervisors(
        self,
        client,
        manager_user,
        supervisor_user,
        manager_token,
    ):
        payload = {
            "body": "اجتماع طارئ",
            "recipients": [{"role": "all_supervisors"}],
        }
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 201
        data = r.json()
        assert data["created"] >= 1

    def test_broadcast_empty_body_rejected(
        self, client, manager_user, supervisor_user, manager_token
    ):
        payload = {"body": "   ", "recipients": [{"role": "all_supervisors"}]}
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 400

    def test_broadcast_to_foreign_supervisor_rejected(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة خارجية", name_en="Ext KG",
            governorate="Aqaba", district="Aqaba", area="East", address_line="St 3",
            contact_phone="0600000004", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        from auth import get_password_hash
        foreign_sup = models.User(
            username="extsup99", email="extsup99@test.com",
            hashed_password=get_password_hash("Pass123!"),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=other_kg.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(foreign_sup)
        test_db.commit()

        payload = {
            "body": "رسالة محظورة",
            "recipients": [{"role": "supervisor", "id": foreign_sup.id}],
        }
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_broadcast_to_class_parents(
        self,
        client,
        manager_user,
        parent_user,
        sample_child,
        sample_class,
        sample_enrollment,
        manager_token,
    ):
        payload = {
            "subject": "إشعار",
            "body": "نشاط قادم",
            "recipients": [{"role": "parents_class", "class_id": sample_class.id}],
        }
        r = client.post("/api/messages/broadcast", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 201
        assert r.json()["created"] >= 1


# ===========================================================================
# Manager — Edit Daily Report (PUT /api/manager/daily-reports/{id})
# ===========================================================================

class TestManagerReportEdit:
    def _make_report(self, test_db, child_id, supervisor_id, status, kindergarten_id=None):
        import models
        from datetime import date
        if kindergarten_id is None:
            enr = test_db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.child_id == child_id
            ).first()
            kindergarten_id = enr.kindergarten_id if enr else None
        report = models.DailyReport(
            child_id=child_id,
            date=date.today(),
            status=status,
            submitted_by=supervisor_id,
            arrival_time="08:00",
            leave_time="14:00",
            kindergarten_id=kindergarten_id,
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)
        return report

    def test_manager_can_edit_submitted_report(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        supervisor_user,
        sample_child,
        sample_enrollment,
    ):
        report = self._make_report(
            test_db, sample_child.id, supervisor_user.id,
            models.DailyReportStatus.SUBMITTED,
        )
        r = client.put(
            f"/api/manager/daily-reports/{report.id}",
            json={"notes": "ملاحظة المدير", "breakfast": True},
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200
        test_db.refresh(report)
        assert report.notes == "ملاحظة المدير"
        assert report.breakfast is True

    def test_manager_cannot_edit_sent_report(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        supervisor_user,
        sample_child,
        sample_enrollment,
    ):
        report = self._make_report(
            test_db, sample_child.id, supervisor_user.id,
            models.DailyReportStatus.SENT_TO_PARENT,
        )
        r = client.put(
            f"/api/manager/daily-reports/{report.id}",
            json={"notes": "محاولة تعديل"},
            headers=_hdr(manager_token),
        )
        assert r.status_code == 403

    def test_manager_cannot_edit_report_in_foreign_kindergarten(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        supervisor_user,
        sample_child,
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى", name_en="Other KG",
            governorate="Zarqa", district="Zarqa", area="West", address_line="St 5",
            contact_phone="0600000099", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)

        other_class = models.Class(
            kindergarten_id=other_kg.id,
            name_ar="الفصل ب", name_en="Class B",
            capacity_total=15,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            class_code=str(uuid.uuid4())[:8].upper(), age_group="AGE_2_4",
        )
        test_db.add(other_class)
        test_db.commit()
        test_db.refresh(other_class)

        other_child = models.Child(
            parent_id=sample_child.parent_id,
            first_name="Ahmad", last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=sample_child.date_of_birth,
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            mother_national_id="1111111111",
            media_consent=False,
        )
        test_db.add(other_child)
        test_db.commit()
        test_db.refresh(other_child)

        other_enrollment = models.EnrollmentApplication(
            child_id=other_child.id,
            kindergarten_id=other_kg.id,
            class_id=other_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="WEB",
        )
        test_db.add(other_enrollment)
        test_db.commit()

        report = self._make_report(
            test_db, other_child.id, supervisor_user.id,
            models.DailyReportStatus.SUBMITTED,
        )
        r = client.put(
            f"/api/manager/daily-reports/{report.id}",
            json={"notes": "لا يجب أن يعمل"},
            headers=_hdr(manager_token),
        )
        # Cross-kindergarten resource access returns 404 (not 403) so we don't
        # leak that another tenant's report exists (#14).
        assert r.status_code == 404


# ===========================================================================
# Frontend RBAC — /curriculum supervisor block
# ===========================================================================

class TestCurriculumAccess:
    def test_manager_can_access_curriculum(self, client, manager_token):
        r = client.get("/curriculum", headers=_hdr(manager_token))
        assert r.status_code == 200

    def test_supervisor_is_blocked_from_curriculum(self, client, supervisor_token):
        r = client.get("/curriculum", headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_admin_is_blocked_from_curriculum(self, client, admin_token):
        r = client.get("/curriculum", headers=_hdr(admin_token))
        assert r.status_code == 403


# ===========================================================================
# Frontend RBAC — supervisor page access restrictions (criteria 1 & 2)
# ===========================================================================

class TestSupervisorFrontendBlocks:
    def test_supervisor_blocked_from_enrollments_redirected(self, client, supervisor_token):
        r = client.get("/enrollments", headers=_hdr(supervisor_token), follow_redirects=False)
        # Supervisor is blocked from enrollments (403 or redirect)
        assert r.status_code in (302, 303, 307, 403)

    def test_supervisor_blocked_from_attendance_daily(self, client, supervisor_token):
        r = client.get("/attendance/daily", headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_supervisor_blocked_from_daily_reports_create(self, client, supervisor_token):
        r = client.get("/daily-reports/create", headers=_hdr(supervisor_token))
        assert r.status_code == 403


# ===========================================================================
# Frontend RBAC — admin classroom page blocks (criteria 20)
# ===========================================================================

class TestAdminFrontendBlocks:
    def test_admin_blocked_from_attendance_daily(self, client, admin_token):
        r = client.get("/attendance/daily", headers=_hdr(admin_token))
        assert r.status_code == 403

    def test_admin_blocked_from_daily_reports_create(self, client, admin_token):
        r = client.get("/daily-reports/create", headers=_hdr(admin_token))
        assert r.status_code == 403

    def test_admin_can_access_attendance_history(self, client, admin_token):
        r = client.get("/attendance/history", headers=_hdr(admin_token))
        assert r.status_code == 200


# ===========================================================================
# Manager child move between classes (criteria 12)
# ===========================================================================

class TestManagerChildMove:
    def test_manager_can_move_child_between_classes(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        sample_kindergarten,
        sample_child,
        sample_class,
        sample_enrollment,
    ):
        # Create a second class in the same kindergarten
        class_b = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="الصف ب", name_en="Class B",
            capacity_total=20, min_age_months=24, max_age_months=60, is_active=True,
            class_code=str(uuid.uuid4())[:8].upper(), age_group="AGE_2_4",
        )
        test_db.add(class_b)
        test_db.commit()
        test_db.refresh(class_b)

        r = client.post(
            "/api/manager/children/move-class",
            json={"child_id": sample_child.id, "from_class_id": sample_class.id, "to_class_id": class_b.id},
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["new_class_id"] == class_b.id

        # Verify enrollment updated in DB
        test_db.expire_all()
        updated = test_db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == sample_child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).first()
        assert updated.class_id == class_b.id

    def test_manager_cannot_move_child_to_foreign_class(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        sample_child,
        sample_class,
        sample_enrollment,
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة مختلفة", name_en="Other KG",
            governorate="Zarqa", district="Zarqa", area="West", address_line="St 1",
            contact_phone="0600000042", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        foreign_class = models.Class(
            kindergarten_id=other_kg.id, name_ar="فصل غريب", name_en="Foreign",
            capacity_total=10, min_age_months=24, max_age_months=60, is_active=True,
            class_code=str(uuid.uuid4())[:8].upper(), age_group="AGE_2_4",
        )
        test_db.add(foreign_class)
        test_db.commit()
        test_db.refresh(foreign_class)

        r = client.post(
            "/api/manager/children/move-class",
            json={"child_id": sample_child.id, "from_class_id": sample_class.id, "to_class_id": foreign_class.id},
            headers=_hdr(manager_token),
        )
        # Cross-tenant target returns 404 (no existence leak) after the S2 scope
        # unification; both 403 and 404 are valid denials.
        assert r.status_code in (403, 404)


# ===========================================================================
# Parent receives message when report sent (criteria 16)
# ===========================================================================

class TestParentReceivesReportMessage:
    def test_parent_gets_message_when_report_sent_to_parents(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        parent_user,
        sample_child,
        sample_enrollment,
        supervisor_user,
    ):
        report = models.DailyReport(
            child_id=sample_child.id,
            date=date.today(),
            status=models.DailyReportStatus.SUBMITTED,
            submitted_by=supervisor_user.id,
            arrival_time="08:00",
            leave_time="14:00",
            kindergarten_id=manager_user.kindergarten_id,
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        r = client.put(
            f"/api/manager/daily-reports/{report.id}/send-to-parents",
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "SENT_TO_PARENT"

        # Verify a notification message was created for the parent
        msg = test_db.query(models.Message).filter(
            models.Message.recipient_id == parent_user.id,
        ).first()
        assert msg is not None, "No message created for parent after send-to-parents"


# ===========================================================================
# Supervisor unassign and swap (criteria 10, partial)
# ===========================================================================

class TestManagerSupervisorAssignment:
    def test_manager_can_unassign_supervisor(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
    ):
        r = client.delete(
            f"/api/manager/classes/{sample_class.id}/supervisors/{supervisor_user.id}",
            headers=_hdr(manager_token),
        )
        assert r.status_code == 204

        # Assignment should be soft-deleted (deleted_at set)
        test_db.expire_all()
        remaining = test_db.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.class_id == sample_class.id,
            models.SupervisorAssignment.supervisor_id == supervisor_user.id,
        ).first()
        assert remaining is None or remaining.deleted_at is not None

    def test_manager_can_swap_supervisor(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
        supervisor_user,
        sample_class,
        sample_kindergarten,
        sample_supervisor_assignment,
    ):
        from auth import get_password_hash
        new_sup = models.User(
            username="newsup01", email="newsup01@test.com",
            hashed_password=get_password_hash("Pass123!"),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(new_sup)
        test_db.commit()
        test_db.refresh(new_sup)

        r = client.put(
            f"/api/manager/classes/{sample_class.id}/swap-supervisor",
            json={"supervisor_id": new_sup.id, "class_id": sample_class.id, "is_primary": True},
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200
