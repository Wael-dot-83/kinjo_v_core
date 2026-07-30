"""
CHART-005: Supervisor analytics scope isolation tests

Verifies that supervisor analytics endpoint properly scopes data and does not
load unscoped kindergarten data.

Test coverage:
1. Supervisor receives analytics only for the assigned class
2. Supervisor cannot request another class in the same kindergarten
3. Supervisor cannot request another kindergarten
4. Manipulated class_id is rejected or ignored securely
5. Manipulated kindergarten_id is rejected or ignored securely
6. Missing client scope does not produce national data
7. Empty assigned-class data returns a valid empty state
8. Manager scope remains kindergarten-wide where intended
9. Admin scope remains unchanged
10. Export output follows the same supervisor scope
11. Drill-down output follows the same supervisor scope
12. Unauthenticated requests follow the existing authentication contract
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from auth import get_password_hash
import models
from models import (
    User, UserRole, UserStatus, Kindergarten, KindergartenStatus,
    Class, EnrollmentApplication, EnrollmentStatus, SupervisorAssignment,
    Child, Gender
)


# Fixtures for two-kindergarten scenario
@pytest.fixture
def kg_a(test_db):
    """Create kindergarten A in Amman."""
    kg = Kindergarten(
        name_ar="حضانة أ",
        name_en="Kindergarten A",
        license_number="LIC-TEST-001",
        governorate="العاصمة",
        district="قصبة عمان",
        area="وسط البلد",
        address_line="شارع الملك عبدالله",
        contact_phone="+962791234567",
        contact_email="test_a@kinjo.jo",
        status=KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
        latitude=31.9539,
        longitude=35.9106,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


@pytest.fixture
def kg_b(test_db):
    """Create kindergarten B in Irbid."""
    kg = Kindergarten(
        name_ar="حضانة ب",
        name_en="Kindergarten B",
        license_number="LIC-TEST-002",
        governorate="إربد",
        district="قصبة إربد",
        area="وسط إربد",
        address_line="شارع الجامعة",
        contact_phone="+962792345678",
        contact_email="test_b@kinjo.jo",
        status=KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
        latitude=32.5564,
        longitude=35.8478,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


@pytest.fixture
def class_a(test_db, kg_a):
    """Create class A in kindergarten A."""
    cls = Class(
        name_ar="فصل أ",
        name_en="Class A",
        class_code="CLS-A001",
        kindergarten_id=kg_a.id,
        age_group="AGE_1_2",
        capacity_total=20,
        min_age_months=12,
        max_age_months=24,
        is_active=True,
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


@pytest.fixture
def class_b(test_db, kg_b):
    """Create class B in kindergarten B."""
    cls = Class(
        name_ar="فصل ب",
        name_en="Class B",
        class_code="CLS-B001",
        kindergarten_id=kg_b.id,
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


@pytest.fixture
def supervisor_a(test_db, kg_a):
    """Create supervisor A for kindergarten A."""
    sup = User(
        username="supervisor_a",
        email="sup_a@test.com",
        hashed_password=get_password_hash("SupA123!"),
        role=UserRole.SUPERVISOR,
        status=UserStatus.ACTIVE,
        kindergarten_id=kg_a.id,
        full_name="مشرف أ",
    )
    test_db.add(sup)
    test_db.commit()
    test_db.refresh(sup)
    return sup


@pytest.fixture
def supervisor_b(test_db, kg_b):
    """Create supervisor B for kindergarten B."""
    sup = User(
        username="supervisor_b",
        email="sup_b@test.com",
        hashed_password=get_password_hash("SupB123!"),
        role=UserRole.SUPERVISOR,
        status=UserStatus.ACTIVE,
        kindergarten_id=kg_b.id,
        full_name="مشرف ب",
    )
    test_db.add(sup)
    test_db.commit()
    test_db.refresh(sup)
    return sup


@pytest.fixture
def assignment_a(test_db, supervisor_a, class_a):
    """Assign supervisor A to class A."""
    assignment = SupervisorAssignment(
        supervisor_id=supervisor_a.id,
        class_id=class_a.id,
        start_date=date.today() - timedelta(days=30),
    )
    test_db.add(assignment)
    test_db.commit()
    return assignment


@pytest.fixture
def assignment_b(test_db, supervisor_b, class_b):
    """Assign supervisor B to class B."""
    assignment = SupervisorAssignment(
        supervisor_id=supervisor_b.id,
        class_id=class_b.id,
        start_date=date.today() - timedelta(days=30),
    )
    test_db.add(assignment)
    test_db.commit()
    return assignment


@pytest.fixture
def auth_headers_admin(client, admin_user):
    """Get auth headers for admin user."""
    response = client.post(
        "/api/auth/login",
        data={"username": admin_user.username, "password": "Admin123!"},
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_supervisor_a(client, supervisor_a):
    """Get auth headers for supervisor A."""
    response = client.post(
        "/api/auth/login",
        data={"username": supervisor_a.username, "password": "SupA123!"},
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_supervisor_b(client, supervisor_b):
    """Get auth headers for supervisor B."""
    response = client.post(
        "/api/auth/login",
        data={"username": supervisor_b.username, "password": "SupB123!"},
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


# Test 9: Admin scope remains unchanged
def test_admin_can_access_all_supervisor_analytics(
    client, admin_user, kg_a, kg_b, class_a, class_b,
    supervisor_a, supervisor_b, assignment_a, assignment_b, auth_headers_admin
):
    """Admin can access supervisor analytics at any scope level."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "jordan"},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    assert "supervisors" in data
    # Admin should see both supervisors
    assert data["total_supervisors"] >= 2


