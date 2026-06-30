"""
Enrollment domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from audit_actions import AuditAction
from config import settings
from database import get_db
from dependencies import get_current_user
from i18n import gettext as _api


def _ulang(user) -> str:
    """Return the user's preferred UI language, defaulting to Arabic."""
    return getattr(user, "preferred_language", None) or "ar"


router = APIRouter(tags=["Enrollment"])

VALID_TRANSITIONS: dict[models.EnrollmentStatus, set[models.EnrollmentStatus]] = {
    models.EnrollmentStatus.DRAFT:          {models.EnrollmentStatus.SUBMITTED, models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.SUBMITTED:      {models.EnrollmentStatus.PENDING_REVIEW, models.EnrollmentStatus.ACCEPTED, models.EnrollmentStatus.REJECTED, models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.PENDING_REVIEW: {models.EnrollmentStatus.ACCEPTED, models.EnrollmentStatus.REJECTED, models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.ACCEPTED:       {models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.ACTIVE:         {models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.WAITLISTED:     {models.EnrollmentStatus.ACCEPTED, models.EnrollmentStatus.WITHDRAWN},
    models.EnrollmentStatus.REJECTED:       set(),
    models.EnrollmentStatus.WITHDRAWN:      set(),
}


def _assert_valid_transition(
    current: models.EnrollmentStatus,
    target: models.EnrollmentStatus,
    lang: str = "ar",
) -> None:
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        msg = (
            f"Cannot move enrollment from {current.value} to {target.value}"
            if lang == "en"
            else f"لا يمكن تغيير حالة الطلب من {current.value} إلى {target.value}"
        )
        raise HTTPException(status_code=400, detail=msg)

@router.get("/enrollments")
def list_enrollments(
    status: Optional[str] = None,
    kindergarten_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List enrollment applications with filtering"""
    query = db.query(
        models.EnrollmentApplication,
        models.Child,
        models.ParentProfile,
        models.Kindergarten
    ).join(
        models.Child, models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.ParentProfile, models.Child.parent_id == models.ParentProfile.id
    ).join(
        models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    )

    # Filter by user role and scope
    if current_user.role == models.UserRole.ADMIN:
        # Admin can see all, but can filter by kindergarten
        if kindergarten_id:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
    elif current_user.role == models.UserRole.MANAGER:
        # Manager can only see enrollments for their kindergarten
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    elif current_user.role == models.UserRole.SUPERVISOR:
        # Supervisor can only see enrollments for their kindergarten
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view enrollments")

    # Filter by status if provided — validate against enum first
    if status:
        try:
            status_enum = models.EnrollmentStatus(status.upper())
            query = query.filter(models.EnrollmentApplication.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {[s.value for s in models.EnrollmentStatus]}")

    # Get total count
    total = query.count()

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Format results
    enrollments = []
    for enrollment, child, parent, kg in results:
        enrollments.append({
            "id": enrollment.id,
            "child_name": f"{child.first_name} {child.last_name}",
            "parent_name": f"{parent.first_name} {parent.last_name}",
            "kindergarten_name": kg.name_ar or kg.name_en,
            "status": enrollment.status.value if hasattr(enrollment.status, 'value') else str(enrollment.status),
            "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
            "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None,
            "kindergarten_id": enrollment.kindergarten_id,
            "child_id": enrollment.child_id
        })

    return {
        "enrollments": enrollments,
        "total": total,
        "skip": skip,
        "limit": limit
    }


class EnrollmentApplicationRequest(BaseModel):
    first_name: str
    second_name: Optional[str] = None
    last_name: str
    gender: str
    date_of_birth: date  # validated by Pydantic → 422 for bad strings
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    father_name: str
    mother_first_name: str
    mother_last_name: str
    mother_nationality: str
    mother_national_id: str
    kindergarten_id: int
    media_consent: Optional[bool] = False
    health_notes: Optional[str] = None
    educational_notes: Optional[str] = None


@router.post("/enrollment/apply", status_code=status.HTTP_201_CREATED)
def create_enrollment_application(
    enrollment_data: EnrollmentApplicationRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new enrollment application (Parent only)"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Only parents can apply for enrollment", _ulang(current_user)))

    # Get parent profile
    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        raise HTTPException(status_code=400, detail=_api("Parent profile not found", _ulang(current_user)))
    
    # Validate kindergarten exists
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == enrollment_data.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Conditional identity validation
    child_nationality = enrollment_data.nationality or ""
    if child_nationality == "Jordanian":
        if not enrollment_data.national_id:
            raise HTTPException(
                status_code=400,
                detail=_api("national_id required for Jordanian children", _ulang(current_user))
            )
    else:
        if child_nationality and not enrollment_data.passport_number:
            raise HTTPException(
                status_code=400,
                detail=_api("passport_number required for non-Jordanian children", _ulang(current_user))
            )
    
    # Check for duplicate enrollment (same child + same KG)
    existing_child = db.query(models.Child).filter(
        models.Child.parent_id == parent_profile.id,
        models.Child.first_name == enrollment_data.first_name,
        models.Child.last_name == enrollment_data.last_name,
        models.Child.date_of_birth == enrollment_data.date_of_birth,
    ).first()
    if existing_child:
        # Only block duplicate if there is a non-terminal enrollment for this child at this KG
        dup_enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == existing_child.id,
            models.EnrollmentApplication.kindergarten_id == enrollment_data.kindergarten_id,
            models.EnrollmentApplication.status.notin_([
                models.EnrollmentStatus.REJECTED,
                models.EnrollmentStatus.WITHDRAWN,
            ]),
        ).first()
        if dup_enrollment:
            raise HTTPException(
                status_code=400,
                detail=_api("An active or pending enrollment already exists for this child at the same kindergarten", _ulang(current_user))
            )
        # Check for active enrollment at any KG
        active = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == existing_child.id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
        ).first()
        if active:
            raise HTTPException(
                status_code=400,
                detail=_api("Child is already enrolled at another kindergarten", _ulang(current_user))
            )

    # Validate child age (1 day to 56 months)
    dob = enrollment_data.date_of_birth
    today = datetime.now(_JORDAN_TZ).date()
    age_days = (today - dob).days
    age_months = age_days / 30.44  # Average days per month

    if age_days < settings.MIN_CHILD_AGE_DAYS:
        raise HTTPException(status_code=400, detail=_api(f"Child must be at least {settings.MIN_CHILD_AGE_DAYS} days old", _ulang(current_user)))
    if age_months > 56:
        raise HTTPException(status_code=400, detail=_api("Child must be under 56 months old", _ulang(current_user)))

    # Create child record (or reuse existing)
    if existing_child:
        child = existing_child
    else:
        # Name matching: child's last_name and second_name must match parent's (new children only)
        if parent_profile.last_name and enrollment_data.last_name != parent_profile.last_name:
            raise HTTPException(
                status_code=400,
                detail=_api("Child last name does not match parent's last name", _ulang(current_user))
            )
        if parent_profile.second_name and enrollment_data.second_name and enrollment_data.second_name != parent_profile.second_name:
            raise HTTPException(
                status_code=400,
                detail=_api("Child second name does not match parent's second name", _ulang(current_user))
            )
        child = models.Child(
            parent_id=parent_profile.id,
            first_name=enrollment_data.first_name,
            second_name=enrollment_data.second_name,
            last_name=enrollment_data.last_name,
            gender=models.Gender(enrollment_data.gender.upper()),
            date_of_birth=dob,
            nationality=enrollment_data.nationality,
            national_id=enrollment_data.national_id,
            passport_number=enrollment_data.passport_number,
            father_name=enrollment_data.father_name,
            mother_first_name=enrollment_data.mother_first_name,
            mother_last_name=enrollment_data.mother_last_name,
            mother_nationality=enrollment_data.mother_nationality,
            mother_national_id=enrollment_data.mother_national_id,
            media_consent=enrollment_data.media_consent,
            health_notes=enrollment_data.health_notes,
            educational_notes=enrollment_data.educational_notes,
        )
        db.add(child)
        db.commit()
        db.refresh(child)
    
    # Create enrollment application
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=enrollment_data.kindergarten_id,
        status=models.EnrollmentStatus.DRAFT,
        source="online"
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    
    return {
        "id": enrollment.id,
        "child_id": child.id,
        "kindergarten_id": enrollment.kindergarten_id,
        "status": enrollment.status.value.lower()
    }


@router.post("/enrollment/{enrollment_id}/submit")
def submit_enrollment(
    enrollment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit enrollment application for review"""
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if current_user.role not in {models.UserRole.PARENT, models.UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Only parents can submit enrollment applications")

    _assert_valid_transition(enrollment.status, models.EnrollmentStatus.SUBMITTED, _ulang(current_user))

    # Verify parent owns this enrollment
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        child = enrollment.child
        if child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail=_api("Not authorized to submit this enrollment", _ulang(current_user)))

    # Check if child has active enrollment elsewhere
    active_elsewhere = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == enrollment.child_id,
        models.EnrollmentApplication.kindergarten_id != enrollment.kindergarten_id,
        models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
    ).first()
    if active_elsewhere:
        raise HTTPException(
            status_code=400,
            detail=_api("Child is already enrolled at another kindergarten", _ulang(current_user))
        )

    enrollment.status = models.EnrollmentStatus.SUBMITTED
    enrollment.submitted_at = datetime.now(_JORDAN_TZ)
    db.commit()
    db.refresh(enrollment)

    return {
        "id": enrollment.id,
        "status": enrollment.status.value.lower(),
        "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None
    }


@router.post("/enrollment/{enrollment_id}/review")
@router.post("/enrollments/{enrollment_id}/review", include_in_schema=False)
def review_enrollment(
    enrollment_id: int,
    decision: str = Query(..., pattern="^(accept|reject)$"),
    reason: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manager reviews (accept/reject) an enrollment application"""
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    target_status = models.EnrollmentStatus.REJECTED if decision == "reject" else models.EnrollmentStatus.ACCEPTED
    _assert_valid_transition(enrollment.status, target_status, _ulang(current_user))

    before_state = {"status": enrollment.status.value, "class_id": enrollment.class_id}

    # Only managers or admins can review
    if current_user.role not in [models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only managers can review applications")

    # Ensure manager is in the same kindergarten
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)

    if decision == "reject":
        if not reason or not reason.strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required.")
        enrollment.status = models.EnrollmentStatus.REJECTED
        enrollment.rejected_at = datetime.now(_JORDAN_TZ)
        enrollment.status_reason = reason.strip()[:255]
        audit_action = AuditAction.ENROLLMENT_REJECTED
    else:
        # Verify profile completeness before accepting
        child = enrollment.child
        ok, missing = validators.check_profile_complete(db, child.id)
        if not ok:
            raise HTTPException(status_code=400, detail={"missing_fields": missing})
        # Verify required documents are uploaded
        docs_ok, missing_docs = validators.validate_required_documents(db, child.id)
        if not docs_ok:
            raise HTTPException(status_code=400, detail={"missing_documents": missing_docs})

        # Require class assignment before acceptance
        if not enrollment.class_id:
            raise HTTPException(
                status_code=400,
                detail=_api("Child must be assigned to a class before the enrollment can be accepted", _ulang(current_user))
            )

        # Class capacity guard — row-level lock prevents double-booking
        if enrollment.class_id:
            class_obj = (
                db.query(models.Class)
                .filter(models.Class.id == enrollment.class_id)
                .with_for_update()
                .first()
            )
            if class_obj:
                active_count = (
                    db.query(func.count(models.EnrollmentApplication.id))
                    .filter(
                        models.EnrollmentApplication.class_id == enrollment.class_id,
                        models.EnrollmentApplication.status.in_(
                            [models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.ACCEPTED]
                        ),
                        models.EnrollmentApplication.id != enrollment.id,
                    )
                    .scalar()
                ) or 0
                if active_count >= class_obj.capacity_total:
                    raise HTTPException(
                        status_code=409,
                        detail=_api(
                            "Class is at full capacity. Place the child on the waitlist.",
                            _ulang(current_user),
                        ),
                    )

        enrollment.status = models.EnrollmentStatus.ACCEPTED
        enrollment.accepted_at = datetime.now(_JORDAN_TZ)
        enrollment.status_reason = None
        audit_action = AuditAction.ENROLLMENT_ACCEPTED

    enrollment.decision_by = current_user.id
    enrollment.decision_at = datetime.now(_JORDAN_TZ)
    db.commit()
    db.refresh(enrollment)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=audit_action,
        entity_type="EnrollmentApplication",
        entity_id=enrollment.id,
        details=reason if reason else None,
        sensitivity_level=2,
        old_data=before_state,
        new_data={"status": enrollment.status.value, "class_id": enrollment.class_id}
    )

    return {
        "id": enrollment.id,
        "status": enrollment.status.value.lower(),
        "decision_at": enrollment.decision_at.isoformat() if enrollment.decision_at else None,
    }
