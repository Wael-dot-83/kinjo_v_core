"""Public, unauthenticated endpoints (no login required).

Currently: the public Contact Us form, which feeds the existing admin-only
ContactMessage inbox (see admin_endpoints.py).
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session
from fastapi import Depends

import models
from captcha_service import captcha_required, verify_captcha, captcha_error_message
from database import get_db
from rate_limiter import limiter

router = APIRouter(tags=["Public"])

ALLOWED_SUBJECTS = {"enrollment", "technical", "account", "other"}


def _lang_from_request(request: Request) -> str:
    accept = request.headers.get("Accept-Language", "ar")
    return "en" if accept.startswith("en") else "ar"


class ContactMessageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    subject: str = Field(..., max_length=255)
    message: str = Field(..., min_length=1, max_length=5000)
    captcha_token: str | None = Field(default=None, max_length=10000)

    @field_validator("name", "message")
    @classmethod
    def strip_and_require_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("phone")
    @classmethod
    def blank_phone_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        stripped = value.strip().lower()
        return stripped if stripped in ALLOWED_SUBJECTS else "other"


@router.post("/contact")
@limiter.limit("5/minute")
def submit_contact_message(
    request: Request,
    payload: ContactMessageCreate,
    db: Session = Depends(get_db),
):
    """Public Contact Us submission — creates a row in the existing admin-reviewed inbox."""
    if captcha_required() and not verify_captcha(payload.captcha_token):
        raise HTTPException(status_code=400, detail=captcha_error_message(_lang_from_request(request)))

    contact_message = models.ContactMessage(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        subject=payload.subject,
        message=payload.message,
    )
    db.add(contact_message)
    db.commit()

    return {
        "message": "Your message has been received. We will get back to you soon.",
    }
