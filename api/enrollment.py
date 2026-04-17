"""
Enrollment domain endpoints
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

router = APIRouter(tags=["Enrollment"])

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
        models.ParentProfile, models.Child.parent_id == models.ParentProfile.user_id
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

    # Filter by status if provided
    if status:
        query = query.filter(models.EnrollmentApplication.status == status)

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
    last_name: str
    gender: str
    date_of_birth: str  # ISO format date
    father_name: str
    mother_first_name: str
    mother_last_name: str
    mother_nationality: str
    mother_national_id: str
    kindergarten_id: int


@router.post("/enrollment/apply", status_code=status.HTTP_201_CREATED)
def create_enrollment_application(
    enrollment_data: EnrollmentApplicationRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new enrollment application (Parent only)"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only parents can apply for enrollment")
    
    # Get parent profile
    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        raise HTTPException(status_code=400, detail="Parent profile not found")
    
    # Validate kindergarten exists
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == enrollment_data.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")
    
    # Validate child age (70 days to 56 months)
    dob = date.fromisoformat(enrollment_data.date_of_birth)
    today = date.today()
    age_days = (today - dob).days
    age_months = age_days / 30.44  # Average days per month
    
    if age_days < 70:
        raise HTTPException(status_code=400, detail="Child must be at least 70 days old")
    if age_months > 56:
        raise HTTPException(status_code=400, detail="Child must be under 56 months old")
    
    # Create child record
    child = models.Child(
        parent_id=parent_profile.id,
        first_name=enrollment_data.first_name,
        last_name=enrollment_data.last_name,
        gender=models.Gender(enrollment_data.gender.upper()),
        date_of_birth=dob,
        father_name=enrollment_data.father_name,
        mother_first_name=enrollment_data.mother_first_name,
        mother_last_name=enrollment_data.mother_last_name,
        mother_nationality=enrollment_data.mother_nationality,
        mother_national_id=enrollment_data.mother_national_id
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
    
    if enrollment.status != models.EnrollmentStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft applications can be submitted")
    
    # Verify parent owns this enrollment
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        child = enrollment.child
        if child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized to submit this enrollment")
    
    enrollment.status = models.EnrollmentStatus.SUBMITTED
    enrollment.submitted_at = datetime.now()
    db.commit()
    db.refresh(enrollment)

    return {
        "id": enrollment.id,
        "status": enrollment.status.value.lower(),
        "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None
    }


@router.post("/enrollment/{enrollment_id}/review")
def review_enrollment(
    enrollment_id: int,
    decision: str = Query(..., regex="^(accept|reject)$"),
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

    if enrollment.status != models.EnrollmentStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted applications can be reviewed")

    # Only managers or admins can review
    if current_user.role not in [models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only managers can review applications")

    # Ensure manager is in the same kindergarten
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)

    if decision == "reject":
        if not reason or not reason.strip():
            raise HTTPException(status_code=400, detail="سبب الرفض مطلوب")
        enrollment.status = models.EnrollmentStatus.REJECTED
        enrollment.rejected_at = datetime.now()
        audit_action = "REJECT"
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
        enrollment.status = models.EnrollmentStatus.ACTIVE
        enrollment.accepted_at = datetime.now()
        audit_action = "ACCEPT"

    db.commit()
    db.refresh(enrollment)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=audit_action,
        entity_type="EnrollmentApplication",
        entity_id=enrollment.id,
        details=reason if reason else None,
        sensitivity_level=2
    )

    return {"id": enrollment.id, "status": enrollment.status.value.lower()}
