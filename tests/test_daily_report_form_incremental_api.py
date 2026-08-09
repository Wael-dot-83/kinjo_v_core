"""Tests for structured form conversion and incremental API alignment.

Verifies that single (/api/daily-reports/create) and batch (/api/daily-reports/batch)
incremental APIs accept and persist all structured daily report fields:
- Meal controls: breakfast, snack, milk, lunch
- Sleep/Nap/Rest controls: nap_start, nap_end, nap_duration_minutes
- Toilet/Potty controls: bathroom_count, diaper_wet, diaper_soiled
- Mood & Health controls: mood, health_notes
- Arrival & Dismissal controls: arrival_time, leave_time
"""
from datetime import date, timedelta
import pytest
import models
from conftest import bearer_headers


def _ensure_child_and_assignment(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    sample_child.mother_first_name = sample_child.mother_first_name or "أمي"
    sample_child.mother_last_name = sample_child.mother_last_name or "اختبار"
    sample_child.mother_nationality = sample_child.mother_nationality or "Jordanian"
    sample_child.father_name = sample_child.father_name or "أبي"
    if not sample_child.date_of_birth:
        sample_child.date_of_birth = date.today() - timedelta(days=365 * 3)
    test_db.commit()

    enrollment = test_db.query(models.EnrollmentApplication).filter_by(child_id=sample_child.id).first()
    if not enrollment:
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()
    else:
        enrollment.status = models.EnrollmentStatus.ACTIVE
        test_db.commit()

    assignment = test_db.query(models.SupervisorAssignment).filter_by(
        supervisor_id=supervisor_user.id,
        class_id=sample_class.id
    ).first()
    if not assignment:
        assignment = models.SupervisorAssignment(
            supervisor_id=supervisor_user.id,
            class_id=sample_class.id,
            start_date=date.today() - timedelta(days=10),
            end_date=None,
            is_primary=True,
        )
        test_db.add(assignment)
        test_db.commit()


def test_single_create_persists_all_structured_fields(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _ensure_child_and_assignment(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    today_str = date.today().isoformat()
    # Clean any report for today to prevent 409
    test_db.query(models.DailyReport).filter_by(child_id=sample_child.id, date=date.today()).delete()
    test_db.commit()

    payload = {
        "child_id": sample_child.id,
        "date": today_str,
        "arrival_time": "08:15",
        "leave_time": "13:30",
        "mood": "happy",
        "health_notes": "Energetic and well hydrated",
        "breakfast": True,
        "lunch": True,
        "snack": False,
        "milk": True,
        "breakfast_time": "08:30",
        "snack_time": "10:30",
        "milk_time": "09:30",
        "lunch_time": "12:30",
        "nap_start": "11:30",
        "nap_end": "12:30",
        "nap_duration_minutes": 60,
        "bathroom_count": 2,
        "diaper_wet": True,
        "diaper_soiled": False,
        "activities": "Painting, Singing",
        "notes": "Had a wonderful productive day"
    }

    res = client.post(
        "/api/daily-reports/create",
        json=payload,
        headers=bearer_headers(supervisor_token)
    )
    assert res.status_code == 201, res.text
    report_id = res.json()["id"]

    # Verify directly from DB
    report = test_db.query(models.DailyReport).filter_by(id=report_id).first()
    assert report is not None
    assert report.arrival_time == "08:15"
    assert report.leave_time == "13:30"
    assert report.mood == "happy"
    assert report.health_notes == "Energetic and well hydrated"
    assert report.breakfast is True
    assert report.lunch is True
    assert report.snack is False
    assert report.milk is True
    assert report.breakfast_time == "08:30"
    assert report.snack_time == "10:30"
    assert report.milk_time == "09:30"
    assert report.lunch_time == "12:30"
    assert report.nap_start == "11:30"
    assert report.nap_end == "12:30"
    assert report.nap_duration_minutes == 60
    assert report.bathroom_count == 2
    assert report.diaper_wet is True
    assert report.diaper_soiled is False

    # Verify via GET endpoint
    get_res = client.get(
        f"/api/daily-reports/{report_id}",
        headers=bearer_headers(supervisor_token)
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["mood"] == "happy"
    assert data["health_notes"] == "Energetic and well hydrated"
    assert data["breakfast"] is True
    assert data["milk"] is True
    assert data["breakfast_time"] == "08:30"
    assert data["snack_time"] == "10:30"
    assert data["milk_time"] == "09:30"
    assert data["lunch_time"] == "12:30"
    assert data["nap_duration_minutes"] == 60
    assert data["bathroom_count"] == 2
    assert data["diaper_wet"] is True
    assert data["diaper_soiled"] is False


def test_batch_create_persists_all_structured_fields(client, supervisor_token, test_db, supervisor_user, sample_kindergarten, sample_class, sample_child):
    _ensure_child_and_assignment(test_db, supervisor_user, sample_kindergarten, sample_class, sample_child)

    today_str = date.today().isoformat()
    # Delete any existing report for today
    test_db.query(models.DailyReport).filter_by(child_id=sample_child.id, date=date.today()).delete()
    test_db.commit()

    payload = {
        "date": today_str,
        "arrival_time": "08:00",
        "leave_time": "13:00",
        "breakfast": True,
        "lunch": True,
        "snack": True,
        "breakfast_time": "08:30",
        "lunch_time": "12:30",
        "children": [
            {
                "child_id": sample_child.id,
                "arrival_time": "08:30",
                "leave_time": "14:00",
                "mood": "tired",
                "health_notes": "Slight cough",
                "breakfast": True,
                "lunch": False,
                "milk": True,
                "snack": True,
                "breakfast_time": "08:45",
                "milk_time": "09:45",
                "nap_start": "12:00",
                "nap_end": "13:00",
                "nap_duration_minutes": 60,
                "bathroom_count": 3,
                "diaper_wet": True,
                "diaper_soiled": True,
                "activities": "Story time",
                "notes": "Rested during quiet hour"
            }
        ]
    }

    res = client.post(
        "/api/daily-reports/batch",
        json=payload,
        headers=bearer_headers(supervisor_token)
    )
    assert res.status_code == 207, res.text
    body = res.json()
    assert body["created"] == 1, f"Batch response: {body}"

    report_id = body["results"][0]["report_id"]
    report = test_db.query(models.DailyReport).filter_by(id=report_id).first()
    assert report.arrival_time == "08:30"
    assert report.leave_time == "14:00"
    assert report.mood == "tired"
    assert report.health_notes == "Slight cough"
    assert report.lunch is False
    assert report.milk is True
    assert report.breakfast_time == "08:45"
    assert report.milk_time == "09:45"
    assert report.lunch_time == "12:30"
    assert report.nap_duration_minutes == 60
    assert report.bathroom_count == 3
    assert report.diaper_wet is True
    assert report.diaper_soiled is True
