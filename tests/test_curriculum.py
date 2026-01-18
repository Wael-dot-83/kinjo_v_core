import pytest
from datetime import datetime, timedelta, date
import models

def test_curriculum_workflow(client, test_db, manager_token, manager_user, sample_kindergarten, parent_user):
    """Test observation and portfolio workflow"""
    
    # Setup: Ensure manager linked to KG
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    # Setup: Create Child
    dob = date.today() - timedelta(days=365*4)
    child = models.Child(
        parent_id=parent_user.id,
        first_name="Smart",
        last_name="Learner",
        date_of_birth=dob,
        gender=models.Gender.FEMALE,
        father_name="Smart Father",
        mother_first_name="Smart",
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

    # 1. Record Observation
    obs_data = {
        "child_id": child.id,
        "domain": "COGNITIVE",
        "observation_text": "Child can count to 20 independently.",
        "mastery_level": "ON_TRACK",
        "observed_at": datetime.now().isoformat()
    }

    response = client.post("/api/observations", json=obs_data, headers=headers)
    assert response.status_code == 201, f"Observation failed: {response.text}"
    
    # 2. List Observations
    response = client.get(f"/api/children/{child.id}/observations", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["domain"] == "COGNITIVE"

    # 3. Create Portfolio Entry
    portfolio_data = {
        "child_id": child.id,
        "title": "Spring Painting",
        "description": "Watercolor painting of flowers.",
        "status": "PUBLISHED"
    }
    
    response = client.post("/api/portfolios", json=portfolio_data, headers=headers)
    assert response.status_code == 201
    
    # 4. List Portfolio (as Manager)
    response = client.get(f"/api/children/{child.id}/portfolio", headers=headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    assert items[0]["title"] == "Spring Painting"
