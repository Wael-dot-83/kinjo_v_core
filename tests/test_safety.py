import pytest
from datetime import datetime, timedelta, date
import models

def test_incident_reporting(client, test_db, manager_token, manager_user, sample_kindergarten, parent_user):
    """Test incident reporting workflow"""
    
    # Setup: Ensure manager linked to KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    # Setup: Create Child
    dob = date.today() - timedelta(days=365*4)
    child = models.Child(
        parent_id=parent_user.id,
        first_name="Safety",
        last_name="Test",
        date_of_birth=dob,
        gender=models.Gender.FEMALE,
        father_name="Safety Father",
        mother_first_name="Safety",
        mother_last_name="Mother",
        mother_nationality="Jordanian"
    )
    test_db.add(child)
    test_db.flush()

    # Setup: Enroll Child (Active)
    enrollment = models.EnrollmentApplication(
        kindergarten_id=sample_kindergarten.id,
        child_id=child.id,
        status=models.EnrollmentStatus.ACTIVE,
        submitted_at=datetime.now()
    )
    test_db.add(enrollment)
    test_db.commit()

    headers = {"Authorization": f"Bearer {manager_token}"}

    # 1. Report Incident
    incident_data = {
        "child_id": child.id,
        "type": "INJURY",
        "severity_level": "MEDIUM",
        "description": "Child fell on the playground and scraped knee.",
        "occurred_at": datetime.now().isoformat(),
        "followup_required_flag": True
    }

    response = client.post("/api/incidents", json=incident_data, headers=headers)
    assert response.status_code == 201, f"Report failed: {response.text}"
    incident_id = response.json()["id"]

    # 2. List Incidents
    response = client.get(f"/api/incidents?child_id={child.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["type"] == "INJURY"

    # 3. Add Health Alert
    alert_data = {
        "alert_type": "Allergy",
        "description": "Peanuts",
        "severity": "High"
    }
    response = client.post(f"/api/children/{child.id}/health-alerts", json=alert_data, headers=headers)
    assert response.status_code == 201
    
    # 4. List Health Alerts
    response = client.get(f"/api/children/{child.id}/health-alerts", headers=headers)
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) >= 1
    assert alerts[0]["alert_type"] == "Allergy"
