"""
Integration tests for KinJo platform
Tests end-to-end workflows across multiple modules
"""
import pytest
from datetime import date, datetime, timedelta
import models


class TestAuthenticationWorkflow:
    """
    Test authentication and authorization flows
    """

    def test_admin_login(self, client, admin_user):
        """Happy path: Admin can login"""
        response = client.post(
            "/token",
            data={"username": "testadmin", "password": "Admin123!"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_invalid_credentials(self, client):
        """Sad path: Login with invalid credentials fails"""
        response = client.post(
            "/token",
            data={"username": "nonexistent", "password": "wrongpass"}
        )
        assert response.status_code == 401

    def test_unauthenticated_access_denied(self, client):
        """Sad path: Unauthenticated requests should be denied"""
        response = client.get("/supervisor/dashboard")
        assert response.status_code == 401


class TestSupervisorAssignmentWorkflow:
    """
    Test supervisor assignment to classes
    """

    def test_manager_assign_supervisor_happy_path(
        self, client, test_db, manager_user, supervisor_user,
        auth_headers_manager, sample_class
    ):
        """Happy path: Manager assigns supervisor to class"""
        response = client.post(
            "/supervisor/assign",
            headers=auth_headers_manager,
            params={
                "supervisor_id": supervisor_user.id,
                "class_id": sample_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )
        assert response.status_code == 201
        assignment = response.json()
        assert assignment["supervisor_id"] == supervisor_user.id
        assert assignment["class_id"] == sample_class.id
        assert assignment["is_primary"] is True

    def test_manager_assign_replacement_supervisor(
        self, client, test_db, manager_user, supervisor_user,
        auth_headers_manager, sample_class, sample_kindergarten
    ):
        """Test manager assigning replacement supervisor"""
        # Create replacement supervisor
        replacement = models.User(
            username="replacement_super",
            email="replacement@test.com",
            hashed_password="hashed",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(replacement)
        test_db.commit()
        test_db.refresh(replacement)

        # Assign primary supervisor first
        client.post(
            "/supervisor/assign",
            headers=auth_headers_manager,
            params={
                "supervisor_id": supervisor_user.id,
                "class_id": sample_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )

        # Assign replacement for next week
        start_date = date.today() + timedelta(days=7)
        end_date = date.today() + timedelta(days=14)

        response = client.post(
            "/supervisor/assign-replacement",
            headers=auth_headers_manager,
            params={
                "class_id": sample_class.id,
                "replacement_supervisor_id": replacement.id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "reason": "Annual leave"
            }
        )
        assert response.status_code == 201
        assignment = response.json()
        assert assignment["replacement_supervisor_id"] == replacement.id
        assert assignment["class_id"] == sample_class.id

    def test_supervisor_cannot_be_double_assigned(
        self, client, test_db, manager_user, supervisor_user,
        auth_headers_manager, sample_class, sample_kindergarten
    ):
        """Sad path: Cannot assign supervisor to two classes simultaneously"""
        # Create second class
        class2 = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="الصف الثاني",
            name_en="Class B",
            capacity_total=20,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(class2)
        test_db.commit()
        test_db.refresh(class2)

        # Assign to first class
        response = client.post(
            "/supervisor/assign",
            headers=auth_headers_manager,
            params={
                "supervisor_id": supervisor_user.id,
                "class_id": sample_class.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )
        assert response.status_code == 201

        # Try to assign to second class (overlapping dates) - should fail
        response = client.post(
            "/supervisor/assign",
            headers=auth_headers_manager,
            params={
                "supervisor_id": supervisor_user.id,
                "class_id": class2.id,
                "start_date": date.today().isoformat(),
                "is_primary": True
            }
        )
        assert response.status_code == 400


class TestSupervisorOperations:
    """
    Test supervisor daily operations
    """

    def test_supervisor_view_assigned_classes(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class
    ):
        """Happy path: Supervisor can view their assigned classes"""
        # Assign supervisor to class
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()

        # Get assigned classes
        response = client.get(
            "/supervisor/my-classes",
            headers=auth_headers_supervisor
        )
        assert response.status_code == 200
        classes = response.json()
        assert len(classes["classes"]) >= 1

    def test_supervisor_dashboard(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_class
    ):
        """Happy path: Supervisor can view dashboard"""
        # Assign supervisor to class
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)
        test_db.commit()

        # Get dashboard
        response = client.get(
            "/supervisor/dashboard",
            headers=auth_headers_supervisor
        )
        assert response.status_code == 200
        dashboard = response.json()
        assert "classes" in dashboard
        assert "attendance_summary" in dashboard
        assert "total_children" in dashboard

    def test_supervisor_record_observation(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_kindergarten, sample_class, sample_child
    ):
        """Happy path: Supervisor records observation for child"""
        # Assign supervisor to class
        assignment = models.SupervisorAssignment(
            class_id=sample_class.id,
            supervisor_id=supervisor_user.id,
            is_primary=True,
            start_date=date.today()
        )
        test_db.add(assignment)

        # Create active enrollment
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE, source="online",
            submitted_at=datetime.now(),
            enrollment_start_date=date.today(),
            class_id=sample_class.id,
            class_assignment_date=date.today()
        )
        test_db.add(enrollment)
        test_db.commit()

        # Record observation
        response = client.post(
            "/supervisor/observations/record",
            headers=auth_headers_supervisor,
            params={
                "child_id": sample_child.id,
                "domain": "social_emotional",
                "observation_text": "Excellent sharing during group activities",
                "mastery_level": "on_track"
            }
        )
        assert response.status_code == 201
        observation = response.json()
        assert observation["domain"] == "social_emotional"
        assert observation["child_id"] == sample_child.id


class TestAttendanceWorkflow:
    """
    Test attendance check-in/out workflows
    """

    def test_checkin_checkout_workflow(
        self, client, test_db, sample_child, sample_kindergarten,
        manager_user, auth_headers_manager
    ):
        """Happy path: Check-in followed by check-out"""
        # Create active enrollment
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE, source="online",
            submitted_at=datetime.now(),
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        test_db.commit()

        # Check-in
        response = client.post(
            "/attendance/check-in",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "method": "pin",
                "dropped_by_name": "Mother"
            }
        )
        assert response.status_code == 200
        checkin = response.json()
        assert checkin["child_id"] == sample_child.id
        assert checkin["check_in_at"] is not None

        # Check-out
        response = client.post(
            "/attendance/check-out",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "picked_by_name": "Father"
            }
        )
        assert response.status_code == 200
        checkout = response.json()
        assert checkout["check_out_at"] is not None

    def test_duplicate_checkin_prevented(
        self, client, test_db, sample_child, sample_kindergarten,
        auth_headers_manager
    ):
        """Sad path: Cannot check-in same child twice on same day"""
        # Create active enrollment
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE, source="online",
            submitted_at=datetime.now(),
            enrollment_start_date=date.today()
        )
        test_db.add(enrollment)
        test_db.commit()

        # First check-in
        response = client.post(
            "/attendance/check-in",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "method": "pin",
                "dropped_by_name": "Mother"
            }
        )
        assert response.status_code == 200

        # Second check-in should fail
        response = client.post(
            "/attendance/check-in",
            headers=auth_headers_manager,
            params={
                "child_id": sample_child.id,
                "method": "pin",
                "dropped_by_name": "Father"
            }
        )
        assert response.status_code == 400


