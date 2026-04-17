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
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

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
    home_city: str
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

    @field_validator("home_governorate")
    def validate_home_governorate(cls, value):
        try:
            return validators.validate_jordan_governorate(value)
        except validators.ValidationError as e:
            raise ValueError(str(e))


@router.post("/register/parent", status_code=status.HTTP_201_CREATED)
def register_parent(
    registration_data: ParentRegistrationRequest,
    db: Session = Depends(get_db)
):
    """Register a new parent user with profile"""
    from auth import get_password_hash

    # Check if email already exists
    existing_user = db.query(models.User).filter(
        models.User.email == registration_data.email
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل مسبقاً")

    # Validate identification: either national_id or passport_number required
    if not registration_data.national_id and not registration_data.passport_number:
        raise HTTPException(
            status_code=400,
            detail="يجب إدخال الرقم الوطني أو رقم جواز السفر"
        )

    # Validate password strength (minimum 8 characters)
    password = registration_data.password
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")

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
        home_city=registration_data.home_city,
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
        action="REGISTER",
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
