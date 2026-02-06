import io
import models
import notification_service
from config import settings


def test_archive_and_bulk_actions(
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
            "subject": "Archive me",
            "message_body": "Archive test",
            "message_type": "direct"
        },
        headers=headers_manager
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.post(f"/comm/messages/{msg_id}/archive", headers=headers_parent)
    assert response.status_code == 200

    response = client.get("/comm/messages?archived_only=true", headers=headers_parent)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(m["id"] == msg_id for m in items)

    response = client.post(
        "/comm/messages/bulk",
        json={"message_ids": [msg_id], "action": "unarchive"},
        headers=headers_parent
    )
    assert response.status_code == 200

    response = client.get("/comm/messages?archived_only=true", headers=headers_parent)
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(m["id"] != msg_id for m in items)


def test_attachment_upload_and_download(
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
            "subject": "Attachment",
            "message_body": "See attachment",
            "message_type": "direct"
        },
        headers=headers_manager
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    file_content = b"hello attachment"
    response = client.post(
        f"/comm/messages/{msg_id}/attachments",
        files={"file": ("hello.txt", io.BytesIO(file_content), "text/plain")},
        headers=headers_manager
    )
    assert response.status_code == 200
    attachment_id = response.json()["id"]

    response = client.get(f"/comm/messages/{msg_id}/attachments", headers=headers_parent)
    assert response.status_code == 200
    assert any(att["id"] == attachment_id for att in response.json())

    response = client.get(f"/comm/messages/attachments/{attachment_id}", headers=headers_parent)
    assert response.status_code == 200


def test_device_token_register_and_remove(
    client,
    test_db,
    parent_user,
    parent_token
):
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response = client.post(
        "/comm/notifications/devices",
        json={"token": "device-token-1", "platform": "WEB"},
        headers=headers_parent
    )
    assert response.status_code == 200
    assert response.json()["token"] == "device-token-1"

    response = client.delete(
        "/comm/notifications/devices/device-token-1",
        headers=headers_parent
    )
    assert response.status_code == 200


def test_attachment_size_limit(
    client,
    test_db,
    manager_user,
    parent_user,
    manager_token,
    parent_token,
    sample_kindergarten,
    monkeypatch,
    parent_enrollment
):
    parent_user = test_db.query(models.User).filter(models.User.id == parent_user.id).first()
    parent_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    monkeypatch.setattr(settings, "MAX_ATTACHMENT_SIZE_MB", 0)

    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    headers_parent = {"Authorization": f"Bearer {parent_token}"}

    response = client.post(
        "/comm/messages",
        json={
            "recipient_id": parent_user.id,
            "subject": "Attachment limit",
            "message_body": "Limit test",
            "message_type": "direct"
        },
        headers=headers_manager
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.post(
        f"/comm/messages/{msg_id}/attachments",
        files={"file": ("too-big.txt", io.BytesIO(b"1"), "text/plain")},
        headers=headers_manager
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_message_notifications_queueing(
    test_db,
    manager_user,
    parent_user,
    sample_kindergarten,
    monkeypatch
):
    parent_user = test_db.query(models.User).filter(models.User.id == parent_user.id).first()
    parent_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    manager_user = test_db.query(models.User).filter(models.User.id == manager_user.id).first()
    manager_user.kindergarten_id = sample_kindergarten.id
    test_db.commit()

    msg = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=manager_user.id,
        recipient_id=parent_user.id,
        kindergarten_id=sample_kindergarten.id,
        subject="Notify",
        message_body="Notification test"
    )
    test_db.add(msg)
    test_db.commit()
    test_db.refresh(msg)

    queued = {}

    def fake_queue(notifications):
        queued["count"] = len(notifications)

    monkeypatch.setattr(notification_service, "_queue_notification_tasks", fake_queue)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False)

    notification_service.create_message_notifications(test_db, msg, [parent_user])

    notifications = test_db.query(models.Notification).filter(
        models.Notification.message_id == msg.id
    ).all()
    assert len(notifications) == 1
    assert notifications[0].channel == models.NotificationChannel.EMAIL
    assert queued["count"] == 1
