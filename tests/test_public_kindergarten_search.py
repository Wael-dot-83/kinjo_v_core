from datetime import date, timedelta

import pytest

from main import app
from fastapi.testclient import TestClient
from models import Kindergarten, KindergartenStatus


def test_public_search_cannot_override_active_registry_filter(client, test_db):
    active = Kindergarten(name_ar="Active Registry Nursery", name_en="Active Registry Nursery", governorate="Amman", district="Amman", area="Jubeiha", address_line="Registry Street", contact_phone="+962790000001", status=KindergartenStatus.ACTIVE)
    frozen = Kindergarten(name_ar="Frozen Nursery", name_en="Frozen Nursery", governorate="Amman", district="Amman", area="Jubeiha", address_line="Registry Street", contact_phone="+962790000002", status=KindergartenStatus.FROZEN)
    expired = Kindergarten(name_ar="Expired Nursery", name_en="Expired Nursery", governorate="Amman", district="Amman", area="Jubeiha", address_line="Registry Street", contact_phone="+962790000003", status=KindergartenStatus.ACTIVE, license_status="expired", license_valid_until=date.today() - timedelta(days=1))
    test_db.add_all([active, frozen, expired])
    test_db.commit()

    response = client.get("/api/public/kindergartens/search?status=frozen&limit=100")
    assert response.status_code == 200
    names = {item["name_en"] for item in response.json()["data"]["items"]}
    assert "Active Registry Nursery" in names
    assert "Frozen Nursery" not in names
    assert "Expired Nursery" not in names


def test_public_kindergarten_details_are_safe_and_public(client, test_db):
    kg = Kindergarten(name_ar="Public Details Nursery", name_en="Public Details Nursery", governorate="Amman", district="Amman", area="Jubeiha", address_line="Details Street", contact_phone="+962790000004", contact_email="details@example.jo", status=KindergartenStatus.ACTIVE, manager_name="Private Manager", license_number="PRIVATE-LICENSE-1", operating_hours_start="08:00", operating_hours_end="16:00", working_days="Sunday-Thursday", latitude=31.99, longitude=35.90)
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    response = client.get(f"/api/public/kindergartens/{kg.id}")
    assert response.status_code == 200
    item = response.json()["data"]
    assert item["license_status"] == "active"
    assert item["working_hours_start"] == "08:00"
    assert item["latitude"] == 31.99
    assert "manager_name" not in item
    assert "license_number" not in item


def test_public_search_returns_200_and_items(client, test_db):
    kg = Kindergarten(
        name_ar="حضانة الأمل",
        name_en="Hope Kindergarten",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@hope.jo",
        status=KindergartenStatus.ACTIVE,
        total_capacity=50,
        current_child_count=30,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    response = client.get("/api/public/kindergartens/search?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]["items"]) >= 1


def test_public_search_projection_excludes_sensitive_fields(client, test_db):
    kg = Kindergarten(
        name_ar="حضانة الأمل",
        name_en="Hope Kindergarten",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@hope.jo",
        status=KindergartenStatus.ACTIVE,
        total_capacity=50,
        current_child_count=30,
        manager_name="Manager Name",
        license_number="LIC-001",
        monthly_fees=150.0,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    response = client.get("/api/public/kindergartens/search?limit=10")
    assert response.status_code == 200
    data = response.json()
    item = data["data"]["items"][0]

    allowed = {
        "id", "name_ar", "name_en", "governorate", "district", "area",
        "address_line", "contact_phone", "contact_email", "status",
        "total_capacity", "current_child_count", "latitude", "longitude",
    }
    assert set(item.keys()).issubset(allowed)
    assert "manager_name" not in item
    assert "license_number" not in item
    assert "monthly_fees" not in item
    assert "administrative_notes" not in item


def test_public_search_filters_by_governorate(client, test_db):
    kg = Kindergarten(
        name_ar="حضانة عمان",
        name_en="Amman KG",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@amman.jo",
        status=KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    response = client.get("/api/public/kindergartens/search?governorate=Amman&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    for item in data["data"]["items"]:
        assert item["governorate"] == "Amman"


def test_public_search_excludes_deleted(client, test_db):
    kg = Kindergarten(
        name_ar="حضانة محذوفة",
        name_en="Deleted KG",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@deleted.jo",
        status=KindergartenStatus.DELETED,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    response = client.get("/api/public/kindergartens/search?limit=10")
    assert response.status_code == 200
    data = response.json()
    names = [item["name_ar"] for item in data["data"]["items"]]
    assert "حضانة محذوفة" not in names