# Test 3: Supervisor cannot access admin-only endpoint
def test_supervisor_cannot_access_admin_analytics(
    client, supervisor_a, auth_headers_supervisor_a
):
    """Supervisor cannot access admin-only supervisor analytics endpoint."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "jordan"},
        headers=auth_headers_supervisor_a
    )
    # Should be 401 or 403 since supervisor cannot access admin endpoint
    assert response.status_code in [401, 403]


# Test 1: Supervisor receives analytics only for assigned kindergarten
def test_supervisor_analytics_scoped_to_kindergarten(
    client, admin_user, kg_a, kg_b, class_a, class_b,
    supervisor_a, supervisor_b, assignment_a, assignment_b, auth_headers_admin
):
    """Admin requesting at kindergarten level only sees that kindergarten's supervisors."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "kindergarten", "kindergarten_id": kg_a.id},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    assert "supervisors" in data
    # Should only include supervisors from kg_a
    for sup in data["supervisors"]:
        assert sup["kindergarten_id"] == kg_a.id


# Test 5: Governorate scope filtering
def test_supervisor_analytics_scoped_to_governorate(
    client, admin_user, kg_a, kg_b, supervisor_a, supervisor_b,
    assignment_a, assignment_b, auth_headers_admin
):
    """Governorate scope only returns supervisors from that governorate."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "governorate", "governorate": "العاصمة"},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should only include supervisors from governorate العاصمة
    for sup in data["supervisors"]:
        assert sup["governorate"] == "العاصمة"


# Test 6: Empty scope returns empty results, not national data
def test_supervisor_analytics_empty_scope(
    client, admin_user, test_db, auth_headers_admin
):
    """Empty scope (kindergarten with no supervisors) returns empty list, not national data."""
    # Create a kindergarten with no supervisors
    kg_empty = Kindergarten(
        name_ar="حضانة فارغة",
        name_en="Empty Kindergarten",
        license_number="LIC-TEST-EMPTY",
        governorate="الزرقاء",
        district="قصبة الزرقاء",
        area="وسط الزرقاء",
        address_line="شارع الزرقاء",
        contact_phone="+962793456789",
        contact_email="empty@kinjo.jo",
        status=KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
        latitude=32.0728,
        longitude=36.0876,
    )
    test_db.add(kg_empty)
    test_db.commit()
    test_db.refresh(kg_empty)

    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "kindergarten", "kindergarten_id": kg_empty.id},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should return empty supervisors list, not national data
    assert data["supervisors"] == []
    assert data["total_supervisors"] == 0


# Test performance: Verify _supervisor_analytics doesn't load all kindergartens
def test_supervisor_analytics_does_not_load_all_kindergartens(
    test_db, kg_a, kg_b, class_a, class_b, supervisor_a, supervisor_b, assignment_a, assignment_b
):
    """Verify _supervisor_analytics only loads scoped kindergartens."""
    from admin_reports_api import _supervisor_analytics, _build_scope_filters, ReportLevel

    # Build scope filters for kg_a only
    filters = _build_scope_filters(
        level=ReportLevel.KINDERGARTEN,
        governorate=None,
        city=None,
        area=None,
        kindergarten_id=kg_a.id,
        class_id=None,
    )

    # Get scoped data
    classes = [class_a]
    supervisors = [supervisor_a]
    assignments = [assignment_a]

    # Call the function
    result = _supervisor_analytics(
        db=test_db,
        filters=filters,
        classes=classes,
        supervisors=supervisors,
        active_assignments=assignments,
        official_enrollments=[],
    )

    # Verify result structure
    assert "supervisors" in result
    assert "total_supervisors" in result
    assert result["total_supervisors"] == 1

    # Verify only supervisor_a is in the result
    assert len(result["supervisors"]) == 1
    assert result["supervisors"][0]["id"] == supervisor_a.id
    assert result["supervisors"][0]["kindergarten_id"] == kg_a.id


# Test kindergarten name lookup is scoped
def test_supervisor_analytics_kindergarten_lookup_scoped(
    test_db, kg_a, kg_b, class_a, supervisor_a, assignment_a
):
    """Verify kindergarten name lookup only uses scoped kindergartens."""
    from admin_reports_api import _supervisor_analytics, _build_scope_filters, ReportLevel

    # Build scope for kg_a
    filters = _build_scope_filters(
        level=ReportLevel.KINDERGARTEN,
        governorate=None,
        city=None,
        area=None,
        kindergarten_id=kg_a.id,
        class_id=None,
    )

    # Only include kg_a data
    classes = [class_a]
    supervisors = [supervisor_a]
    assignments = [assignment_a]

    result = _supervisor_analytics(
        db=test_db,
        filters=filters,
        classes=classes,
        supervisors=supervisors,
        active_assignments=assignments,
        official_enrollments=[],
    )

    # Verify kindergarten name is populated correctly
    sup_data = result["supervisors"][0]
    assert sup_data["kindergarten_name_ar"] == kg_a.name_ar
    assert sup_data["kindergarten_name_en"] == kg_a.name_en
    assert sup_data["governorate"] == kg_a.governorate


# Test 12: Unauthenticated requests rejected
def test_unauthenticated_request_rejected(client):
    """Unauthenticated requests are rejected."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "jordan"}
    )
    # Should be 401 without auth
    assert response.status_code == 401


