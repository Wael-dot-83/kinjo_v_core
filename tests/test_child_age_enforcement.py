from datetime import date, timedelta

import pytest

import models
from dependencies import get_current_user
from main import app


def _make_child(test_db, parent_profile, dob):
    child = models.Child(
        parent_id=parent_profile.id,
        first_name="Valid",
        last_name="Child",
        gender=models.Gender.MALE,
        date_of_birth=dob,
        father_name="Father",
        mother_first_name="Mother",
        mother_last_name="Last",
        mother_nationality="Jordanian",
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)
    return child


def test_enrollment_rejects_out_of_range_dob(client, parent_user, sample_kindergarten):
    app.dependency_overrides[get_current_user] = lambda: parent_user

    too_young = (date.today() - timedelta(days=10)).isoformat()
    payload = {
        "first_name": "Baby",
        "last_name": "Al-Rashid",  # Match parent's last name
        "gender": "male",
        "date_of_birth": too_young,
        "father_name": "Father",
        "mother_first_name": "Mother",
        "mother_last_name": "Last",
        "mother_nationality": "Jordanian",
        "mother_national_id": "1234567890",
        "national_id": "9876543210",  # Add child's national ID for Jordanian child
        "kindergarten_id": sample_kindergarten.id,
    }

    response = client.post("/api/enrollment/apply", json=payload)
    assert response.status_code == 400

    too_old = (date.today() - timedelta(days=365 * 6)).isoformat()
    payload["date_of_birth"] = too_old
    response = client.post("/api/enrollment/apply", json=payload)
    assert response.status_code == 400

    valid = (date.today() - timedelta(days=365 * 3)).isoformat()
    payload["date_of_birth"] = valid
    response = client.post("/api/enrollment/apply", json=payload)
    assert response.status_code == 201

    app.dependency_overrides.clear()


def test_update_child_rejects_out_of_range_dob(client, test_db, parent_user):
    app.dependency_overrides[get_current_user] = lambda: parent_user

    child = _make_child(
        test_db,
        parent_user.parent_profile,
        date.today() - timedelta(days=365 * 3),
    )

    payload = {"date_of_birth": (date.today() - timedelta(days=365 * 6)).isoformat()}
    response = client.put(f"/api/children/{child.id}", json=payload)
    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_children_list_filters_out_of_range(client, test_db, admin_user, sample_kindergarten):
    app.dependency_overrides[get_current_user] = lambda: admin_user

    parent = models.ParentProfile(
        user_id=admin_user.id,
        first_name="P",
        last_name="T",
        phone_number="+962700000000",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        home_governorate="Amman",
        home_city="Amman",
        home_area="Area",
        home_address_line="Address",
        correspondence_preference=True,
    )
    test_db.add(parent)
    test_db.commit()
    test_db.refresh(parent)

    valid_child = _make_child(
        test_db, parent, date.today() - timedelta(days=365 * 3)
    )

    # Insert out-of-range child by bypassing policy guards
    test_db.info["skip_child_age_policy"] = True
    out_of_range_child = _make_child(
        test_db, parent, date.today() - timedelta(days=365 * 6)
    )
    enrollment_valid = models.EnrollmentApplication(
        child_id=valid_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    enrollment_invalid = models.EnrollmentApplication(
        child_id=out_of_range_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add_all([enrollment_valid, enrollment_invalid])
    test_db.commit()
    test_db.info.pop("skip_child_age_policy", None)

    response = client.get("/api/children")
    assert response.status_code == 200
    data = response.json()
    ids = {child["id"] for child in data.get("children", [])}
    assert valid_child.id in ids
    assert out_of_range_child.id not in ids

    app.dependency_overrides.clear()
