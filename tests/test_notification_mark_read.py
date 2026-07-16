"""Marking a single notification read must work — and must not mark someone else's.

templates/user/notifications.html has always rendered a per-notification "mark read"
control, but only `/notifications/read-all` existed. The request 404'd, and the caller
never checked `response.ok`: it reloaded the list and the notification stayed unread
with no error shown. The user clicks, nothing happens, nothing is said.

The id comes from the URL, so the ownership filter is the whole security story here.
"""
import models


def _notify(test_db, user_id):
    n = models.Notification(
        user_id=user_id,
        channel=list(models.NotificationChannel)[0],
        status=models.NotificationStatus.PENDING,
    )
    test_db.add(n)
    test_db.commit()
    test_db.refresh(n)
    return n


def test_marks_own_notification_read(client, parent_token, parent_user, test_db):
    n = _notify(test_db, parent_user.id)
    resp = client.post(
        f"/api/notifications/{n.id}/read",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:200]}"

    test_db.expire_all()
    assert test_db.get(models.Notification, n.id).status == models.NotificationStatus.SENT, (
        "endpoint answered 200 but the notification is still unread"
    )


def test_cannot_mark_another_users_notification_read(client, parent_token, admin_user, test_db):
    """IDOR: the id is a guessable integer straight off the URL."""
    victim = _notify(test_db, admin_user.id)

    resp = client.post(
        f"/api/notifications/{victim.id}/read",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert resp.status_code == 404, (
        f"a parent marked another user's notification read ({resp.status_code}) — the "
        "ownership filter is missing from the UPDATE"
    )

    test_db.expire_all()
    assert test_db.get(models.Notification, victim.id).status == models.NotificationStatus.PENDING, (
        "the victim's notification was mutated even though the request was refused"
    )


def test_unknown_notification_is_404(client, parent_token):
    resp = client.post(
        "/api/notifications/999999/read",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert resp.status_code == 404, f"{resp.status_code}: {resp.text[:150]}"


def test_requires_authentication(client, test_db, parent_user):
    n = _notify(test_db, parent_user.id)
    client.cookies.clear()
    resp = client.post(f"/api/notifications/{n.id}/read")
    assert resp.status_code in (401, 403), (
        f"anonymous caller got {resp.status_code}"
    )
