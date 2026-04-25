"""SMTP email utilities for transactional notifications."""
import smtplib
from email.mime.text import MIMEText
from typing import Any

from config import settings


def is_smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM)


def check_smtp_health() -> dict[str, Any]:
    """Probe SMTP connectivity and return a health dict.

    Used by the admin health endpoint to make SMTP misconfiguration visible.
    Does NOT send any email — only opens and closes a connection.
    """
    if not is_smtp_configured():
        return {
            "status": "unconfigured",
            "detail": "SMTP_HOST or SMTP_FROM not set — password reset emails disabled",
        }
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5) as smtp:
            smtp.ehlo()
        return {"status": "ok", "host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        return {
            "status": "error",
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "detail": str(exc),
        }


def send_email(to_email: str, subject: str, body: str) -> None:
    if not is_smtp_configured():
        raise RuntimeError("SMTP configuration is missing")

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def send_password_reset_email(to_email: str, token: str, base_url: str) -> None:
    reset_url = f"{base_url.rstrip('/')}/reset-password?token={token}"
    subject = "KinJo password reset"
    body = (
        "We received a password reset request for your KinJo account.\n\n"
        f"Use this link to reset your password:\n{reset_url}\n\n"
        "This link expires in 24 hours. If you did not request this change, you can ignore this email."
    )
    send_email(to_email, subject, body)
