"""
Celery tasks for message processing.

dispatch_scheduled_messages
  - Runs every minute via Celery Beat.
  - Promotes SCHEDULED messages whose scheduled_at <= now(UTC) to SENT.
  - Safe to call directly (e.g. in tests) by passing an existing db session.
  - Idempotent: already-SENT messages are never re-processed.
"""
import logging
from datetime import datetime, timezone

from celery_app import celery_app
from database import SessionLocal
import models

logger = logging.getLogger(__name__)


def dispatch_scheduled_messages_now(db=None) -> int:
    """
    Core dispatch logic — callable directly without Celery infrastructure.

    Returns the number of messages transitioned SCHEDULED → SENT.
    When *db* is None a fresh SessionLocal session is opened and closed here.
    When *db* is supplied the caller owns the session lifecycle.
    """
    _owns_db = db is None
    if _owns_db:
        db = SessionLocal()

    dispatched = 0
    try:
        now = datetime.now(timezone.utc)

        due = (
            db.query(models.Message)
            .filter(
                models.Message.queue_status == models.MessageQueueStatus.SCHEDULED,
                models.Message.scheduled_at <= now,
            )
            .all()
        )

        for msg in due:
            msg.queue_status = models.MessageQueueStatus.SENT
            dispatched += 1
            logger.info(
                "Dispatching scheduled message id=%s sender_id=%s recipient_id=%s scheduled_at=%s",
                msg.id,
                msg.sender_id,
                msg.recipient_id,
                msg.scheduled_at,
            )

        if dispatched:
            db.commit()
            logger.info("dispatch_scheduled_messages_now: committed %d message(s).", dispatched)
        else:
            logger.debug("dispatch_scheduled_messages_now: no due messages found.")

    except Exception:
        db.rollback()
        logger.exception("dispatch_scheduled_messages_now: error — rolled back.")
        raise
    finally:
        if _owns_db:
            db.close()

    return dispatched


@celery_app.task(
    name="messaging_tasks.dispatch_scheduled_messages",
    bind=True,
    ignore_result=True,
    max_retries=3,
    default_retry_delay=30,
)
def dispatch_scheduled_messages(self) -> None:
    """Celery Beat task: dispatch due scheduled messages."""
    try:
        count = dispatch_scheduled_messages_now()
        logger.info("dispatch_scheduled_messages task: dispatched %d message(s).", count)
    except Exception as exc:
        logger.exception("dispatch_scheduled_messages task failed: %s", exc)
        raise self.retry(exc=exc)
