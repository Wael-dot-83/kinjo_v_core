import models


def test_unread_count_and_soft_delete(
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
        "subject": "Delete test",
        "message_body": "Delete this message",
        "message_type": "direct"
    }
    response = client.post("/comm/messages", json=msg_data, headers=headers_manager)
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.get("/comm/messages/unread/count", headers=headers_parent)
    assert response.status_code == 200
    assert response.json()["unread_count"] == 1

    response = client.delete(f"/comm/messages/{msg_id}", headers=headers_parent)
    assert response.status_code == 200

    response = client.get("/comm/messages", headers=headers_parent)
    payload = response.json()
    messages = payload["items"] if "items" in payload else payload
    assert all(m["id"] != msg_id for m in messages)

    response = client.get("/comm/messages/unread/count", headers=headers_parent)
    assert response.status_code == 200
    assert response.json()["unread_count"] == 0


def test_reply_and_thread_listing(
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
        "subject": "Reply test",
        "message_body": "Please reply",
        "message_type": "direct"
    }
    response = client.post("/comm/messages", json=msg_data, headers=headers_manager)
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.post(
        f"/comm/messages/{msg_id}/replies",
        json={"message_body": "Replying now"},
        headers=headers_parent
    )
    assert response.status_code == 200
    reply_id = response.json()["id"]
    assert response.json()["reply_to_id"] == msg_id

    response = client.get(f"/comm/messages/{msg_id}/replies", headers=headers_parent)
    assert response.status_code == 200
    thread = response.json()
    assert thread["root"]["id"] == msg_id
    assert any(r["id"] == reply_id for r in thread["replies"])


def test_announcement_reply_creates_direct(
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
            "subject": "Announcement with reply",
            "message_body": "You can reply to this announcement",
            "message_type": "announcement",
            "audience": {"roles": ["PARENT"], "users": []},
            "allow_replies": True
        },
        headers=headers_manager
    )
    assert response.status_code == 201
    announcement_id = response.json()["id"]

    response = client.post(
        f"/comm/messages/{announcement_id}/replies",
        json={"message_body": "Replying to the announcement"},
        headers=headers_parent
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_type"] == "DIRECT"
    assert payload["reply_to_id"] == announcement_id
    assert payload["recipient_id"] == manager_user.id


def test_filtering_and_search(
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

    response = client.post(
        "/comm/messages",
        json={
            "recipient_id": parent_user.id,
            "subject": "Alpha note",
            "message_body": "First message",
            "message_type": "direct"
        },
        headers=headers_manager
    )
    assert response.status_code == 201

    response = client.post(
        "/comm/messages",
        json={
            "subject": "Beta broadcast",
            "message_body": "Broadcast message",
            "message_type": "announcement",
            "audience": {"roles": ["PARENT"], "users": []}
        },
        headers=headers_manager
    )
    assert response.status_code == 201

    response = client.get("/comm/messages?thread_type=direct&search=Alpha", headers=headers_parent)
    assert response.status_code == 200
    payload = response.json()
    items = payload["items"]
    assert all(m["thread_type"] == "DIRECT" for m in items)
    assert any("Alpha" in (m["subject"] or "") for m in items)

    response = client.get("/comm/messages?thread_type=announcement", headers=headers_parent)
    assert response.status_code == 200
    payload = response.json()
    items = payload["items"]
    assert all(m["thread_type"] == "ANNOUNCEMENT" for m in items)