class TestDailyReportWorkflow:
    """
    Test daily report creation and submission
    """

    def test_create_and_submit_daily_report(
        self, client, test_db, supervisor_user, auth_headers_supervisor,
        sample_kindergarten, sample_class, sample_child
    ):
        """Happy path: Create and submit daily report"""
        # Setup: Assign supervisor and enroll child
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
            status=models.EnrollmentStatus.ACTIVE, source="online",
            submitted_at=datetime.now(),
            enrollment_start_date=date.today(),
            class_id=sample_class.id,
            class_assignment_date=date.today()
        )
        test_db.add(enrollment)

        # Check-in child
        attendance = models.AttendanceLog(
            child_id=sample_child.id,
            date=date.today(),
            check_in_at=datetime.now(),
            method=models.AttendanceMethod.PIN
        )
        test_db.add(attendance)
        test_db.commit()

        # Create daily report
        response = client.post(
            "/daily-reports/create",
            headers=auth_headers_supervisor,
            json={
                "child_id": sample_child.id,
                "date": date.today().isoformat(),
                "arrival_time": "07:30",
                "leave_time": "14:00",
                "breakfast": True,
                "lunch": True,
                "nap_start": "12:00",
                "nap_end": "13:30",
                "activities": "Outdoor play, story time, art project",
                "notes": "Great day, very engaged!"
            }
        )
        assert response.status_code == 201
        report = response.json()
        assert report["status"] == "draft"
        report_id = report["id"]

        # Submit daily report
        response = client.post(
            f"/daily-reports/{report_id}/submit",
            headers=auth_headers_supervisor
        )
        assert response.status_code == 200
        submitted = response.json()
        assert submitted["status"] == "submitted"


