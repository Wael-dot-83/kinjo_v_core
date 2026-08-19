import pytest

from main import app
from fastapi.testclient import TestClient
from models import Kindergarten, KindergartenStatus


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
        "total_capacity", "current_child_count",
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
