import pytest
from datetime import date, timedelta, datetime
import models

def test_kindergarten_crud_admin(client, test_db, admin_token, admin_user):
    """Test that an admin can create and list kindergartens"""
    
    # 1. Create Kindergarten
    kg_data = {
        "name_ar": "روضة المستقبل",
        "name_en": "Future KG",
        "governorate": "Irbid",
        "city": "Irbid",
        "area": "University St",
        "address_line": "Building 5",
        "contact_phone": "0799999999",
        "contact_email": "future@kg.com",
        "license_number": "LIC-TEST-001",
        "operating_hours_start": "08:00",
        "operating_hours_end": "14:00"
    }
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post("/api/kindergartens", json=kg_data, headers=headers)
    assert response.status_code == 201, f"Create failed: {response.text}"
    kg_id = response.json()["id"]

    # 2. List Kindergartens (should find it)
    response = client.get("/api/kindergartens", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    found = any(k["id"] == kg_id for k in data["kindergartens"])
    assert found


def test_kindergarten_creation_without_email_or_license(client, test_db, admin_token, admin_user):
    """Admin can create kindergarten without optional email/license fields"""
    kg_data = {
        "name_ar": "OñU^OOc O1O3OªU,O_",
        "name_en": "Hope KG",
        "governorate": "Amman",
        "city": "Amman",
        "area": "Downtown",
        "address_line": "Main street",
        "contact_phone": "0788888888",
        "operating_hours_start": "07:30",
        "operating_hours_end": "15:30"
    }

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post("/api/kindergartens", json=kg_data, headers=headers)
    assert response.status_code == 201, f"Create without email failed: {response.text}"
    payload = response.json()
    assert payload["contact_email"] is None
    assert payload.get("license_number") is None
    assert payload.get("license_valid_until") is None


def test_kindergarten_invalid_email_rejected(client, test_db, admin_token, admin_user):
    """Invalid email format should be rejected with 422"""
    kg_data = {
        "name_ar": "روضة البريد",
        "name_en": "Email KG",
        "governorate": "Amman",
        "city": "Amman",
        "area": "Web",
        "address_line": "Test street",
        "contact_phone": "0777777777",
        "contact_email": "not-an-email"
    }
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post("/api/kindergartens", json=kg_data, headers=headers)
    assert response.status_code == 422


def test_kindergarten_blank_optional_fields_become_null(client, test_db, admin_token, admin_user):
    """Blank optional strings should be normalized to null on create"""
    kg_data = {
        "name_ar": "روضة الفراغ",
        "name_en": "",
        "governorate": "Amman",
        "city": "Amman",
        "area": "Area",
        "address_line": "Line",
        "contact_phone": "0792222222",
        "contact_email": "   ",
        "license_number": "   ",
        "license_valid_until": ""
    }
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post("/api/kindergartens", json=kg_data, headers=headers)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["contact_email"] is None
    assert payload["license_number"] is None


def test_kindergarten_duplicate_phone_returns_code(client, test_db, admin_token, admin_user):
    """Duplicate phone should trigger clear duplicate error code"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    base_payload = {
        "name_ar": "روضة الهاتف 1",
        "name_en": "Phone KG 1",
        "governorate": "Amman",
        "city": "Amman",
        "area": "Area 1",
        "address_line": "Line 1",
        "contact_phone": "0791111111",
    }
    first = client.post("/api/kindergartens", json=base_payload, headers=headers)
    assert first.status_code == 201

    dup_payload = dict(base_payload)
    dup_payload["name_ar"] = "روضة الهاتف 2"
    second = client.post("/api/kindergartens", json=dup_payload, headers=headers)
    assert second.status_code == 400
    detail = second.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "error_duplicate_phone"
    assert "phone" in detail.get("message", "").lower()

def test_class_management_manager(client, test_db, manager_token, manager_user, sample_kindergarten):
    """Test Class creation and capacity checks"""
    
    # Ensure manager is linked to sample KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create Class
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف الأول",
        "name_en": "Grade 1",
        "capacity_total": 15,
        "min_age_months": 48,
        "max_age_months": 60
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers)
    assert response.status_code == 201, f"Create class failed: {response.text}"
    class_id = response.json()["id"]
    
    # 2. Check Capacity (should be empty)
    response = client.get(f"/api/classes/{class_id}/capacity-status", headers=headers)
    assert response.status_code == 200
    stats = response.json()
    assert stats["enrolled_count"] == 0
    assert stats["available_spots"] == 15

def test_enrollment_class_assignment(client, test_db, manager_token, manager_user, sample_kindergarten, parent_user):
    """Test assigning a child to a class"""
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # Setup: Create a class
    class_obj = models.Class(
        kindergarten_id=sample_kindergarten.id,
        name_ar="Bunnies",
        name_en="Bunnies",
        capacity_total=10,
        min_age_months=36,
        max_age_months=48,
        is_active=True
    )
    test_db.add(class_obj)
    test_db.flush()
    
    # Setup: Create a child (approx 40 months old to fit class)
    dob = date.today() - timedelta(days=40*30) 
    child = models.Child(
        parent_id=parent_user.parent_profile.id, # Using parent_user's parent_profile ID
        first_name="Leo",
        last_name="Test",
        date_of_birth=dob,
        gender=models.Gender.MALE,
        father_name="Leo Father",
        mother_first_name="Layla",
        mother_last_name="Test",
        mother_nationality="Jordanian"
    )
    test_db.add(child)
    test_db.flush()
    
    # Setup: Create ACTIVE enrollment
    enrollment = models.EnrollmentApplication(
        kindergarten_id=sample_kindergarten.id,
        child_id=child.id,
        status=models.EnrollmentStatus.ACTIVE,
        submitted_at=datetime.now()
    )
    test_db.add(enrollment)
    test_db.commit()
    
    # 1. Assign to Class
    response = client.post(
        f"/api/enrollments/{enrollment.id}/assign-class", 
        params={"class_id": class_obj.id}, # Endpoint expects query param or match endpoint sig? 
        # Checking logic: @router.post("/enrollments/{enrollment_id}/assign-class")
        # def assign_child_to_class(..., class_id: int, ...) 
        # By default FastAPI takes simple types as query params if not Path or Body
        headers=headers
    )
    
    assert response.status_code == 200, f"Assignment failed: {response.text}"
    data = response.json()
    assert data["class_id"] == class_obj.id
    
    # 2. Verify Dashboard Stats
    response = client.get("/api/manager/dashboard", headers=headers)
    assert response.status_code == 200
    dash = response.json()
    # Should have 1 active enrollment
    assert dash["summary"]["active_enrollments"] >= 1


def test_class_update_manager(client, test_db, manager_token, manager_user, sample_kindergarten):
    """Test Class update functionality"""
    
    # Ensure manager is linked to sample KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create Class
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف الأول",
        "name_en": "Grade 1",
        "capacity_total": 15,
        "min_age_months": 48,
        "max_age_months": 60
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers)
    assert response.status_code == 201
    class_id = response.json()["id"]
    
    # 2. Update Class
    update_data = {
        "name_ar": "الصف الأول المحدث",
        "name_en": "Updated Grade 1",
        "capacity_total": 20,
        "min_age_months": 50,
        "max_age_months": 65
    }
    
    response = client.put(f"/api/classes/{class_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    updated_class = response.json()
    assert updated_class["name_ar"] == "الصف الأول المحدث"
    assert updated_class["name_en"] == "Updated Grade 1"
    assert updated_class["capacity_total"] == 20
    assert updated_class["min_age_months"] == 50
    assert updated_class["max_age_months"] == 65


def test_class_deactivate_manager(client, test_db, manager_token, manager_user, sample_kindergarten):
    """Test Class deactivation (soft delete)"""
    
    # Ensure manager is linked to sample KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create Class
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف الثاني",
        "name_en": "Grade 2",
        "capacity_total": 12,
        "min_age_months": 60,
        "max_age_months": 72
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers)
    assert response.status_code == 201
    class_id = response.json()["id"]
    
    # 2. Deactivate Class
    response = client.put(f"/api/classes/{class_id}/deactivate", headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert "deactivated successfully" in result["message"]
    
    # 3. Verify class is inactive
    response = client.get("/api/classes", headers=headers)
    assert response.status_code == 200
    classes = response.json()["classes"]
    class_obj = next(c for c in classes if c["id"] == class_id)
    assert class_obj["is_active"] == False


def test_class_delete_admin_only(client, test_db, admin_token, manager_token, sample_kindergarten):
    """Test Class hard delete (admin only)"""
    
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create Class as admin
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف المؤقت",
        "name_en": "Temp Class",
        "capacity_total": 5,
        "min_age_months": 24,
        "max_age_months": 36
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers_admin)
    assert response.status_code == 201
    class_id = response.json()["id"]
    
    # 2. Try to delete as manager (should fail)
    response = client.delete(f"/api/classes/{class_id}", headers=headers_manager)
    assert response.status_code == 403
    
    # 3. Delete as admin (should succeed)
    response = client.delete(f"/api/classes/{class_id}", headers=headers_admin)
    assert response.status_code == 200
    result = response.json()
    assert "permanently deleted" in result["message"]
    
    # 4. Verify class is gone
    response = client.get(f"/api/classes/{class_id}", headers=headers_admin)
    assert response.status_code == 404


def test_class_deactivate_with_enrollments_fails(client, test_db, manager_token, manager_user, sample_kindergarten, parent_user):
    """Test that class deactivation fails when it has active enrollments"""
    
    # Ensure manager is linked to sample KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create Class
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف المشغول",
        "name_en": "Busy Class",
        "capacity_total": 10,
        "min_age_months": 36,
        "max_age_months": 48
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers)
    assert response.status_code == 201
    class_id = response.json()["id"]
    
    # 2. Create child and enrollment directly in database (since no API endpoint exists)
    child = models.Child(
        parent_id=parent_user.id,
        first_name="Test",
        last_name="Child",
        date_of_birth=date.today() - timedelta(days=40*30),
        gender=models.Gender.MALE,
        father_name="Test Father",
        mother_first_name="Test Mother",
        mother_last_name="Test Mother Last",
        mother_nationality="Jordanian"
    )
    test_db.add(child)
    test_db.flush()
    
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE
    )
    test_db.add(enrollment)
    test_db.flush()
    
    # Assign to class
    response = client.post(f"/api/enrollments/{enrollment.id}/assign-class?class_id={class_id}", headers=headers)
    assert response.status_code == 200
    
    # 3. Try to deactivate class (should fail)
    response = client.put(f"/api/classes/{class_id}/deactivate", headers=headers)
    assert response.status_code == 400
    result = response.json()
    assert "active enrollment" in result["detail"]


def test_class_reactivate_via_update(client, test_db, manager_token, manager_user, sample_kindergarten):
    """Test reactivating a class via update endpoint"""
    
    # Ensure manager is linked to sample KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    headers = {"Authorization": f"Bearer {manager_token}"}
    
    # 1. Create and deactivate Class
    class_data = {
        "kindergarten_id": sample_kindergarten.id,
        "name_ar": "الصف الخامل",
        "name_en": "Inactive Class",
        "capacity_total": 8,
        "min_age_months": 30,
        "max_age_months": 42
    }
    
    response = client.post("/api/classes", json=class_data, headers=headers)
    assert response.status_code == 201
    class_id = response.json()["id"]
    
    # Deactivate
    response = client.put(f"/api/classes/{class_id}/deactivate", headers=headers)
    assert response.status_code == 200
    
    # 2. Reactivate via update
    update_data = {"is_active": True}
    response = client.put(f"/api/classes/{class_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    updated_class = response.json()
    assert updated_class["is_active"] == True


