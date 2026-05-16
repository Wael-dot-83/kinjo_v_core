import models


def test_message_read_tracking_and_detail(
    client,
    test_db,
    manager_user,
    parent_user,
    manager_token,
    parent_token,
    sample_kindergarten,
    parent_enrollment
):
    parent_user = test_db.query(models.User).filter(models.User.id == parent_user.id).first()
    parent_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    headers_parent = {"Authorization": f"Bearer {parent_token}"}

    msg_data = {
        "recipient_id": parent_user.id,
        "subject": "Read tracking",
        "message_body": "Please read this message",
        "message_type": "direct"
    }
    response = client.post("/comm/messages", json=msg_data, headers=headers_manager)
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.get("/comm/messages", headers=headers_parent)
    assert response.status_code == 200
    payload = response.json()
    messages = payload["items"] if "items" in payload else payload
    target = next((m for m in messages if m["id"] == msg_id), None)
    assert target is not None
    assert target["is_read"] is False

    response = client.post(f"/comm/messages/{msg_id}/read", headers=headers_parent)
    assert response.status_code == 200
    assert response.json()["read_at"] is not None

    response = client.get(f"/comm/messages/{msg_id}", headers=headers_parent)
    assert response.status_code == 200
    assert response.json()["is_read"] is True

    sent_log = test_db.query(models.AuditLog).filter(
        models.AuditLog.action == "MESSAGE_SENT",
        models.AuditLog.entity_id == msg_id
    ).first()
    assert sent_log is not None

    read_log = test_db.query(models.AuditLog).filter(
        models.AuditLog.action == "MESSAGE_READ",
        models.AuditLog.entity_id == msg_id
    ).first()
    assert read_log is not None


def test_parent_direct_without_recipient_id(
    client,
    test_db,
    manager_user,
    parent_user,
    parent_token,
    sample_kindergarten,
    parent_enrollment
):
    headers_parent = {"Authorization": f"Bearer {parent_token}"}

    response = client.post(
        "/comm/messages",
        json={
            "subject": "Need info",
            "message_body": "Hello manager",
            "message_type": "direct",
            "kindergarten_id": sample_kindergarten.id
        },
        headers=headers_parent
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["recipient_id"] == manager_user.id


def test_announcement_read_updates_recipient(
    client,
    test_db,
    manager_user,
    parent_user,
    manager_token,
    parent_token,
    sample_kindergarten,
    parent_enrollment
):
    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    headers_parent = {"Authorization": f"Bearer {parent_token}"}

    response = client.post(
        "/comm/messages",
        json={
            "subject": "Announcement read",
            "message_body": "Please read this announcement",
            "message_type": "announcement",
            "audience": {"roles": ["PARENT"], "users": []},
            "allow_replies": False
        },
        headers=headers_manager
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    response = client.post(f"/comm/messages/{message_id}/read", headers=headers_parent)
    assert response.status_code == 200

    recipient_state = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == message_id,
        models.MessageRecipient.recipient_user_id == parent_user.id
    ).first()
    assert recipient_state is not None
    assert recipient_state.read_at is not None
