"""Tests for canonical Jordan location data source and API endpoints."""
import pytest
from fastapi.testclient import TestClient

from services.jordan_locations import (
    get_all_governorates,
    get_governorate_by_key,
    get_governorate_by_name,
    get_areas_for_governorate,
    get_area_by_key,
    normalize_governorate,
    normalize_area,
    is_valid_governorate,
    is_valid_area_for_governorate,
    validate_governorate,
    validate_area_for_governorate,
    validate_governorate_area_pair,
)
from main import app

client = TestClient(app)


class TestCanonicalData:
    def test_twelve_governorates(self):
        govs = get_all_governorates()
        assert len(govs) == 12

    def test_every_governorate_has_key_ar_en(self):
        for g in get_all_governorates():
            assert "key" in g
            assert "name_ar" in g
            assert "name_en" in g
            assert isinstance(g["key"], str)
            assert isinstance(g["name_ar"], str)
            assert isinstance(g["name_en"], str)

    def test_every_governorate_has_areas(self):
        for g in get_all_governorates():
            areas = get_areas_for_governorate(g["key"])
            assert len(areas) > 0
            for a in areas:
                assert "key" in a
                assert "name_ar" in a

    def test_lookup_by_key(self):
        g = get_governorate_by_key("amman")
        assert g is not None
        assert g["name_ar"] == "عمان"

    def test_lookup_by_key_case_insensitive(self):
        g = get_governorate_by_key("AMMAN")
        assert g is not None
        assert g["name_ar"] == "عمان"

    def test_lookup_by_name_ar(self):
        g = get_governorate_by_name("عمان")
        assert g is not None
        assert g["key"] == "amman"

    def test_lookup_by_name_en(self):
        g = get_governorate_by_name("Amman", locale="en")
        assert g is not None
        assert g["key"] == "amman"

    def test_area_lookup(self):
        a = get_area_by_key("amman", "jubeiha")
        assert a is not None
        assert a["name_ar"] == "الجبيهة"

    def test_area_lookup_case_insensitive(self):
        a = get_area_by_key("AMMAN", "JUBEIHA")
        assert a is not None
        assert a["name_ar"] == "الجبيهة"


class TestNormalization:
    def test_normalize_governorate_english(self):
        assert normalize_governorate("Amman") == "عمان"

    def test_normalize_governorate_alias(self):
        assert normalize_governorate("العاصمة") == "عمان"

    def test_normalize_governorate_already_canonical(self):
        assert normalize_governorate("عمان") == "عمان"

    def test_normalize_governorate_case_insensitive(self):
        assert normalize_governorate("AMMAN") == "عمان"

    def test_normalize_governorate_none(self):
        assert normalize_governorate(None) is None

    def test_normalize_governorate_unknown(self):
        assert normalize_governorate("UnknownGov") == "UnknownGov"

    def test_normalize_area(self):
        assert normalize_area("amman", "Jubeiha") == "الجبيهة"

    def test_normalize_area_already_canonical(self):
        assert normalize_area("amman", "الجبيهة") == "الجبيهة"

    def test_normalize_area_none(self):
        assert normalize_area("amman", None) is None

    def test_normalize_area_unknown(self):
        assert normalize_area("amman", "UnknownArea") == "UnknownArea"


class TestValidation:
    def test_is_valid_governorate_true(self):
        assert is_valid_governorate("Amman") is True

    def test_is_valid_governorate_false(self):
        assert is_valid_governorate("NotAGov") is False

    def test_is_valid_area_for_governorate_true(self):
        assert is_valid_area_for_governorate("amman", "Jubeiha") is True

    def test_is_valid_area_for_governorate_false(self):
        assert is_valid_area_for_governorate("amman", "NotAnArea") is False

    def test_validate_governorate_success(self):
        assert validate_governorate("Amman") == "عمان"

    def test_validate_governorate_failure(self):
        with pytest.raises(ValueError):
            validate_governorate("NotAGov")

    def test_validate_area_for_governorate_success(self):
        assert validate_area_for_governorate("amman", "Jubeiha") == "الجبيهة"

    def test_validate_area_for_governorate_failure(self):
        with pytest.raises(ValueError):
            validate_area_for_governorate("amman", "NotAnArea")

    def test_validate_area_empty(self):
        assert validate_area_for_governorate("amman", "") == ""

    def test_validate_area_none(self):
        assert validate_area_for_governorate("amman", None) == ""

    def test_validate_governorate_area_pair_success(self):
        gov, area = validate_governorate_area_pair("Amman", "Jubeiha")
        assert gov == "عمان"
        assert area == "الجبيهة"

    def test_validate_governorate_area_pair_invalid_area(self):
        with pytest.raises(ValueError):
            validate_governorate_area_pair("Amman", "NotAnArea")

    def test_validate_governorate_area_pair_invalid_governorate(self):
        with pytest.raises(ValueError):
            validate_governorate_area_pair("NotAGov", "Jubeiha")


class TestApiEndpoints:
    def test_jordan_locations(self):
        response = client.get("/api/locations/jordan")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 12

    def test_jordan_governorates(self):
        response = client.get("/api/locations/jordan/governorates")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "governorates" in data["data"]
        assert len(data["data"]["governorates"]) == 12
        assert all("key" in g for g in data["data"]["governorates"])
        assert all("name_ar" in g for g in data["data"]["governorates"])

    def test_jordan_areas_for_governorate(self):
        response = client.get("/api/locations/jordan/governorates/amman/areas")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "areas" in data["data"]
        assert len(data["data"]["areas"]) > 0
        assert data["data"]["governorate"]["key"] == "amman"

    def test_jordan_areas_not_found(self):
        response = client.get("/api/locations/jordan/governorates/not_a_gov/areas")
        assert response.status_code == 404

    def test_jordan_validate_governorate(self):
        response = client.get("/api/locations/jordan/validate?governorate=Amman")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["governorate"] == "عمان"

    def test_jordan_validate_invalid_governorate(self):
        response = client.get("/api/locations/jordan/validate?governorate=NotAGov")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "governorate_error" in data

    def test_jordan_validate_pair(self):
        response = client.get("/api/locations/jordan/validate?governorate=Amman&area=Jubeiha")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["governorate"] == "عمان"
        assert data["area"] == "الجبيهة"

    def test_jordan_validate_pair_invalid(self):
        response = client.get("/api/locations/jordan/validate?governorate=Amman&area=NotAnArea")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "area_error" in data

    def test_reference_governorates(self):
        response = client.get("/api/reference/governorates")
        assert response.status_code == 200
        data = response.json()
        assert "governorates" in data
        assert len(data["governorates"]) == 12

    def test_governorates_areas(self):
        response = client.get("/api/governorates/amman/districts")
        assert response.status_code == 200
        data = response.json()
        assert "districts" in data
        assert len(data["districts"]) > 0
