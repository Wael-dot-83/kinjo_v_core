"""
Tests for newly implemented endpoints:
- POST /api/staff/create
- POST /api/safeguarding/create
"""
import pytest
from datetime import date

import models
from auth import get_password_hash


# ============================================================================
# POST /api/staff/create
# ============================================================================

class TestStaffCreate:
    def test_admin_creates_staff(self, client, admin_token, sample_kindergarten):
        """Admin can create a staff member for any kindergarten"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "new_staff_member",
                "email": "staff@example.com",
                "password": "StaffPass123!",
                "kindergarten_id": sample_kindergarten.id,
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "new_staff_member"
        assert data["role"] == "SUPERVISOR"
        assert data["kindergarten_id"] == sample_kindergarten.id
        assert data["status"] == "ACTIVE"

    def test_manager_creates_staff_own_kg(self, client, manager_token, sample_kindergarten):
        """Manager can create staff for their own kindergarten"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "mgr_staff_01",
                "password": "StaffPass123!",
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "mgr_staff_01"
        assert data["role"] == "SUPERVISOR"
        assert data["kindergarten_id"] == sample_kindergarten.id

    def test_manager_cannot_create_staff_other_kg(self, client, manager_token):
        """Manager cannot create staff for a different kindergarten"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "other_staff",
                "password": "StaffPass123!",
                "kindergarten_id": 99999,
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 403

    def test_staff_create_rejects_admin_role(self, client, admin_token, sample_kindergarten):
        """Cannot create staff with ADMIN or MANAGER role"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "sneaky_admin",
                "password": "Pass123!",
                "kindergarten_id": sample_kindergarten.id,
                "role": "ADMIN"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_staff_create_rejects_manager_role(self, client, admin_token, sample_kindergarten):
        """Cannot create staff with MANAGER role"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "sneaky_manager",
                "password": "Pass123!",
                "kindergarten_id": sample_kindergarten.id,
                "role": "MANAGER"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_staff_create_duplicate_username(self, client, admin_token, sample_kindergarten):
        """Cannot create staff with existing username"""
        # First create
        client.post(
            "/api/staff/create",
            json={
                "username": "dup_staff_user",
                "password": "Pass123!",
                "kindergarten_id": sample_kindergarten.id,
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # Second attempt with same username
        response = client.post(
            "/api/staff/create",
            json={
                "username": "dup_staff_user",
                "password": "Pass456!",
                "kindergarten_id": sample_kindergarten.id,
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_supervisor_cannot_create_staff(self, client, supervisor_token):
        """Supervisors should not be able to create staff"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "blocked_staff",
                "password": "Pass123!",
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert response.status_code == 403

    def test_admin_must_specify_kg(self, client, admin_token):
        """Admin must specify kindergarten_id"""
        response = client.post(
            "/api/staff/create",
            json={
                "username": "no_kg_staff",
                "password": "Pass123!",
                "role": "SUPERVISOR"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400


# ============================================================================
# POST /api/safeguarding/create
# ============================================================================

class TestSafeguardingCreate:
    @pytest.fixture
    def enrolled_child(self, test_db, sample_kindergarten, parent_user):
        """Create a child with ACTIVE enrollment"""
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Sara",
            last_name="Test",
            gender=models.Gender.FEMALE,
            date_of_birth=date(2022, 6, 15),
            father_name="Father Test",
            mother_first_name="Mother",
            mother_last_name="Test",
            mother_nationality="Jordanian",
            mother_national_id="1111111111",
            media_consent=True
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()
        return child

    def test_manager_creates_safeguarding_case(
        self, client, manager_token, sample_kindergarten, enrolled_child
    ):
        """Manager can create a safeguarding case for enrolled child"""
        response = client.post(
            "/api/safeguarding/create",
            json={
                "child_id": enrolled_child.id,
                "case_description": "Potential concern noted during observation"
            },
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["child_id"] == enrolled_child.id
        assert data["kindergarten_id"] == sample_kindergarten.id
        assert "sla_escalation_deadline" in data
        assert "sla_closure_deadline" in data
        assert data["case_description"] == "Potential concern noted during observation"

    def test_admin_creates_safeguarding_case(
        self, client, admin_token, sample_kindergarten, enrolled_child
    ):
        """Admin can create a safeguarding case with explicit kindergarten_id"""
        response = client.post(
            "/api/safeguarding/create",
            json={
                "child_id": enrolled_child.id,
                "kindergarten_id": sample_kindergarten.id,
                "case_description": "Administrative safeguarding concern"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["child_id"] == enrolled_child.id

    def test_safeguarding_child_not_found(
        self, client, manager_token
    ):
        """Cannot create safeguarding case for non-existent child"""
        response = client.post(
            "/api/safeguarding/create",
            json={
                "child_id": 99999,
                "case_description": "Should fail"
            },
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 404

    def test_safeguarding_child_not_enrolled(
        self, client, manager_token, sample_child
    ):
        """Cannot create case for child not enrolled in the kindergarten"""
        response = client.post(
            "/api/safeguarding/create",
            json={
                "child_id": sample_child.id,
                "case_description": "Should fail - not enrolled with ACTIVE status"
            },
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 400

    def test_supervisor_cannot_create_safeguarding(
        self, client, supervisor_token, enrolled_child
    ):
        """Only managers and admins can create safeguarding cases"""
        response = client.post(
            "/api/safeguarding/create",
            json={
                "child_id": enrolled_child.id,
                "case_description": "Should not work"
            },
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert response.status_code == 403