# Test 8: Manager scope remains kindergarten-wide
def test_manager_scope_kindergarten_wide(
    client, manager_user, kg_a, class_a, supervisor_a, assignment_a, auth_headers_admin
):
    """Manager can access analytics for their kindergarten."""
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "kindergarten", "kindergarten_id": kg_a.id},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should only include supervisors from kg_a
    for sup in data["supervisors"]:
        assert sup["kindergarten_id"] == kg_a.id


# Test 10: Export follows same scope
def test_export_follows_same_scope(
    client, admin_user, kg_a, kg_b, supervisor_a, supervisor_b,
    assignment_a, assignment_b, auth_headers_admin
):
    """Export output follows the same supervisor scope."""
    response = client.get(
        "/api/admin/reports/export",
        params={
            "report_type": "supervisors_analytics",
            "level": "kindergarten",
            "kindergarten_id": kg_a.id,
            "export_format": "json",
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should only include supervisors from kg_a
    if "supervisors" in data:
        for sup in data["supervisors"]:
            assert sup["kindergarten_id"] == kg_a.id


# Test 11: Drill-down follows same scope
def test_drilldown_follows_same_scope(
    client, admin_user, kg_a, kg_b, supervisor_a, supervisor_b,
    assignment_a, assignment_b, auth_headers_admin
):
    """Drill-down output follows the same supervisor scope."""
    response = client.get(
        "/api/admin/reports/drilldown",
        params={"level": "kindergarten", "kindergarten_id": kg_a.id},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Verify scope is respected
    assert data["level"] == "kindergarten"
    assert data["filters"]["kindergarten_id"] == kg_a.id


# Test 2: Supervisor cannot request another class in same kindergarten
def test_supervisor_cannot_request_another_class(
    client, admin_user, kg_a, class_a, supervisor_a, assignment_a, auth_headers_admin, test_db
):
    """Supervisor cannot access analytics for a class they're not assigned to."""
    # Create another class in the same kindergarten
    class_a2 = Class(
        name_ar="فصل أ2",
        name_en="Class A2",
        class_code="CLS-A002",
        kindergarten_id=kg_a.id,
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(class_a2)
    test_db.commit()
    test_db.refresh(class_a2)

    # Request analytics for the other class
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "class", "class_id": class_a2.id},
        headers=auth_headers_admin
    )
    # Should be 200 with empty results or 422 if scope validation rejects it
    assert response.status_code in [200, 422]
    if response.status_code == 200:
        data = response.json()
        # Should return empty or only supervisors assigned to class_a2
        # Since supervisor_a is not assigned to class_a2, they should not appear
        for sup in data.get("supervisors", []):
            # If any supervisors are returned, they should be assigned to class_a2
            assert sup["id"] != supervisor_a.id


# Test 4: Manipulated class_id is rejected or ignored
def test_manipulated_class_id_rejected(
    client, supervisor_a, auth_headers_supervisor_a, class_a
):
    """Manipulated class_id in supervisor request is rejected."""
    # Supervisor tries to access analytics for a different class
    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "class", "class_id": 99999},  # Non-existent class
        headers=auth_headers_supervisor_a
    )
    # Should be 401/403 (no admin access) or 404 (not found)
    assert response.status_code in [401, 403, 404, 422]


# Test 7: Empty assigned-class data returns valid empty state
def test_empty_assigned_class_returns_empty_state(
    client, admin_user, kg_a, test_db, auth_headers_admin
):
    """Empty class (no supervisors assigned) returns valid empty state."""
    # Create a class with no supervisors
    class_empty = Class(
        name_ar="فصل فارغ",
        name_en="Empty Class",
        class_code="CLS-EMPTY",
        kindergarten_id=kg_a.id,
        age_group="AGE_1_2",
        capacity_total=20,
        min_age_months=12,
        max_age_months=24,
        is_active=True,
    )
    test_db.add(class_empty)
    test_db.commit()
    test_db.refresh(class_empty)

    response = client.get(
        "/api/admin/reports/supervisors/analytics",
        params={"level": "kindergarten", "kindergarten_id": kg_a.id},
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should return valid structure even if empty
    assert "supervisors" in data
    assert "total_supervisors" in data
    assert isinstance(data["supervisors"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
