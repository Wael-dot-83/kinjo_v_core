"""
Registration domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from audit_actions import AuditAction
import validators
from captcha_service import captcha_error_message, captcha_required, verify_captcha
from config import settings
from database import get_db
from dependencies import get_current_user
from i18n import gettext as _api
from rate_limiter import limiter


def _req_lang(request: Request) -> str:
    """Detect language from Accept-Language header, defaulting to Arabic."""
    accept = request.headers.get("Accept-Language", "ar")
    return "en" if accept.startswith("en") else "ar"


router = APIRouter(tags=["Registration"])

class ParentRegistrationRequest(BaseModel):
    first_name: str
    second_name: Optional[str] = None
    last_name: str
    first_name_en: Optional[str] = None
    last_name_en: Optional[str] = None
    phone_number: str
    gender: str
    nationality: str
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    home_governorate: str
    home_district: str
    home_area: str
    home_address_line: str
    correspondence_preference: Optional[bool] = True
    email: str
    password: str
    work_address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    relationship_to_child: Optional[str] = None
    captcha_token: Optional[str] = None

    @field_validator("home_governorate")
    def validate_home_governorate(cls, value):
        try:
            return validators.validate_jordan_governorate(value)
        except validators.ValidationError as e:
            raise ValueError(str(e))


@router.post("/register/parent", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def register_parent(
    request: Request,
    registration_data: ParentRegistrationRequest,
    db: Session = Depends(get_db)
):
    """Register a new parent user with profile"""
    from auth import get_password_hash

    if not (settings.PUBLIC_REGISTRATION_ENABLED or settings.TESTING):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled. Contact an administrator for an invite.",
        )

    lang = _req_lang(request)
    if captcha_required() and not verify_captcha(registration_data.captcha_token):
        raise HTTPException(status_code=400, detail=captcha_error_message(lang))

    # Check if email already exists (case-insensitive)
    existing_user = db.query(models.User).filter(
        func.lower(models.User.email) == registration_data.email.lower()
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail=_api("Email is already registered.", lang))

    # Validate identification: either national_id or passport_number required
    if not registration_data.national_id and not registration_data.passport_number:
        raise HTTPException(
            status_code=400,
            detail=_api("national_id or passport_number is required", lang)
        )

    # Validate password strength (complexity policy)
    password = registration_data.password
    try:
        validators.validate_password_policy(password)
    except validators.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create user
    user = models.User(
        username=registration_data.email,
        email=registration_data.email,
        hashed_password=get_password_hash(password),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create parent profile
    parent_profile = models.ParentProfile(
        user_id=user.id,
        first_name=registration_data.first_name,
        second_name=registration_data.second_name,
        last_name=registration_data.last_name,
        first_name_en=registration_data.first_name_en,
        last_name_en=registration_data.last_name_en,
        phone_number=registration_data.phone_number,
        gender=models.Gender(registration_data.gender.upper()),
        nationality=registration_data.nationality,
        national_id=registration_data.national_id,
        passport_number=registration_data.passport_number,
        home_governorate=registration_data.home_governorate,
        home_district=registration_data.home_district,
        home_area=registration_data.home_area,
        home_address_line=registration_data.home_address_line,
        correspondence_preference=registration_data.correspondence_preference or True,
        work_address=registration_data.work_address,
        emergency_contact_name=registration_data.emergency_contact_name,
        emergency_contact_phone=registration_data.emergency_contact_phone,
        emergency_contact_relationship=registration_data.emergency_contact_relationship,
        relationship_to_child=registration_data.relationship_to_child,
    )
    db.add(parent_profile)
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=user.id,
        action=AuditAction.REGISTER,
        entity_type="User",
        entity_id=user.id,
        details="Parent registration",
        sensitivity_level=1
    )

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value.lower(),
        "first_name": registration_data.first_name,
        "last_name": registration_data.last_name
    }
