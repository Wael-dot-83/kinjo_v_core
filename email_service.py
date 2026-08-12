"""SMTP email utilities for transactional notifications."""
import mimetypes
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from config import settings

# An attachment large enough to bounce at the far end helps nobody; refuse it
# here, where the caller can still record a useful status.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# (filename, bytes)
Attachment = Tuple[str, bytes]


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


def _safe_attachment_name(name: str) -> str:
    """Strip directory components and characters that would break the header.

    A caller-supplied name like "../../etc/passwd" or one carrying a newline
    must never reach Content-Disposition.
    """
    base = Path(str(name or "attachment")).name
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ()").strip()
    return cleaned or "attachment"


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: Optional[Sequence[Attachment]] = None,
) -> None:
    """Send a plain-text email, optionally with attachments.

    With no attachments this still builds a bare MIMEText, so every existing
    caller produces exactly the message it did before.
    """
    if not is_smtp_configured():
        raise RuntimeError("SMTP configuration is missing")

    if attachments:
        message = MIMEMultipart()
        message.attach(MIMEText(body, _charset="utf-8"))
        for raw_name, payload in attachments:
            if not isinstance(payload, (bytes, bytearray)):
                raise TypeError("attachment payload must be bytes")
            if len(payload) > MAX_ATTACHMENT_BYTES:
                raise ValueError(
                    f"attachment {raw_name!r} is {len(payload)} bytes, over the "
                    f"{MAX_ATTACHMENT_BYTES} limit"
                )
            filename = _safe_attachment_name(raw_name)
            guessed, _ = mimetypes.guess_type(filename)
            subtype = (guessed or "application/octet-stream").split("/")[-1]
            part = MIMEApplication(bytes(payload), _subtype=subtype)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            message.attach(part)
    else:
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
