"""
Notification helpers for messaging.
"""
import logging
from typing import Iterable, List

import models
from config import settings
from notification_tasks import send_email_notification, send_push_notification

logger = logging.getLogger(__name__)


def _build_notification_payload(message: models.Message) -> dict:
    subject = message.subject or "New message"
    body = message.message_body[:240] if message.message_body else "You have a new message"
    return {"subject": subject, "title": subject, "body": body}


def _queue_notification_tasks(notifications: List[models.Notification]) -> None:
    for notification in notifications:
        if notification.channel == models.NotificationChannel.EMAIL:
            send_email_notification.delay(notification.id)
        elif notification.channel == models.NotificationChannel.PUSH:
            send_push_notification.delay(notification.id)


def create_message_notifications(
    db,
    message: models.Message,
    recipients: Iterable[models.User]
) -> bool:
    if settings.TESTING:
        return False

    channels = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)

    if not channels:
        logger.warning("Notifications disabled for message %s", message.id)
        return False

    payload = _build_notification_payload(message)
    notifications: List[models.Notification] = []

    for user in recipients:
        for channel in channels:
            notifications.append(models.Notification(
                user_id=user.id,
                message_id=message.id,
                channel=channel,
                status=models.NotificationStatus.PENDING,
                payload=payload
            ))

    if not notifications:
        return False

    db.add_all(notifications)
    db.commit()

    _queue_notification_tasks(notifications)

    return True


__all__ = ["create_message_notifications"]
