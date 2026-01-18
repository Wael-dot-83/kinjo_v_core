import pytest
import models
from datetime import date, timedelta

def test_communication_suite(client, test_db, manager_token, parent_token, manager_user, parent_user, sample_kindergarten):
    # Setup: Assign parent to kindergarten to enable communication scoping
    parent_user = test_db.query(models.User).filter(models.User.id == parent_user.id).first()
    parent_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()
    
    # ---------------------------------------------------------
    # Test 1: Direct Message sending (Manager -> Parent)
    # ---------------------------------------------------------
    msg_data = {
        "recipient_id": parent_user.id,
        "subject": "Welcome",
        "message_body": "This is a direct message test",
        "thread_type": "DIRECT"
    }
    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    response = client.post("/comm/messages", json=msg_data, headers=headers_manager)
    assert response.status_code == 201, f"Failed to send message: {response.text}"
    msg_id = response.json()["id"]
    
    # ---------------------------------------------------------
    # Test 2: Parent checking inbox (should see the message)
    # ---------------------------------------------------------
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response = client.get("/comm/messages", headers=headers_parent)
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) >= 1
    # Verify the specific message is found
    found = False
    for m in messages:
        if m["id"] == msg_id:
            found = True
            break
    assert found, "Direct message not found in parent inbox"

    # ---------------------------------------------------------
    # Test 3: Manager creates a Survey
    # ---------------------------------------------------------
    survey_data = {
        "title": "Feedback Survey",
        "description": "Please rate us",
        "nps_question_enabled": True,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=7))
    }
    
    response = client.post("/comm/surveys", json=survey_data, headers=headers_manager)
    assert response.status_code == 201
    survey_id = response.json()["id"]

    # ---------------------------------------------------------
    # Test 4: Parent views Survey
    # ---------------------------------------------------------
    response = client.get("/comm/surveys", headers=headers_parent)
    assert response.status_code == 200
    surveys = response.json()
    assert any(s["id"] == survey_id for s in surveys)

    # ---------------------------------------------------------
    # Test 5: Parent Submits Survey Response
    # ---------------------------------------------------------
    resp_data = {
        "nps_score": 9,
        "feedback_text": "Great school!"
    }
    response = client.post(f"/comm/surveys/{survey_id}/submit", json=resp_data, headers=headers_parent)
    assert response.status_code == 201
    assert response.json()["nps_score"] == 9
    
    # ---------------------------------------------------------
    # Test 6: Prevent Double Submission
    # ---------------------------------------------------------
    response = client.post(f"/comm/surveys/{survey_id}/submit", json=resp_data, headers=headers_parent)
    assert response.status_code == 400
    assert "already responded" in response.json()["detail"]

