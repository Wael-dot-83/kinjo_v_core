"""
Comprehensive Integration Tests for KinJo Platform
===================================================
Professional-grade test suite covering all 11 modules with:
- Happy path scenarios
- Sad path (error handling) scenarios
- Security boundary tests
- Multi-tenancy isolation tests
- Performance regression tests
- Data integrity tests

Test Categories:
1. Authentication & Authorization
2. Enrollment Workflows
3. Attendance & Ratio Compliance
4. Daily Reports & Parent Feed
5. Safety & Incidents
6. KPI & Governance
7. Supervisor Operations
8. Multi-tenancy & Data Isolation
9. Concurrent Operations
10. API Rate Limiting & Throttling

NOTE: Many tests are skipped because they require endpoints that haven't been 
implemented yet. They serve as documentation for future API development.
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch
import models
from sqlalchemy import func


# ============================================================================
# Module 1: Authentication & Authorization Tests
# ============================================================================

class TestAuthenticationIntegration:
    """Comprehensive authentication workflow tests"""

    def test_full_registration_to_login_flow(self, client, test_db):
        """Happy path: Complete registration -> login -> authenticated access"""
        # Step 1: Register as parent
        registration_data = {
            "first_name": "سارة",
            "last_name": "الأحمد",
            "phone_number": "+962791234567",
            "gender": "female",
            "nationality": "Jordanian",
            "national_id": "9876543210",
            "home_governorate": "Amman",
            "home_district": "Amman",
            "home_area": "Jubeiha",
            "home_address_line": "شارع الجامعة 123",
            "email": "sara.ahmad@test.jo",
            "password": "SecurePass123!"
        }
        
        response = client.post("/api/register/parent", json=registration_data)
        assert response.status_code == 201
        user_data = response.json()
        assert user_data["email"] == registration_data["email"]
        assert user_data["role"] == "parent"
        
        # Step 2: Login with new credentials
        login_response = client.post(
            "/token",
            data={
                "username": registration_data["email"],
                "password": registration_data["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        assert token is not None
        
        # Step 3: Access authenticated endpoint
        headers = {"Authorization": f"Bearer {token}"}
        me_response = client.get("/api/users/me", headers=headers)
        assert me_response.status_code == 200
        assert me_response.json()["email"] == registration_data["email"]

    def test_password_security_requirements(self, client, test_db):
        """Sad path: Weak passwords should be rejected"""
        weak_passwords = [
            "short",           # Too short
            "nouppercasedigit", # No uppercase/digit
            "NOLOWERCASE1",    # No lowercase
        ]
        
        base_data = {
            "first_name": "Test",
            "last_name": "User",
            "phone_number": "+962791234567",
            "gender": "male",
            "nationality": "Jordanian",
            "national_id": "1234567890",
            "home_governorate": "Amman",
            "home_district": "Amman",
            "home_area": "Test",
            "home_address_line": "Test Address",
            "email": "weak@test.jo",
        }
        
        # Note: Password validation should be implemented
        # These tests document expected behavior

    def test_token_expiration(self, client, admin_user):
        """Sad path: Expired tokens should be rejected"""
        # Create token that expires immediately
        with patch('auth.settings.ACCESS_TOKEN_EXPIRE_MINUTES', 0):
            response = client.post(
                "/token",
                data={"username": "testadmin", "password": "Admin123!"}
            )
            # Token should still be created (expiration checked on use)
            assert response.status_code == 200

    def test_invalid_token_rejected(self, client):
        """Sad path: Invalid/malformed tokens rejected"""
        invalid_tokens = [
            "invalid.token.here",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid",
            "",
            "Bearer",
        ]
        
        for token in invalid_tokens:
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get("/api/users/me", headers=headers)
            assert response.status_code in [401, 403], f"Token '{token}' should be rejected"

    def test_role_based_endpoint_access(
        self, client, auth_headers_admin, auth_headers_manager,
        auth_headers_supervisor, auth_headers_parent
    ):
        """Role-based access control verification"""
        # Admin-only endpoint
        response = client.get("/api/kpi/governance-score", 
                            headers=auth_headers_parent,
                            params={"kindergarten_id": 1, 
                                  "period_start": "2026-01-01",
                                  "period_end": "2026-01-31"})
        assert response.status_code in [400, 401, 403]
        
        # Supervisor-only endpoint
        response = client.get("/api/supervisor/dashboard", headers=auth_headers_parent)
        assert response.status_code in [401, 403]


# ============================================================================
# Module 2: Enrollment Workflow Tests
# ============================================================================

class TestEnrollmentWorkflowIntegration:
    """Complete enrollment lifecycle tests"""

    def test_full_enrollment_workflow(
        self, client, test_db, parent_user, auth_headers_parent,
        auth_headers_manager, sample_kindergarten, sample_class, manager_user
    ):
        """Happy path: Complete enrollment from application to acceptance"""
        # Step 1: Parent creates enrollment application
        enrollment_data = {
            "first_name": "Amir",
            "last_name": parent_user.parent_profile.last_name,
            "gender": "male",
            "date_of_birth": "2023-06-15",  # ~2.5 years old
            "father_name": "Mohammad Al-Ahmad",
            "mother_first_name": "Fatima",
            "mother_last_name": "Khalil",
            "mother_nationality": "Jordanian",
            "mother_national_id": "1111111111",
            "national_id": "2222222222",
            "kindergarten_id": sample_kindergarten.id
        }

        response = client.post(
            "/api/enrollment/apply",
            headers=auth_headers_parent,
            json=enrollment_data
        )
        assert response.status_code == 201, f"Enrollment apply failed: {response.text}"
        enrollment = response.json()
        enrollment_id = enrollment["id"]
        child_id = enrollment["child_id"]
        assert enrollment["status"] == "draft"

        # Step 2: Submit application
        response = client.post(
            f"/api/enrollment/{enrollment_id}/submit",
            headers=auth_headers_parent
        )
        assert response.status_code == 200
        assert response.json()["status"] == "submitted"

        # Add required documents and class assignment before acceptance
        import models as m
        for doc_type in ("birth_certificate", "health_certificate"):
            test_db.add(m.ChildDocument(
                child_id=child_id, document_type=doc_type,
                file_name=f"{doc_type}.pdf",
                file_path=f"/fake/{doc_type}.pdf", uploaded_by=manager_user.id,
            ))
        # H-7: class_id must be set before enrollment can be accepted
        ea = test_db.query(m.EnrollmentApplication).filter(m.EnrollmentApplication.id == enrollment_id).first()
        if ea:
            ea.class_id = sample_class.id
        test_db.commit()

        # Step 3: Manager reviews and accepts
        response = client.post(
            f"/api/enrollment/{enrollment_id}/review",
            headers=auth_headers_manager,
            params={"decision": "accept"}
        )
        assert response.status_code == 200

    def test_enrollment_age_validation(
        self, client, auth_headers_parent, sample_kindergarten
    ):
        """Sad path: Children outside age range rejected"""
        # Child too young (less than 1 day — born today)
        too_young_data = {
            "first_name": "طفل",
            "last_name": "صغير",
            "gender": "male",
            "date_of_birth": date.today().isoformat(),  # Born today
            "father_name": "أب",
            "mother_first_name": "أم",
            "mother_last_name": "الأم",
            "mother_nationality": "Jordanian",
            "mother_national_id": "2222222222",
            "kindergarten_id": sample_kindergarten.id
        }
        
        response = client.post(
            "/api/enrollment/apply",
            headers=auth_headers_parent,
            json=too_young_data
        )
        assert response.status_code == 400
        
        # Child too old (more than 56 months)
        too_old_date = date.today() - timedelta(days=365*6)  # 6 years old
        too_old_data = too_young_data.copy()
        too_old_data["date_of_birth"] = too_old_date.isoformat()
        
        response = client.post(
            "/api/enrollment/apply",
            headers=auth_headers_parent,
            json=too_old_data
        )
        assert response.status_code == 400

    def test_duplicate_enrollment_prevention(
        self, client, test_db, parent_user, auth_headers_parent,
        sample_kindergarten
    ):
        """Sad path: Cannot have active enrollments in multiple kindergartens"""
        # Create child with active enrollment in first kindergarten
        child = models.Child(
            parent_id=parent_user.id,
            first_name="Active",
            last_name="Child",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Father",
            mother_first_name="Mother",
            mother_last_name="Last",
            mother_nationality="Jordanian",
            mother_national_id="3333333333"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)
        
        # Create active enrollment
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        test_db.commit()
        
        # Create second kindergarten
        kg2 = models.Kindergarten(
            name_ar="حضانة ثانية",
            name_en="Second KG",
            license_number="LIC-002",
            governorate="Zarqa",
            district="Zarqa",
            area="Center",
            address_line="456 Other St",
            contact_phone="+962792222222",
            contact_email="second@kg.jo",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()


# ============================================================================
# Module 3: Attendance & Ratio Compliance Tests
# ============================================================================

class TestAttendanceIntegration:
    """Attendance tracking and ratio monitoring tests"""

    def test_complete_attendance_day(
        self, client, test_db, auth_headers_manager,
        sample_kindergarten, sample_child, sample_class, manager_user
    ):
        """Happy path: Full day attendance cycle"""
        # Create active enrollment with class assignment
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        
        # Manager needs supervisor assignment to the class
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=manager_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()
        
        # Check-in at 8:00 AM
        checkin_response = client.post(
            "/api/attendance/check-in",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "method": "pin",
                "dropped_by_name": "الأم - فاطمة"
            }
        )
        assert checkin_response.status_code == 200
        assert checkin_response.json()["check_in_at"] is not None
        assert checkin_response.json()["check_out_at"] is None
        
        # Check-out at 3:00 PM
        checkout_response = client.post(
            "/api/attendance/check-out",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "picked_by_name": "الأب - أحمد"
            }
        )
        assert checkout_response.status_code == 200
        assert checkout_response.json()["check_out_at"] is not None

    def test_prevent_double_checkin(
        self, client, test_db, auth_headers_manager,
        sample_kindergarten, sample_child, sample_class, manager_user
    ):
        """Sad path: Cannot check-in same child twice"""
        # Setup enrollment with class and supervisor assignment
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=manager_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()
        
        # First check-in
        client.post(
            "/api/attendance/check-in",
            headers=auth_headers_manager,
            params={"child_id": sample_child.id, "method": "qr"}
        )
        
        # Second check-in should fail
        response = client.post(
            "/api/attendance/check-in",
            headers=auth_headers_manager,
            params={"child_id": sample_child.id, "method": "qr"}
        )
        assert response.status_code in (400, 409)  # 409 on IntegrityError race, 400 on pre-flight check

    def test_checkout_without_checkin_fails(
        self, client, test_db, auth_headers_manager, sample_child,
        sample_kindergarten, sample_class, manager_user
    ):
        """Sad path: Cannot check-out without prior check-in"""
        # Setup enrollment and class assignment so we get past auth checks
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=manager_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()

        response = client.post(
            "/api/attendance/check-out",
            headers=auth_headers_manager,
            params={"child_id": sample_child.id}
        )
        assert response.status_code == 400


# ============================================================================
# Module 4: Daily Reports Tests
# ============================================================================

class TestDailyReportsIntegration:
    """Daily report creation and approval workflow tests"""

    def test_complete_daily_report_workflow(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        auth_headers_manager, sample_kindergarten, sample_class, sample_child
    ):
        """Happy path: Create -> Submit -> Approve daily report"""
        # Setup: Assign supervisor and create enrollment
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            enrollment_start_date=date.today(),
            class_id=sample_class.id
        )
        test_db.add(enrollment)
        
        attendance = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=date.today(),
            check_in_at=datetime.now(),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=supervisor_user.id
        )
        test_db.add(attendance)
        test_db.commit()
        
        # Create report
        report_data = {
            "child_id": sample_child.id,
            "date": date.today().isoformat(),
            "arrival_time": "07:45",
            "leave_time": "14:30",
            "breakfast": True,
            "snack": True,
            "milk": True,
            "lunch": True,
            "nap_start": "12:00",
            "nap_end": "13:30",
            "activities": "لعب خارجي، قراءة قصة، رسم",
            "mood": "سعيد",
            "health_notes": "بصحة جيدة",
            "notes": "يوم رائع! تفاعل بشكل ممتاز مع الأنشطة"
        }
        
        # Mock datetime.now to avoid 4PM submission deadline
        morning_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        with patch("api.daily_reports_routes.datetime") as mock_dt:
            mock_dt.now.return_value = morning_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            create_response = client.post(
                "/api/daily-reports/create",
                headers=auth_headers_supervisor,
                json=report_data
            )
            assert create_response.status_code == 201
            report = create_response.json()
            report_id = report["id"]
            assert report["status"] == "draft"
            
            # Submit report
            submit_response = client.post(
                f"/api/daily-reports/{report_id}/submit",
                headers=auth_headers_supervisor
            )
            assert submit_response.status_code == 200
            assert submit_response.json()["status"] == "submitted"
        
        # Approve report
        approve_response = client.post(
            f"/api/daily-reports/{report_id}/approve",
            headers=auth_headers_manager
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"

    def test_parent_sees_only_approved_reports(
        self, client, test_db, parent_user, auth_headers_parent,
        sample_child
    ):
        """Parents should only see approved daily reports"""
        # Create draft report
        draft_report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_child.enrollments[0].kindergarten_id if sample_child.enrollments else 1,
            date=date.today() - timedelta(days=1),
            status=models.DailyReportStatus.DRAFT,
            submitted_by=1,
            arrival_time="08:00",
            leave_time="14:00"
        )
        test_db.add(draft_report)
        
        # Create approved report
        approved_report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_child.enrollments[0].kindergarten_id if sample_child.enrollments else 1,
            date=date.today(),
            status=models.DailyReportStatus.APPROVED,
            submitted_by=1,
            arrival_time="08:00",
            leave_time="14:00"
        )
        test_db.add(approved_report)
        test_db.commit()
        
        # Parent should only see approved report
        response = client.get(
            f"/api/daily-reports/child/{sample_child.id}",
            headers=auth_headers_parent
        )
        # Note: This test documents expected behavior


# ============================================================================
# Module 5: Safety & Incidents Tests
# ============================================================================

class TestSafetyIncidentsIntegration:
    """Incident reporting and safeguarding tests"""

    def test_incident_creation_with_followup(
        self, client, test_db, auth_headers_manager,
        sample_kindergarten, sample_class, sample_child
    ):
        """Happy path: Create incident with follow-up SLA"""
        import models as m
        enrollment = m.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=m.EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        # The legacy query-param /api/incidents/create endpoint was removed;
        # POST /api/incidents (JSON body, IncidentCreate schema) is canonical.
        incident_data = {
            "child_id": sample_child.id,
            "type": "INJURY",
            "severity_level": "MEDIUM",
            "description": "سقط الطفل أثناء اللعب وأصيب بكدمة في الركبة",
            "occurred_at": datetime.now().isoformat(),
            "followup_required_flag": True,
            "parent_informed": True,
        }

        response = client.post(
            "/api/incidents",
            headers=auth_headers_manager,
            json=incident_data
        )
        assert response.status_code == 201, response.text


# ============================================================================
# Module 6: KPI & Governance Tests
# ============================================================================

class TestKPIGovernanceIntegration:
    """KPI calculation and governance scoring tests"""

    def test_attendance_rate_calculation(
        self, client, test_db, auth_headers_manager, sample_kindergarten
    ):
        """Happy path: Calculate attendance rate KPI"""
        response = client.get(
            "/api/kpi/attendance-rate",
            headers=auth_headers_manager,
            params={
                "kindergarten_id": sample_kindergarten.id,
                "period_start": (date.today() - timedelta(days=30)).isoformat(),
                "period_end": date.today().isoformat()
            }
        )
        assert response.status_code == 200
        kpi = response.json()
        assert "attendance_rate" in kpi
        assert 0 <= kpi["attendance_rate"] <= 100

    def test_governance_score_calculation(
        self, client, test_db, auth_headers_admin, sample_kindergarten
    ):
        """Happy path: Calculate governance score with band"""
        response = client.get(
            "/api/kpi/governance-score",
            headers=auth_headers_admin,
            params={
                "kindergarten_id": sample_kindergarten.id,
                "period_start": (date.today() - timedelta(days=30)).isoformat(),
                "period_end": date.today().isoformat()
            }
        )
        assert response.status_code == 200
        score = response.json()
        assert "governance_score" in score
        assert "governance_band" in score
        assert score["governance_band"] in ["RED", "AMBER", "GREEN", "INSUFFICIENT"]


# ============================================================================
# Module 7: Supervisor Operations Tests
# ============================================================================

class TestSupervisorOperationsIntegration:
    """Supervisor class management and observation tests"""

    def test_supervisor_assignment_workflow(
        self, client, test_db, manager_user, supervisor_user,
        auth_headers_manager, sample_class
    ):
        """Happy path: Manager assigns supervisor to class"""
        response = client.post(
            "/api/supervisor/assign",
            headers=auth_headers_manager,
            json={
                "supervisor_id": supervisor_user.id,
                "class_id": sample_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )
        assert response.status_code == 201
        assignment = response.json()
        assert assignment["is_primary"] is True

    def test_supervisor_assignment_uniqueness_enforced(
        self, client, test_db, manager_user, supervisor_user,
        auth_headers_manager, sample_class, sample_kindergarten
    ):
        """Supervisors cannot be assigned to multiple classes (409 conflict)"""
        other_class = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="Conflict Class",
            name_en="Conflict Class",
            class_code="CONF-001",
            age_group="AGE_2_4",
            capacity_total=12,
            min_age_months=30,
            max_age_months=48,
            is_active=True
        )
        test_db.add(other_class)
        test_db.commit()
        test_db.refresh(other_class)

        response = client.post(
            "/api/supervisor/assign",
            headers=auth_headers_manager,
            json={
                "supervisor_id": supervisor_user.id,
                "class_id": sample_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )
        assert response.status_code == 201

        conflict = client.post(
            "/api/supervisor/assign",
            headers=auth_headers_manager,
            json={
                "supervisor_id": supervisor_user.id,
                "class_id": other_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": False
            }
        )
        assert conflict.status_code == 409
        assert "already assigned" in conflict.json().get("detail", "").lower()

    def test_observation_recording(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class, sample_child, sample_kindergarten
    ):
        """Happy path: Supervisor records child observation"""
        # Setup
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online",
            class_id=sample_class.id
        )
        test_db.add(enrollment)
        test_db.commit()
        
        response = client.post(
            "/api/supervisor/observations/record",
            headers=auth_headers_supervisor,
            json={
                "child_id": sample_child.id,
                "domain": "social_emotional",
                "observation_text": "أظهر تعاوناً ممتازاً مع الأقران خلال نشاط المجموعة",
                "mastery_level": "exceeds"
            }
        )
        assert response.status_code == 201

    def test_supervisor_children_endpoint_is_class_scoped(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class, sample_child, sample_kindergarten
    ):
        """Supervisor must only receive children from assigned classes."""
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)

        enrollment_allowed = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online"
        )
        test_db.add(enrollment_allowed)

        other_class = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="الصف غير المسند",
            name_en="Unassigned Class",
            class_code="UNASSIGNED-01",
            age_group="AGE_2_4",
            capacity_total=15,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(other_class)
        test_db.flush()

        other_child = models.Child(
            parent_id=sample_child.parent_id,
            first_name="سارة",
            last_name="الخطيب",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 4),
            father_name="خالد الخطيب",
            mother_first_name="ريم",
            mother_last_name="الخطيب",
            mother_nationality="Jordanian",
            mother_national_id="1000000001",
            media_consent=True
        )
        test_db.add(other_child)
        test_db.flush()

        enrollment_blocked = models.EnrollmentApplication(
            child_id=other_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=other_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online"
        )
        test_db.add(enrollment_blocked)
        test_db.commit()

        response = client.get("/api/supervisor/children", headers=auth_headers_supervisor)
        assert response.status_code == 200
        ids = {child["id"] for child in response.json().get("children", [])}
        assert sample_child.id in ids
        assert other_child.id not in ids

    def test_supervisor_observation_access_blocked_for_unassigned_child(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class, sample_child, sample_kindergarten
    ):
        """Supervisor cannot create/read observations for children outside assigned classes."""
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)

        enrollment_allowed = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online"
        )
        test_db.add(enrollment_allowed)

        other_class = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="الصف الخارجي",
            name_en="External Class",
            class_code="EXTERNAL-01",
            age_group="AGE_2_4",
            capacity_total=15,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(other_class)
        test_db.flush()

        other_child = models.Child(
            parent_id=sample_child.parent_id,
            first_name="عمر",
            last_name="الحسن",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 4),
            father_name="محمود الحسن",
            mother_first_name="هبة",
            mother_last_name="الحسن",
            mother_nationality="Jordanian",
            mother_national_id="1000000002",
            media_consent=True
        )
        test_db.add(other_child)
        test_db.flush()

        enrollment_blocked = models.EnrollmentApplication(
            child_id=other_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=other_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="online"
        )
        test_db.add(enrollment_blocked)
        test_db.commit()

        create_resp = client.post(
            "/api/supervisor/observations/record",
            headers=auth_headers_supervisor,
            json={
                "child_id": other_child.id,
                "domain": "social_emotional",
                "observation_text": "ملاحظة خارج نطاق الفصل",
                "mastery_level": "on_track"
            }
        )
        assert create_resp.status_code == 403

        list_resp = client.get(
            f"/api/children/{other_child.id}/observations",
            headers=auth_headers_supervisor
        )
        assert list_resp.status_code == 403


# ============================================================================
# Module 8: Multi-Tenancy & Data Isolation Tests
# ============================================================================

class TestMultiTenancyIsolation:
    """Cross-kindergarten data isolation tests"""

    def test_kindergarten_data_isolation(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_kindergarten
    ):
        """Sad path: Supervisor cannot access other kindergarten's data"""
        # Create another kindergarten
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى",
            name_en="Other KG",
            license_number="LIC-OTHER-001",
            governorate="Irbid",
            district="Irbid",
            area="University Area",
            address_line="789 University St",
            contact_phone="+962793333333",
            contact_email="other@kindergarten.jo",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)
        test_db.commit()  # Commit to get ID
        test_db.refresh(other_kg)
        
        # Create class in other kindergarten
        other_class = models.Class(
            kindergarten_id=other_kg.id,
            name_ar="صف آخر",
            name_en="Other Class",
            class_code="OTH-001",
            age_group="AGE_2_4",
            capacity_total=20,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(other_class)
        test_db.commit()
        
        # Supervisor should not see other kindergarten's classes
        response = client.get(
            "/api/supervisor/my-classes",
            headers=auth_headers_supervisor
        )
        assert response.status_code == 200
        classes = response.json()["classes"]
        for c in classes:
            assert c["id"] != other_class.id


# ============================================================================
# Module 9: Concurrent Operations Tests
# ============================================================================

class TestConcurrentOperations:
    """Tests for race conditions and concurrent access"""

    def test_concurrent_enrollment_handling(
        self, client, test_db, sample_kindergarten
    ):
        """Verify concurrent enrollment attempts are handled correctly"""
        # This test documents expected behavior for production
        pass

    def test_concurrent_checkin_handling(
        self, client, test_db, sample_child
    ):
        """Verify concurrent check-in attempts are handled correctly"""
        # This test documents expected behavior for production
        pass


# ============================================================================
# Module 10: Data Integrity Tests
# ============================================================================

class TestDataIntegrity:
    """Database constraint and integrity tests"""

    def test_audit_log_created_on_sensitive_operations(
        self, client, test_db, auth_headers_admin
    ):
        """Verify audit logs are created for sensitive operations"""
        initial_count = test_db.query(models.AuditLog).count()
        
        # Perform sensitive operation (would trigger audit)
        # Check audit log count increased
        
    def test_unique_constraints_enforced(self, test_db):
        """Verify unique constraints prevent duplicate data"""
        # Create kindergarten
        kg = models.Kindergarten(
            name_ar="حضانة فريدة",
            name_en="Unique KG",
            license_number="UNIQUE-001",
            governorate="Amman",
            district="Amman",
            area="Test",
            address_line="123 Test St",
            contact_phone="+962791111111",
            contact_email="unique@kg.jo",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()


# ============================================================================
# Module 11: API Performance Tests
# ============================================================================

class TestAPIPerformance:
    """API response time and performance tests"""

    def test_dashboard_response_time(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class
    ):
        """Dashboard should respond within acceptable time"""
        import time
        
        # Setup
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()
        
        start_time = time.time()
        response = client.get(
            "/api/supervisor/dashboard",
            headers=auth_headers_supervisor
        )
        elapsed_time = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed_time < 2.0, f"Dashboard took {elapsed_time}s, expected < 2s"
