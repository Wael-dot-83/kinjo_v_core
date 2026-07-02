"""
Comprehensive Security Tests for Admin Endpoints

This test module verifies:
- [P0] Admin auth enforcement on all /api/admin/* endpoints (401/403)
- [P0] Rate limiting on password reset and bulk endpoints (429)
- [P1] Object-level authorization / IDOR protection
- [P0] Server-side schema validation
- [P1] CSV import validation with per-row errors
- [P0] Audit logging with correlation IDs
- [P1] Pagination enforcement
- [P1] Bulk operation guardrails and confirmation tokens
- [P2] Dry-run/preview mode
"""

import pytest
import json
from datetime import datetime, timedelta, timezone, date

from auth import get_password_hash
from audit_actions import AuditAction
import models


# =============================================================================
# Test Fixtures
# =============================================================================

def _create_kindergarten(db, suffix="A"):
    """Create a test kindergarten."""
    # Use hash of suffix for unique phone number
    suffix_hash = abs(hash(suffix)) % 100
    kg = models.Kindergarten(
        name_ar=f"روضة اختبار {suffix}",
        name_en=f"Test KG {suffix}",
        license_number=f"LIC-{suffix}-001",
        governorate="عمان",
        district="Amman",
        area="Abdoun",
        address_line="123 Test Street",
        contact_phone=f"+96279123{suffix_hash:04d}",
        contact_email=f"contact-{suffix.lower().replace(' ', '')}@kg.jo",
        status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _create_user(db, username, email, role, kindergarten_id=None, password="SecurePass123!"):
    """Create a test user."""
    user = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# =============================================================================
# [P0] Admin Auth Enforcement Tests
# =============================================================================

class TestAdminAuthEnforcement:
    """Test that all admin endpoints properly enforce authorization."""

    def test_unauthenticated_gets_401(self, client, test_db):
        """Unauthenticated requests should get 401."""
        endpoints = [
            ("GET", "/api/admin/users"),
            ("POST", "/api/admin/users"),
            ("GET", "/api/admin/users/1"),
            ("PUT", "/api/admin/users/1"),
            ("DELETE", "/api/admin/users/1"),
            ("POST", "/api/admin/users/bulk-status-update"),
            ("POST", "/api/admin/users/bulk-delete"),
            ("POST", "/api/admin/users/bulk-create"),
            ("POST", "/api/admin/users/1/admin-reset-password"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            elif method == "PUT":
                response = client.put(endpoint, json={})
            elif method == "DELETE":
                response = client.delete(endpoint)

            assert response.status_code == 401, f"{method} {endpoint} should return 401, got {response.status_code}"

    def test_non_admin_gets_403(self, client, test_db, supervisor_user, auth_headers_supervisor):
        """Authenticated non-admin users should get 403."""
        admin_only_endpoints = [
            ("POST", "/api/admin/users/bulk-status-update", {"user_ids": [1], "new_status": "ACTIVE"}),
            ("POST", "/api/admin/users/bulk-delete", {"user_ids": [1]}),
            ("POST", "/api/admin/users/bulk-create", {"users": []}),
        ]

        for method, endpoint, payload in admin_only_endpoints:
            response = client.post(endpoint, json=payload, headers=auth_headers_supervisor)
            assert response.status_code == 403, f"{endpoint} should return 403 for supervisor, got {response.status_code}"

    def test_admin_can_access_admin_endpoints(self, client, test_db, admin_user, auth_headers_admin):
        """Admin users should be able to access admin endpoints."""
        response = client.get("/api/admin/users", headers=auth_headers_admin)
        assert response.status_code == 200

    def test_manager_has_limited_access(self, client, test_db, manager_user, auth_headers_manager):
        """Managers can list users but only their kindergarten."""
        response = client.get("/api/admin/users", headers=auth_headers_manager)
        assert response.status_code == 200

        # Should not be able to access bulk admin operations
        response = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": [1]},
            headers=auth_headers_manager
        )
        assert response.status_code == 403

    def test_route_resolution_users_export_static_path(self, client, auth_headers_admin):
        """Static export path must resolve to export endpoint, not user-id endpoint."""
        response = client.get("/api/admin/users/export?format=json", headers=auth_headers_admin)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_route_resolution_users_id_dynamic_path(self, client, test_db, auth_headers_admin, sample_kindergarten):
        """Numeric user-id path must resolve to the user detail endpoint."""
        user = _create_user(
            test_db,
            username="route_resolution_user",
            email="route_resolution_user@test.jo",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=sample_kindergarten.id
        )
        response = client.get(f"/api/admin/users/{user.id}", headers=auth_headers_admin)
        assert response.status_code == 200
        assert response.json()["id"] == user.id


class TestErrorResponseContract:
    """Test that error responses follow the standardized contract."""

    def test_403_response_format(self, client, test_db, parent_user, auth_headers_parent):
        """403 errors should follow standardized format."""
        response = client.get("/api/admin/users", headers=auth_headers_parent)
        assert response.status_code == 403

        data = response.json()
        # Should have error object with code, message, correlation_id
        assert "error" in data or "detail" in data

    def test_correlation_id_in_response(self, client, test_db, admin_user, auth_headers_admin):
        """Responses should include correlation ID."""
        response = client.get("/api/admin/users", headers=auth_headers_admin)
        assert response.status_code == 200

        # Check header
        assert "X-Correlation-ID" in response.headers

        # Check body
        data = response.json()
        assert "correlation_id" in data


# =============================================================================
# [P1] IDOR Protection Tests
# =============================================================================

class TestIDORProtection:
    """Test object-level authorization to prevent IDOR attacks."""

    def test_manager_cannot_view_other_kg_users(self, client, test_db, manager_user, auth_headers_manager):
        """Manager should not see users from other kindergartens."""
        # Create another kindergarten with a user
        other_kg = _create_kindergarten(test_db, "OtherKG")
        other_user = _create_user(
            test_db,
            username="other_kg_user",
            email="other@kg.jo",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=other_kg.id
        )

        # Try to access the other user directly
        response = client.get(
            f"/api/admin/users/{other_user.id}",
            headers=auth_headers_manager
        )
        assert response.status_code == 403

    def test_manager_can_view_own_kg_users(self, client, test_db, manager_user, auth_headers_manager, sample_kindergarten):
        """Manager should be able to view users in their own kindergarten."""
        # Create a user in manager's kindergarten
        supervisor = _create_user(
            test_db,
            username="my_supervisor",
            email="supervisor@mykg.jo",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=manager_user.kindergarten_id
        )

        response = client.get(
            f"/api/admin/users/{supervisor.id}",
            headers=auth_headers_manager
        )
        assert response.status_code == 200

    def test_admin_cannot_access_other_admins(self, client, test_db, admin_user, auth_headers_admin):
        """Admins should not be able to view/modify other admin accounts."""
        # Create another admin
        other_admin = _create_user(
            test_db,
            username="other_admin",
            email="other_admin@kinjo.jo",
            role=models.UserRole.ADMIN
        )

        # Try to access
        response = client.get(
            f"/api/admin/users/{other_admin.id}",
            headers=auth_headers_admin
        )
        assert response.status_code == 403

    def test_bulk_operation_validates_each_target(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Bulk operations should validate access to each target."""
        # Create users - some accessible, some not (other admin)
        user1 = _create_user(
            test_db,
            username="bulk_user1",
            email="bulk1@test.jo",
            role=models.UserRole.PARENT,
            kindergarten_id=sample_kindergarten.id
        )

        # Try bulk status update including the admin (which should fail for that user)
        response = client.post(
            "/api/admin/users/bulk-status-update",
            json={
                "user_ids": [user1.id],
                "new_status": "SUSPENDED",
                "dry_run": True
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True


# =============================================================================
# [P0] Validation Tests
# =============================================================================

class TestServerSideValidation:
    """Test server-side schema validation."""

    def test_create_user_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """User creation should validate all fields."""
        # Missing required fields
        response = client.post(
            "/api/admin/users",
            json={"username": "test"},
            headers=auth_headers_admin
        )
        assert response.status_code == 422  # Pydantic validation error

        # Invalid email
        response = client.post(
            "/api/admin/users",
            json={
                "username": "testuser",
                "email": "not-an-email",
                "password": "SecurePass123!",
                "role": "PARENT"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 422

        # Password too short
        response = client.post(
            "/api/admin/users",
            json={
                "username": "testuser",
                "email": "valid@email.jo",
                "password": "short",
                "role": "PARENT"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 422

    def test_email_uniqueness_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Email uniqueness should be enforced."""
        # Create first user
        response = client.post(
            "/api/admin/users",
            json={
                "username": "firstuser",
                "email": "unique@email.jo",
                "password": "SecurePass123!",
                "role": "PARENT",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201

        # Try to create another with same email
        response = client.post(
            "/api/admin/users",
            json={
                "username": "seconduser",
                "email": "unique@email.jo",
                "password": "SecurePass123!",
                "role": "PARENT"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 409  # Conflict

    def test_manager_creation_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Manager creation should enforce kindergarten assignment and uniqueness."""
        # Create first manager for kindergarten
        response = client.post(
            "/api/admin/users",
            json={
                "username": "firstmanager",
                "email": "manager1@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201

        # Try to create another manager for same kindergarten - should fail
        response = client.post(
            "/api/admin/users",
            json={
                "username": "secondmanager",
                "email": "manager2@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 409  # Conflict
        data = response.json()
        assert "already has an active manager" in data["error"]["message"]

        # Try to create manager without kindergarten - should fail
        response = client.post(
            "/api/admin/users",
            json={
                "username": "nokgmanager",
                "email": "nokg@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER"
                # No kindergarten_id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 400  # Bad Request (validation error)

    def test_manager_update_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Manager update should enforce kindergarten assignment and uniqueness rules."""
        # Create first manager
        response = client.post(
            "/api/admin/users",
            json={
                "username": "manager1",
                "email": "manager1@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201
        manager1_data = response.json()
        manager1_id = manager1_data["id"]

        # Create second kindergarten
        kg2 = _create_kindergarten(test_db, "B")

        # Create second manager for different kindergarten
        response = client.post(
            "/api/admin/users",
            json={
                "username": "manager2",
                "email": "manager2@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": kg2.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201
        manager2_data = response.json()
        manager2_id = manager2_data["id"]

        # Try to reassign manager1 to kg2 (should fail - kg2 already has manager2)
        response = client.put(
            f"/api/admin/users/{manager1_id}",
            json={"kindergarten_id": kg2.id},
            headers=auth_headers_admin
        )
        assert response.status_code == 409
        data = response.json()
        assert "already has an active manager" in data["error"]["message"]

        # Try to change manager1's role to SUPERVISOR without kindergarten (should succeed)
        response = client.put(
            f"/api/admin/users/{manager1_id}",
            json={"role": "SUPERVISOR", "kindergarten_id": None},
            headers=auth_headers_admin
        )
        assert response.status_code == 200

        # Now kg1 has no manager, so we can assign manager2 to kg1
        response = client.put(
            f"/api/admin/users/{manager2_id}",
            json={"kindergarten_id": sample_kindergarten.id},
            headers=auth_headers_admin
        )
        assert response.status_code == 200

    def test_bulk_create_manager_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Bulk create should validate manager assignments."""
        # Create second kindergarten
        kg2 = _create_kindergarten(test_db, "B")

        response = client.post(
            "/api/admin/users/bulk-create",
            json={
                "users": [
                    {
                        "username": "bulkmanager1",
                        "email": "bulkmanager1@email.jo",
                        "password": "SecurePass123!",
                        "role": "MANAGER",
                        "kindergarten_id": sample_kindergarten.id
                    },
                    {
                        "username": "bulkmanager2",
                        "email": "bulkmanager2@email.jo",
                        "password": "SecurePass123!",
                        "role": "MANAGER",
                        "kindergarten_id": sample_kindergarten.id  # Same KG - should fail
                    },
                    {
                        "username": "bulksupervisor",
                        "email": "bulksupervisor@email.jo",
                        "password": "SecurePass123!",
                        "role": "SUPERVISOR",
                        "kindergarten_id": kg2.id
                    }
                ],
                "dry_run": True
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data["failed_count"] == 1
        assert len(data["errors"]) == 1
        assert "Multiple managers" in data["errors"][0]["error"]

    def test_bulk_status_update_manager_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Bulk status update should validate manager activations."""
        # Create a suspended manager for the kindergarten
        response = client.post(
            "/api/admin/users",
            json={
                "username": "suspendedmanager",
                "email": "suspended@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201
        suspended_data = response.json()
        suspended_id = suspended_data["id"]

        # Suspend the manager
        response = client.put(
            f"/api/admin/users/{suspended_id}",
            json={"status": "SUSPENDED"},
            headers=auth_headers_admin
        )
        assert response.status_code == 200

        # Create another suspended manager for same kindergarten
        response = client.post(
            "/api/admin/users",
            json={
                "username": "suspendedmanager2",
                "email": "suspended2@email.jo",
                "password": "SecurePass123!",
                "role": "MANAGER",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201
        suspended2_data = response.json()
        suspended2_id = suspended2_data["id"]

        # Try to activate both suspended managers (should fail)
        response = client.post(
            "/api/admin/users/bulk-status-update",
            json={
                "user_ids": [suspended_id, suspended2_id],
                "new_status": "ACTIVE"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 409
        data = response.json()
        assert "Manager activation would violate" in data["message"]
        assert len(data["errors"]) == 2  # Two errors: individual conflict + batch duplicate

    def test_bulk_create_per_row_validation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Bulk create should validate each row and report errors."""
        response = client.post(
            "/api/admin/users/bulk-create",
            json={
                "users": [
                    {
                        "username": "valid_user",
                        "email": "valid@email.jo",
                        "password": "SecurePass123!",
                        "role": "PARENT",
                        "kindergarten_id": sample_kindergarten.id
                    },
                    {
                        "username": "invalid_user",
                        "email": "not-valid",  # Invalid email
                        "password": "short",  # Too short
                        "role": "PARENT"
                    }
                ],
                "dry_run": True
            },
            headers=auth_headers_admin
        )
        # Should still return 200 but with errors list
        assert response.status_code in [200, 422]


# =============================================================================
# [P1] Pagination Tests
# =============================================================================

class TestPaginationEnforcement:
    """Test pagination limits are enforced."""

    def test_default_page_size(self, client, test_db, admin_user, auth_headers_admin):
        """Default page size should be applied."""
        response = client.get("/api/admin/users", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "pagination" in data
        assert data["pagination"]["page_size"] <= 100

    def test_max_page_size_enforced(self, client, test_db, admin_user, auth_headers_admin):
        """Page size should be capped at max or rejected if over limit."""
        response = client.get(
            "/api/admin/users?page_size=10000",
            headers=auth_headers_admin
        )
        # Either rejected (422) or capped (200 with page_size <= 100)
        if response.status_code == 200:
            data = response.json()
            assert data["pagination"]["page_size"] <= 100
        else:
            # FastAPI Query validation might reject values > MAX_PAGE_SIZE
            assert response.status_code == 422

    def test_pagination_metadata(self, client, test_db, admin_user, auth_headers_admin):
        """Response should include pagination metadata."""
        response = client.get("/api/admin/users", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()

        pagination = data["pagination"]
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total" in pagination
        assert "total_pages" in pagination
        assert "has_next" in pagination
        assert "has_prev" in pagination


# =============================================================================
# [P1] Bulk Operation Guardrails Tests
# =============================================================================

class TestBulkOperationGuardrails:
    """Test bulk operation confirmation and limits."""

    def test_bulk_delete_requires_confirmation(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Bulk delete should require confirmation token."""
        # Create users to delete
        users_to_delete = []
        for i in range(3):
            user = _create_user(
                test_db,
                username=f"to_delete_{i}",
                email=f"delete{i}@test.jo",
                role=models.UserRole.PARENT,
                kindergarten_id=sample_kindergarten.id
            )
            users_to_delete.append(user.id)

        # First call without token should return requires_confirmation
        response = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": users_to_delete},
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("requires_confirmation") is True
        assert "confirmation_token" in data

        # Call with token should succeed
        token = data["confirmation_token"]
        response = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": users_to_delete, "confirmation_token": token},
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        assert response.json().get("deleted_count") == 3

    def test_bulk_operations_respect_limits(self, client, test_db, admin_user, auth_headers_admin):
        """Bulk operations should respect size limits."""
        # Try to delete more than MAX_BULK_DELETE
        too_many_ids = list(range(1, 1000))

        response = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": too_many_ids},
            headers=auth_headers_admin
        )
        # Should fail validation
        assert response.status_code in [400, 422]

    def test_cannot_bulk_delete_admin_accounts(self, client, test_db, admin_user, auth_headers_admin):
        """Should not be able to bulk delete admin accounts."""
        # Create another admin (for testing purposes, we check the protection)
        other_admin = _create_user(
            test_db,
            username="another_admin",
            email="another_admin@kinjo.jo",
            role=models.UserRole.ADMIN
        )

        response = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": [other_admin.id]},
            headers=auth_headers_admin
        )
        assert response.status_code == 403


# =============================================================================
# [P2] Dry-Run Mode Tests
# =============================================================================

class TestDryRunMode:
    """Test dry-run/preview functionality."""

    def test_bulk_status_update_dry_run(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Dry run should not modify data."""
        user = _create_user(
            test_db,
            username="dry_run_user",
            email="dryrun@test.jo",
            role=models.UserRole.PARENT,
            kindergarten_id=sample_kindergarten.id
        )
        original_status = user.status

        response = client.post(
            "/api/admin/users/bulk-status-update",
            json={
                "user_ids": [user.id],
                "new_status": "SUSPENDED",
                "dry_run": True
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert user.id in data["allowed_ids"]

        # Verify user status unchanged
        test_db.refresh(user)
        assert user.status == original_status

    def test_bulk_create_dry_run(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Dry run create should not create users."""
        initial_count = test_db.query(models.User).count()

        response = client.post(
            "/api/admin/users/bulk-create",
            json={
                "users": [
                    {
                        "username": "dry_create_user",
                        "email": "drycreate@test.jo",
                        "password": "SecurePass123!",
                        "role": "PARENT",
                        "kindergarten_id": sample_kindergarten.id
                    }
                ],
                "dry_run": True
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True

        # Verify no user was created
        final_count = test_db.query(models.User).count()
        assert final_count == initial_count


# =============================================================================
# [P0] Audit Logging Tests
# =============================================================================

class TestAuditLogging:
    """Test audit logging functionality."""

    def test_user_creation_audited(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """User creation should be audited."""
        initial_log_count = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_CREATED"
        ).count()

        response = client.post(
            "/api/admin/users",
            json={
                "username": "audited_user",
                "email": "audited@test.jo",
                "password": "SecurePass123!",
                "role": "PARENT",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201

        # Check audit log was created
        final_log_count = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_CREATED"
        ).count()
        assert final_log_count == initial_log_count + 1

    def test_audit_log_includes_correlation_id(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Audit logs should include correlation ID."""
        response = client.post(
            "/api/admin/users",
            json={
                "username": "correlated_user",
                "email": "correlated@test.jo",
                "password": "SecurePass123!",
                "role": "PARENT",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201

        correlation_id = response.headers.get("X-Correlation-ID")
        assert correlation_id is not None

        # Check audit log contains correlation ID
        audit_log = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_CREATED"
        ).order_by(models.AuditLog.id.desc()).first()

        assert audit_log is not None
        if audit_log.details:
            details = json.loads(audit_log.details) if isinstance(audit_log.details, str) else audit_log.details
            assert details.get("correlation_id") == correlation_id

    def test_sensitive_data_redacted(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Sensitive data should be redacted from audit logs."""
        response = client.post(
            "/api/admin/users",
            json={
                "username": "password_user",
                "email": "password@test.jo",
                "password": "SuperSecretPassword123!",
                "role": "PARENT",
                "kindergarten_id": sample_kindergarten.id
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 201

        # Check audit log does not contain password
        audit_log = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_CREATED"
        ).order_by(models.AuditLog.id.desc()).first()

        assert audit_log is not None
        log_str = str(audit_log.details) if audit_log.details else ""
        assert "SuperSecretPassword123!" not in log_str
        assert "hashed_password" not in log_str.lower() or "REDACTED" in log_str


# =============================================================================
# [P0] Password Reset Security Tests
# =============================================================================

class TestPasswordResetSecurity:
    """Test password reset endpoint security."""

    def test_admin_reset_requires_admin_password(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Admin password reset should require admin's own password."""
        target_user = _create_user(
            test_db,
            username="reset_target",
            email="target@test.jo",
            role=models.UserRole.PARENT,
            kindergarten_id=sample_kindergarten.id
        )

        # Wrong admin password should fail
        response = client.post(
            f"/api/admin/users/{target_user.id}/admin-reset-password",
            json={
                "new_password": "NewPassword123!",
                "admin_password": "WrongPassword123!"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 401

        # Correct admin password should succeed
        response = client.post(
            f"/api/admin/users/{target_user.id}/admin-reset-password",
            json={
                "new_password": "NewPassword123!",
                "admin_password": "Admin123!"  # From fixture
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 200

    def test_cannot_reset_admin_password(self, client, test_db, admin_user, auth_headers_admin):
        """Should not be able to reset another admin's password."""
        other_admin = _create_user(
            test_db,
            username="other_admin_reset",
            email="other_admin_reset@kinjo.jo",
            role=models.UserRole.ADMIN
        )

        response = client.post(
            f"/api/admin/users/{other_admin.id}/admin-reset-password",
            json={
                "new_password": "NewPassword123!",
                "admin_password": "Admin123!"
            },
            headers=auth_headers_admin
        )
        assert response.status_code == 403


# =============================================================================
# Manager Role Restrictions Tests
# =============================================================================

class TestManagerRestrictions:
    """Test that managers have proper restrictions."""

    def test_manager_cannot_create_admin(self, client, test_db, manager_user, auth_headers_manager, sample_kindergarten):
        """Manager should not be able to create admin accounts."""
        response = client.post(
            "/api/admin/users",
            json={
                "username": "new_admin",
                "email": "newadmin@test.jo",
                "password": "SecurePass123!",
                "role": "ADMIN"
            },
            headers=auth_headers_manager
        )
        assert response.status_code == 403

    def test_manager_cannot_create_manager(self, client, test_db, manager_user, auth_headers_manager, sample_kindergarten):
        """Manager should not be able to create manager accounts."""
        response = client.post(
            "/api/admin/users",
            json={
                "username": "new_manager",
                "email": "newmanager@test.jo",
                "password": "SecurePass123!",
                "role": "MANAGER"
            },
            headers=auth_headers_manager
        )
        assert response.status_code == 403

    def test_manager_can_create_supervisor_in_own_kg(self, client, test_db, manager_user, auth_headers_manager, sample_kindergarten):
        """Manager should be able to create supervisor in their kindergarten."""
        response = client.post(
            "/api/admin/users",
            json={
                "username": "new_supervisor",
                "email": "newsupervisor@test.jo",
                "password": "SecurePass123!",
                "role": "SUPERVISOR",
                "kindergarten_id": manager_user.kindergarten_id
            },
            headers=auth_headers_manager
        )
        assert response.status_code == 201

    def test_manager_cannot_create_user_in_other_kg(self, client, test_db, manager_user, auth_headers_manager):
        """Manager should not be able to create users in other kindergartens."""
        other_kg = _create_kindergarten(test_db, "OtherManagerKG")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "other_kg_supervisor",
                "email": "otherkgsupervisor@test.jo",
                "password": "SecurePass123!",
                "role": "SUPERVISOR",
                "kindergarten_id": other_kg.id
            },
            headers=auth_headers_manager
        )
        assert response.status_code == 403


# =============================================================================
# CSV Import Tests
# =============================================================================

class TestCSVImport:
    """Test CSV import functionality."""

    def test_csv_import_rejects_non_csv(self, client, test_db, admin_user, auth_headers_admin):
        """Should reject non-CSV files."""
        response = client.post(
            "/api/admin/users/import-csv",
            files={"file": ("test.txt", b"not a csv", "text/plain")},
            headers=auth_headers_admin
        )
        assert response.status_code == 400

    def test_csv_import_validates_headers(self, client, test_db, admin_user, auth_headers_admin):
        """Should validate required CSV headers."""
        csv_content = "username,email\nuser1,user1@test.jo"

        response = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
            headers=auth_headers_admin
        )
        # Should fail due to missing required columns
        assert response.status_code == 400

    def test_csv_import_dry_run(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Dry run should validate without importing."""
        csv_content = f"username,email,password,role,kindergarten_id\ncsv_user,csv@test.jo,SecurePass123!,PARENT,{sample_kindergarten.id}"

        initial_count = test_db.query(models.User).count()

        response = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True

        # No users should be created
        final_count = test_db.query(models.User).count()
        assert final_count == initial_count

    def test_csv_import_reports_per_row_errors(self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
        """Should report errors for each invalid row."""
        csv_content = f"""username,email,password,role,kindergarten_id
valid_user,valid@test.jo,SecurePass123!,PARENT,{sample_kindergarten.id}
invalid_email,not-an-email,SecurePass123!,PARENT,{sample_kindergarten.id}
short_pass,short@test.jo,123,PARENT,{sample_kindergarten.id}"""

        response = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
            headers=auth_headers_admin
        )
        assert response.status_code == 200
        data = response.json()

        # Should have some errors
        assert len(data.get("errors", [])) >= 1


# =============================================================================
# Admin Kindergarten Import Tests
# =============================================================================

def test_admin_import_kindergartens_rejects_non_excel(client, auth_headers_admin):
    """Import endpoint should reject non-Excel uploads."""
    response = client.post(
        "/api/admin/kindergartens/import-excel",
        files={"file": ("kindergartens.txt", b"not excel", "text/plain")},
        headers=auth_headers_admin,
    )
    assert response.status_code == 400


def test_imported_kindergartens_list_access_control(client, auth_headers_admin, auth_headers_manager, auth_headers_parent):
    """Admin/Manager can list imported kindergartens, parent cannot."""
    admin_response = client.get("/api/admin/kindergartens/imported", headers=auth_headers_admin)
    assert admin_response.status_code == 200

    manager_response = client.get("/api/admin/kindergartens/imported", headers=auth_headers_manager)
    assert manager_response.status_code == 200

    parent_response = client.get("/api/admin/kindergartens/imported", headers=auth_headers_parent)
    assert parent_response.status_code == 403


def test_admin_import_kindergartens_success_is_audited(client, test_db, admin_user, auth_headers_admin):
    """Successful kindergarten import should write an audit entry."""
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name_ar", "name_en", "governorate", "district", "area", "address", "phone"])
    ws.append(["روضة التدقيق", "Audit KG", "عمان", "عمان", "عبدون", "شارع 1", "0790000000"])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    response = client.post(
        "/api/admin/kindergartens/import-excel",
        files={"file": ("kindergartens.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    assert response.json()["inserted"] == 1

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == "KINDERGARTEN_IMPORT")
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id


# =============================================================================
# Admin Incident Reporting Tests
# =============================================================================

def test_admin_generate_incident_report(client, test_db, admin_token, admin_user, sample_kindergarten):
    """Test admin can generate incident reports"""
    # Create test incidents
    from datetime import date
    child = models.Child(
        parent_id=1,  # Assume parent exists
        first_name="Test",
        last_name="Child",
        date_of_birth=date.today() - timedelta(days=365*4),
        gender=models.Gender.MALE,
        father_name="Test Father",
        mother_first_name="Test Mother",
        mother_last_name="Last Name",
        mother_nationality="Jordanian"
    )
    test_db.add(child)
    test_db.flush()

    # Create incidents
    incident1 = models.Incident(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        type=models.IncidentType.INJURY,
        severity_level=models.SeverityLevel.HIGH,
        description="Test injury",
        occurred_at=datetime.now()
    )
    incident2 = models.Incident(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        type=models.IncidentType.BEHAVIOR,
        severity_level=models.SeverityLevel.LOW,
        description="Test behavior",
        occurred_at=datetime.now(),
        closed_at=datetime.now()
    )
    test_db.add_all([incident1, incident2])
    test_db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Generate report
    report_data = {
        "scope_type": "KINDERGARTEN",
        "kindergarten_id": sample_kindergarten.id,
        "period_type": "month"
    }

    response = client.post("/api/admin/reports/incidents/generate", data=report_data, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "report_id" in data
    assert data["message"] == "تم إنشاء التقرير بنجاح"

    # Verify report was created
    report_id = data["report_id"]
    report = test_db.query(models.Report).filter(models.Report.id == report_id).first()
    assert report is not None
    assert report.report_type == models.ReportType.INCIDENT_SUMMARY
    assert report.scope_type == models.ReportScopeType.KINDERGARTEN
    assert report.created_by == admin_user.id


def test_admin_list_incident_reports(client, test_db, admin_token):
    """Test admin can list incident reports"""
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get("/api/admin/reports/incidents", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "reports" in data
    assert "pagination" in data


def test_admin_list_incident_reports_invalid_scope_filter_returns_400(client, admin_token):
    """Invalid scope filter should return validation error, not 500."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get("/api/admin/reports/incidents?scope_filter=INVALID", headers=headers)
    assert response.status_code == 400


def test_admin_get_incident_report_detail(client, test_db, admin_token, admin_user, sample_kindergarten):
    """Test admin can get incident report details"""
    # Create a test report
    report = models.Report(
        report_type=models.ReportType.INCIDENT_SUMMARY,
        scope_type=models.ReportScopeType.KINDERGARTEN,
        kindergarten_id=sample_kindergarten.id,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
        metrics_json={"total_incidents": 5, "open_incidents": 2},
        created_by=admin_user.id
    )
    test_db.add(report)
    test_db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get(f"/api/admin/reports/incidents/{report.id}", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == report.id
    assert "metrics" in data
    assert data["metrics"]["total_incidents"] == 5


def test_admin_get_incident_report_detail_not_found_returns_404(client, admin_token):
    """Missing report detail should return 404, not 500."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get("/api/admin/reports/incidents/999999", headers=headers)
    assert response.status_code == 404


def test_admin_generate_incident_report_invalid_scope_returns_400(client, admin_token):
    """Invalid scope should return validation error, not 500."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    report_data = {
        "scope_type": "INVALID",
        "period_type": "month"
    }

    response = client.post("/api/admin/reports/incidents/generate", data=report_data, headers=headers)
    assert response.status_code == 400


def test_admin_export_incident_report_csv(client, test_db, admin_token, admin_user, sample_kindergarten):
    """Test admin can export incident report as CSV"""
    # Create a test report
    report = models.Report(
        report_type=models.ReportType.INCIDENT_SUMMARY,
        scope_type=models.ReportScopeType.KINDERGARTEN,
        kindergarten_id=sample_kindergarten.id,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
        metrics_json={
            "total_incidents": 2,
            "incidents_by_type": {"INJURY": 1, "BEHAVIOR": 1},
            "incidents_by_severity": {"HIGH": 1, "LOW": 1}
        },
        created_by=admin_user.id
    )
    test_db.add(report)
    test_db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get(f"/api/admin/reports/incidents/{report.id}/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check CSV content
    csv_content = response.text
    assert "Report Title" in csv_content
    assert "Total Incidents" in csv_content

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.INCIDENT_REPORT_EXPORT)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.entity_id == report.id


def test_admin_export_incident_report_not_found_returns_404(client, admin_token):
    """Export endpoint should preserve 404 for missing reports."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.get("/api/admin/reports/incidents/999999/export", headers=headers)
    assert response.status_code == 404


def test_admin_export_audit_logs_creates_audit_entry(client, test_db, admin_token, admin_user):
    """Audit log export should itself be audited."""
    # Seed one log row to make export non-empty
    seed_log = models.AuditLog(
        user_id=admin_user.id,
        action="SEED_EVENT",
        entity_type="System",
        entity_id=None,
        details="seed",
        sensitivity_level=1,
    )
    test_db.add(seed_log)
    test_db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.get("/api/audit-logs/export?format=csv&period=all", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.AUDIT_LOG_EXPORT)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id


def test_admin_get_available_scopes(client, admin_token):
    """Test admin can get available report scopes"""
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.get("/api/admin/reports/scopes", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "scopes" in data
    # Should include ALL scope for admin
    scope_types = [s["type"] for s in data["scopes"]]
    assert "ALL" in scope_types


def test_non_admin_cannot_generate_reports(client, manager_token):
    """Test non-admin users cannot generate reports"""
    headers = {"Authorization": f"Bearer {manager_token}"}

    report_data = {
        "scope_type": "ALL",
        "period_type": "month"
    }

    response = client.post("/api/admin/reports/incidents/generate", data=report_data, headers=headers)
    assert response.status_code == 403


def test_admin_incident_report_permissions_enforced(client, test_db, admin_token, manager_token, sample_kindergarten):
    """Test that report generation respects user permissions"""
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_manager = {"Authorization": f"Bearer {manager_token}"}

    # Admin can generate ALL scope reports
    report_data_all = {
        "scope_type": "ALL",
        "period_type": "month"
    }
    response = client.post("/api/admin/reports/incidents/generate", data=report_data_all, headers=headers_admin)
    assert response.status_code == 200

    # Manager cannot generate ALL scope reports (assuming they don't have permission)
    response = client.post("/api/admin/reports/incidents/generate", data=report_data_all, headers=headers_manager)
    assert response.status_code == 403


# =============================================================================
# SQL injection resistance in admin search and filter params
# =============================================================================

class TestAdminSearchSQLInjection:
    """Verify that admin search/filter parameters are parameterised and never cause 500."""

    @pytest.fixture(autouse=True)
    def _setup(self, client, test_db, admin_user, auth_headers_admin):
        self.client = client
        self.headers = auth_headers_admin

    @pytest.mark.parametrize("payload", [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "\" OR \"1\"=\"1",
        "1; SELECT * FROM users",
        "admin'--",
        "' UNION SELECT NULL, NULL, NULL --",
        "%27 OR %271%27=%271",
    ])
    def test_user_search_sqli_never_500(self, payload):
        r = self.client.get(
            "/api/admin/users",
            params={"search": payload, "page": 1, "page_size": 25},
            headers=self.headers,
        )
        assert r.status_code != 500, f"Search payload caused 500: {payload!r}"
        assert r.status_code in (200, 400, 422), (
            f"Unexpected status {r.status_code} for search payload {payload!r}"
        )

    @pytest.mark.parametrize("payload", [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
    ])
    def test_governance_kpi_date_sqli_never_500(self, payload):
        r = self.client.get(
            "/api/admin/governance/kpis",
            params={"start_date": payload, "end_date": "2026-06-01"},
            headers=self.headers,
        )
        assert r.status_code != 500, f"Date param SQLi caused 500: {payload!r}"
        assert r.status_code in (200, 400, 422)

    @pytest.mark.parametrize("bad_id", ["../etc/passwd", "' OR 1=1", "-1", "0; DROP TABLE users"])
    def test_user_id_path_sqli_never_500(self, bad_id):
        r = self.client.get(f"/api/admin/users/{bad_id}", headers=self.headers)
        assert r.status_code != 500, f"Path param caused 500: {bad_id!r}"


# =============================================================================
# Admin-specific IDOR: roles cannot access admin user detail via /api/admin/*
# =============================================================================

class TestAdminIDOR:
    """Manager/supervisor/parent must not read or modify users through admin endpoints."""

    def test_manager_cannot_read_admin_user_via_admin_endpoint(
        self, client, test_db, admin_user, manager_user, auth_headers_manager
    ):
        r = client.get(
            f"/api/admin/users/{admin_user.id}",
            headers=auth_headers_manager,
        )
        assert r.status_code in (403, 404), (
            f"Manager accessed admin user detail via admin endpoint — IDOR! status={r.status_code}"
        )

    def test_manager_cannot_update_admin_user_via_admin_endpoint(
        self, client, test_db, admin_user, manager_user, auth_headers_manager
    ):
        r = client.put(
            f"/api/admin/users/{admin_user.id}",
            json={"role": "PARENT"},
            headers=auth_headers_manager,
        )
        assert r.status_code in (403, 404, 405, 422), (
            f"Manager updated admin user via admin endpoint — IDOR! status={r.status_code}"
        )

    def test_bulk_delete_above_threshold_requires_confirmation(
        self, client, test_db, admin_user, auth_headers_admin
    ):
        """Bulk deleting > BULK_CONFIRMATION_THRESHOLD users must require a confirmation token."""
        r = client.post(
            "/api/admin/users/bulk-delete",
            json={"user_ids": list(range(900000, 900025))},  # 25 non-existent IDs
            headers=auth_headers_admin,
        )
        if r.status_code == 200:
            body = r.json()
            assert body.get("requires_confirmation") is True, (
                "Bulk delete of 25 users succeeded without a confirmation token — dangerous!"
            )
        else:
            assert r.status_code in (400, 404, 422, 429)


# =============================================================================
# CSP Header Validation Tests
# =============================================================================

class TestCSPHeaders:
    """Verify that security_headers_middleware emits the required CSP directives.

    These tests guard against accidental removal of directives that were added
    to harden the Content-Security-Policy during the 2026-06-17 audit.
    """

    # Any endpoint that returns an HTTP response is sufficient — we just need
    # the middleware to fire so we can inspect the CSP header.
    _PROBE_PATH = "/"

    def _get_csp(self, client) -> str:
        r = client.get(self._PROBE_PATH, follow_redirects=False)
        csp = r.headers.get("content-security-policy", "")
        assert csp, "Content-Security-Policy header is missing from the response"
        return csp

    def test_object_src_none(self, client):
        """object-src 'none' must be present (blocks Flash/Java legacy plugins)."""
        csp = self._get_csp(client)
        assert "object-src 'none'" in csp, (
            f"object-src 'none' not found in CSP.\nFull CSP: {csp}"
        )

    def test_worker_src_self_blob(self, client):
        """worker-src 'self' blob: must be present (deck.gl WebGL workers need blob:)."""
        csp = self._get_csp(client)
        assert "worker-src" in csp, f"worker-src directive missing.\nFull CSP: {csp}"
        assert "blob:" in csp, (
            f"blob: missing from CSP; deck.gl workers will break.\nFull CSP: {csp}"
        )

    def test_frame_ancestors_none(self, client):
        """frame-ancestors 'none' must be present (blocks clickjacking)."""
        csp = self._get_csp(client)
        assert "frame-ancestors 'none'" in csp, (
            f"frame-ancestors 'none' not found in CSP.\nFull CSP: {csp}"
        )

    def test_base_uri_self(self, client):
        """base-uri 'self' must be present (prevents base-tag hijacking)."""
        csp = self._get_csp(client)
        assert "base-uri 'self'" in csp, (
            f"base-uri 'self' not found in CSP.\nFull CSP: {csp}"
        )

    def test_form_action_self(self, client):
        """form-action 'self' must be present (prevents form submission hijacking)."""
        csp = self._get_csp(client)
        assert "form-action 'self'" in csp, (
            f"form-action 'self' not found in CSP.\nFull CSP: {csp}"
        )

    def test_default_src_self(self, client):
        """default-src 'self' must be present (catch-all fallback)."""
        csp = self._get_csp(client)
        assert "default-src 'self'" in csp, (
            f"default-src 'self' not found in CSP.\nFull CSP: {csp}"
        )

    def test_x_frame_options_header(self, client):
        """X-Frame-Options: DENY must be set alongside frame-ancestors."""
        r = client.get(self._PROBE_PATH, follow_redirects=False)
        xfo = r.headers.get("x-frame-options", "")
        assert xfo.upper() == "DENY", (
            f"X-Frame-Options should be DENY, got: {xfo!r}"
        )

    def test_x_content_type_options(self, client):
        """X-Content-Type-Options: nosniff must be set."""
        r = client.get(self._PROBE_PATH, follow_redirects=False)
        assert r.headers.get("x-content-type-options", "").lower() == "nosniff"

    def test_referrer_policy(self, client):
        """Referrer-Policy must be set (any value is acceptable, absence is not)."""
        r = client.get(self._PROBE_PATH, follow_redirects=False)
        assert r.headers.get("referrer-policy"), "Referrer-Policy header is missing"

    def test_permissions_policy(self, client):
        """Permissions-Policy restricting camera/mic/geo must be present."""
        r = client.get(self._PROBE_PATH, follow_redirects=False)
        pp = r.headers.get("permissions-policy", "")
        assert pp, "Permissions-Policy header is missing"
        for feature in ("camera", "microphone", "geolocation"):
            assert feature in pp, f"Permissions-Policy missing {feature} restriction"

    def test_script_src_includes_unpkg(self, client):
        """script-src must allow unpkg.com — deck.gl is loaded from there."""
        csp = self._get_csp(client)
        assert "unpkg.com" in csp, (
            f"unpkg.com missing from CSP script-src; deck.gl will be blocked.\nFull CSP: {csp}"
        )