class TestPermissionsAndSecurity:
    """
    Test permission boundaries and multi-tenancy
    """

    def test_supervisor_cannot_access_other_kindergarten_children(
        self, client, test_db, supervisor_user, auth_headers_supervisor
    ):
        """Sad path: Supervisor cannot access children from other kindergartens"""
        # Create another kindergarten
        other_kg = models.Kindergarten(
            name_ar="روضة أخرى",
            name_en="Other KG",
            license_number="LIC-OTHER",
            governorate="Zarqa",
            city="Zarqa",
            area="Downtown",
            address_line="999 Other St",
            contact_phone="+962791111111",
            contact_email="other@kg.jo",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)

        # Create parent and child in other kindergarten
        other_user = models.User(
            username="other_parent@test.com",
            email="other_parent@test.com",
            hashed_password="hashed",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(other_user)
        test_db.commit()
        test_db.refresh(other_user)

        other_child = models.Child(
            parent_id=other_user.id,
            first_name="Other",
            last_name="Child",
            gender=models.Gender.MALE,
            date_of_birth=date(2022, 1, 1),
            father_name="Father Name",
            mother_first_name="Mother",
            mother_last_name="Name",
            mother_nationality="Jordanian",
            mother_national_id="1111111111"
        )
        test_db.add(other_child)
        test_db.commit()

        # Try to record observation for child from other kindergarten
        response = client.post(
            "/supervisor/observations/record",
            headers=auth_headers_supervisor,
            params={
                "child_id": other_child.id,
                "domain": "social_emotional",
                "observation_text": "Should not work",
                "mastery_level": "on_track"
            }
        )
        assert response.status_code in [403, 404, 400]

    def test_parent_cannot_access_other_parent_children(
        self, client, test_db, parent_user, auth_headers_parent
    ):
        """Sad path: Parent cannot access other parent's children data"""
        # Create another parent and child
        other_parent = models.User(
            username="other_p@test.com",
            email="other_p@test.com",
            hashed_password="hashed",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(other_parent)
        test_db.commit()

        other_child = models.Child(
            parent_id=other_parent.id,
            first_name="Someone",
            last_name="Else",
            gender=models.Gender.FEMALE,
            date_of_birth=date(2022, 6, 1),
            father_name="Father",
            mother_first_name="Mother",
            mother_last_name="Name",
            mother_nationality="Jordanian",
            mother_national_id="2222222222"
        )
        test_db.add(other_child)
        test_db.commit()

        # Try to get other child's daily reports
        response = client.get(
            f"/daily-reports/child/{other_child.id}",
            headers=auth_headers_parent
        )
        assert response.status_code in [403, 404]
