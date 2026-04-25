"""Shared password reset domain service."""
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from email_service import is_smtp_configured, send_password_reset_email

logger = logging.getLogger(__name__)


def issue_password_reset_token(
    db: Session,
    user: models.User,
    expires_hours: int = 24,
    invalidate_existing: bool = True,
) -> str:
    """Create a new reset token for a user and optionally invalidate existing tokens."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

    if invalidate_existing:
        (
            db.query(models.PasswordResetToken)
            .filter(
                models.PasswordResetToken.user_id == user.id,
                models.PasswordResetToken.used.is_(False),
            )
            .update({"used": True})
        )

    db.add(
        models.PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
        )
    )
    db.commit()
    return token


def resolve_valid_token(db: Session, token: str) -> Optional[models.PasswordResetToken]:
    """Return an unexpired, unused reset token record if valid."""
    return (
        db.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.token == token,
            models.PasswordResetToken.used.is_(False),
            models.PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )


def deliver_password_reset_email(base_url: str, user: models.User, token: str) -> bool:
    """Best-effort email delivery for password reset links."""
    if not user.email or not is_smtp_configured():
        return False
    try:
        send_password_reset_email(user.email, token, base_url)
        return True
    except (smtplib.SMTPException, OSError, RuntimeError, ValueError) as exc:
        logger.exception("Password reset email delivery failed for user_id=%s: %s", user.id, exc)
        return False
