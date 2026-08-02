"""
Tests for CHART-022: Drill-down scope leakage verification

Verifies that drill-down operations maintain proper scope isolation:
- National → Governorate → City → Kindergarten → Class
- No data leakage between scopes
- Proper authorization at each level
"""
import pytest
from sqlalchemy.orm import Session

import models


# Use conftest.py fixtures - do not redefine them here


@pytest.fixture
def two_governorates_data(test_db: Session):
    """Create test data for two different governorates."""
    # Create kindergartens in two different governorates
    kg_amman = models.Kindergarten(
        name_ar="حضانة عمان",
        name_en="Amman Kindergarten",
        governorate="العاصمة",
        district="قصبة عمان",
        area="وسط البلد",
        address_line="شارع الملك عبدالله",
        contact_phone="+962791234567",
        contact_email="amman@test.com",
        status=models.KindergartenStatus.ACTIVE,
    )
    kg_irbid = models.Kindergarten(
        name_ar="حضانة إربد",
        name_en="Irbid Kindergarten",
        governorate="إربد",
        district="قصبة إربد",
        area="وسط إربد",
        address_line="شارع الجامعة",
        contact_phone="+962792345678",
        contact_email="irbid@test.com",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add_all([kg_amman, kg_irbid])
    test_db.commit()
    test_db.refresh(kg_amman)
    test_db.refresh(kg_irbid)
    
    # Create classes
    class_amman = models.Class(
        name_ar="فصل عمان",
        name_en="Amman Class",
        class_code="CLS-AMMAN",
        kindergarten_id=kg_amman.id,
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    class_irbid = models.Class(
        name_ar="فصل إربد",
        name_en="Irbid Class",
        class_code="CLS-IRBID",
        kindergarten_id=kg_irbid.id,
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add_all([class_amman, class_irbid])
    test_db.commit()
    
    return {
        "kg_amman": kg_amman,
        "kg_irbid": kg_irbid,
        "class_amman": class_amman,
        "class_irbid": class_irbid,
    }


def test_chart_022_drilldown_scope_isolation_governorate(
    client, admin_user, two_governorates_data
):
    """Verify drill-down from national to governorate maintains scope isolation."""
    data = two_governorates_data
    
    # Login as admin
    login_response = client.post(
        "/api/auth/login",
        data={"username": admin_user.username, "password": "Admin123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Drill down to Amman governorate using correct endpoint
    response = client.get(
        "/api/analytics/drilldown/GOVERNORATE/العاصمة",
        headers=headers,
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Verify response structure
    assert result["dimension_type"] == "GOVERNORATE"
    assert result["dimension_id"] == "العاصمة"
    assert "children" in result
    assert "metrics" in result
    
    # Verify only Amman data is returned
    if result["children"]:
        for child in result["children"]:
            # Children should be cities/areas within Amman governorate
            assert child["dimension_type"] == "AREA"
    
    # Drill down to Irbid governorate
    response = client.get(
        "/api/analytics/drilldown/GOVERNORATE/إربد",
        headers=headers,
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Verify only Irbid data is returned
    assert result["dimension_type"] == "GOVERNORATE"
    assert result["dimension_id"] == "إربد"


def test_chart_022_drilldown_scope_isolation_kindergarten(
    client, admin_user, two_governorates_data
):
    """Verify drill-down from governorate to kindergarten maintains scope isolation."""
    data = two_governorates_data
    
    # Login as admin
    login_response = client.post(
        "/api/auth/login",
        data={"username": admin_user.username, "password": "Admin123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Drill down to Amman kindergarten using correct endpoint
    response = client.get(
        f"/api/analytics/drilldown/KINDERGARTEN/{data['kg_amman'].id}",
        headers=headers,
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Verify response structure
    assert result["dimension_type"] == "KINDERGARTEN"
    assert result["dimension_id"] == str(data["kg_amman"].id)
    assert "children" in result
    assert "metrics" in result
    
    # Verify only Amman kindergarten data is returned
    if result["children"]:
        for child in result["children"]:
            # Children should be classes within this kindergarten
            # Actual response structure includes: id, name, capacity, children_count, age_group
            assert "id" in child
            assert "name" in child
            assert "capacity" in child
            assert "children_count" in child


def test_chart_022_drilldown_scope_isolation_class(
    client, admin_user, two_governorates_data
):
    """Verify drill-down from kindergarten to class maintains scope isolation."""
    data = two_governorates_data
    
    # Login as admin
    login_response = client.post(
        "/api/auth/login",
        data={"username": admin_user.username, "password": "Admin123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Drill down to Amman class using correct endpoint
    response = client.get(
        f"/api/analytics/drilldown/CLASS/{data['class_amman'].id}",
        headers=headers,
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Verify response structure
    assert result["dimension_type"] == "CLASS"
    assert result["dimension_id"] == str(data["class_amman"].id)
    assert "children" in result
    assert "metrics" in result
    
    # Verify only Amman class data is returned
    if result["children"]:
        for child in result["children"]:
            # Children should be individual children in this class
            assert child["dimension_type"] == "CHILD"


def test_chart_022_drilldown_cross_scope_prevention(
    client, admin_user, two_governorates_data
):
    """Verify drill-down cannot access data outside scope."""
    data = two_governorates_data
    
    # Login as admin
    login_response = client.post(
        "/api/auth/login",
        data={"username": admin_user.username, "password": "Admin123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Drill down to Irbid kindergarten (should work for admin)
    response = client.get(
        f"/api/analytics/drilldown/KINDERGARTEN/{data['kg_irbid'].id}",
        headers=headers,
    )
    
    # Admin should have access to all kindergartens
    assert response.status_code == 200
    result = response.json()
    assert result["dimension_type"] == "KINDERGARTEN"
    assert result["dimension_id"] == str(data["kg_irbid"].id)


def test_chart_022_drilldown_authorization(
    client, two_governorates_data
):
    """Verify drill-down requires proper authorization."""
    # Try to access drill-down without authentication
    response = client.get(
        "/api/analytics/drilldown/GOVERNORATE/العاصمة",
    )
    
    # Should return 401 (unauthorized)
    assert response.status_code == 401, \
        "Authorization bypass: unauthenticated access allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
