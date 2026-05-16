"""
Tests for messaging_tasks.dispatch_scheduled_messages_now().

All tests call the core function directly with the test DB session —
no Celery worker or Redis instance is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import models
from messaging_tasks import dispatch_scheduled_messages_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    test_db,
    sender_id: int,
    recipient_id: int,
    queue_status: models.MessageQueueStatus,
    scheduled_at=None,
) -> models.Message:
    msg = models.Message(
        sender_id=sender_id,
        recipient_id=recipient_id,
        message_body="test body",
        queue_status=queue_status,
        scheduled_at=scheduled_at,
    )
    test_db.add(msg)
    test_db.commit()
    test_db.refresh(msg)
    return msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDispatchScheduledMessages:

    def test_future_message_remains_scheduled(
        self,
        test_db,
        manager_user,
        supervisor_user,
    ):
        """A message scheduled in the future must NOT be dispatched."""
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        msg = _make_message(
            test_db,
            sender_id=manager_user.id,
            recipient_id=supervisor_user.id,
            queue_status=models.MessageQueueStatus.SCHEDULED,
            scheduled_at=future,
        )

        dispatched = dispatch_scheduled_messages_now(db=test_db)

        assert dispatched == 0
        test_db.refresh(msg)
        assert msg.queue_status == models.MessageQueueStatus.SCHEDULED

    def test_due_message_becomes_sent(
        self,
        test_db,
        manager_user,
        supervisor_user,
    ):
        """A message whose scheduled_at is in the past must be transitioned to SENT."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        msg = _make_message(
            test_db,
            sender_id=manager_user.id,
            recipient_id=supervisor_user.id,
            queue_status=models.MessageQueueStatus.SCHEDULED,
            scheduled_at=past,
        )

        dispatched = dispatch_scheduled_messages_now(db=test_db)

        assert dispatched == 1
        test_db.refresh(msg)
        assert msg.queue_status == models.MessageQueueStatus.SENT

    def test_already_sent_message_is_ignored(
        self,
        test_db,
        manager_user,
        supervisor_user,
    ):
        """A message already in SENT status must never be re-dispatched."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        msg = _make_message(
            test_db,
            sender_id=manager_user.id,
            recipient_id=supervisor_user.id,
            queue_status=models.MessageQueueStatus.SENT,
            scheduled_at=past,
        )

        dispatched = dispatch_scheduled_messages_now(db=test_db)

        assert dispatched == 0
        test_db.refresh(msg)
        assert msg.queue_status == models.MessageQueueStatus.SENT

    def test_task_idempotent_on_double_run(
        self,
        test_db,
        manager_user,
        supervisor_user,
    ):
        """Running the task twice must not re-process or duplicate a dispatched message."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        msg = _make_message(
            test_db,
            sender_id=manager_user.id,
            recipient_id=supervisor_user.id,
            queue_status=models.MessageQueueStatus.SCHEDULED,
            scheduled_at=past,
        )

        first_run = dispatch_scheduled_messages_now(db=test_db)
        second_run = dispatch_scheduled_messages_now(db=test_db)

        assert first_run == 1
        assert second_run == 0  # nothing left to dispatch
        test_db.refresh(msg)
        assert msg.queue_status == models.MessageQueueStatus.SENT
