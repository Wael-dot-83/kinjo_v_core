"""
Classes domain endpoints
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
from config import settings
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Classes"])

class ClassCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kindergarten_id: int
    name_ar: str
    name_en: Optional[str] = None
    class_code: str
    age_group: str
    capacity_total: int = Field(..., ge=1)
    min_age_months: int
    max_age_months: int
    supervisor_id: int

class ClassResponse(ClassCreate):
    id: int
    is_active: bool
    supervisor_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class ClassUpdate(BaseModel):
    name_ar: Optional[str] = None
    name_en: Optional[str] = None
    capacity_total: Optional[int] = Field(None, ge=1)
    min_age_months: Optional[int] = None
    max_age_months: Optional[int] = None
    is_active: Optional[bool] = None
    supervisor_id: Optional[int] = None

@router.post("/classes", status_code=status.HTTP_201_CREATED, response_model=ClassResponse)
def create_class(
    class_data: ClassCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new class (Manager or Admin)"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, class_data.kindergarten_id)

    if class_data.max_age_months < class_data.min_age_months:
        raise HTTPException(status_code=400, detail="Max age must be >= min age")

    # Validate supervisor belongs to the same kindergarten
    supervisor = db.query(models.User).filter(
        models.User.id == class_data.supervisor_id
    ).first()
    if not supervisor:
        raise HTTPException(status_code=400, detail="Supervisor not found")
    if supervisor.kindergarten_id != class_data.kindergarten_id:
        raise HTTPException(status_code=400, detail="Supervisor must belong to the same kindergarten")

    class_dict = class_data.model_dump(exclude={"supervisor_id"})
    class_obj = models.Class(
        **class_dict,
        is_active=True
    )
    if class_data.supervisor_id is not None:
        class_obj.supervisor_id = class_data.supervisor_id

    db.add(class_obj)
    db.commit()
    db.refresh(class_obj)

    # Auto-create primary supervisor assignment when supervisor_id provided
    if class_data.supervisor_id is not None:
        assignment = models.SupervisorAssignment(
            class_id=class_obj.id,
            supervisor_id=class_data.supervisor_id,
            is_primary=True,
            full_time_dedication=True,
            start_date=datetime.now(_JORDAN_TZ).date()
        )
        db.add(assignment)
        db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_CREATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return class_obj


@router.get("/classes")
def list_classes(
    kindergarten_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List classes with filtering and current supervisor info"""
    query = db.query(models.Class)

    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Class.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.Class.kindergarten_id == kindergarten_id)

    if is_active is not None:
        query = query.filter(models.Class.is_active == is_active)

    classes_orm = query.all()
    
    result = []
    today = datetime.now(_JORDAN_TZ).date()
    
    for c in classes_orm:
        # Get active primary supervisor
        current_supervisor = None
        current_primary_assignment = db.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.class_id == c.id,
            models.SupervisorAssignment.is_primary == True,
            models.SupervisorAssignment.start_date <= today,
            (models.SupervisorAssignment.end_date == None) | (models.SupervisorAssignment.end_date >= today)
        ).first()
        
        if current_primary_assignment and current_primary_assignment.supervisor:
            s_user = current_primary_assignment.supervisor
            current_supervisor = {
                "id": s_user.id,
                "name": s_user.username  # User model uses username, not first/last name
            }
            
        c_dict = {
            "id": c.id,
            "name_ar": c.name_ar,
            "name_en": c.name_en,
            "min_age_months": c.min_age_months,
            "max_age_months": c.max_age_months,
            "capacity_total": c.capacity_total,
            "is_active": c.is_active,
            "current_supervisor": current_supervisor
        }
        result.append(c_dict)

    return {"classes": result}


@router.get("/classes/{class_id}/required-supervisors")
def get_class_required_supervisors(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calculate required supervisors for a specific class."""
    cls = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    age_group = cls.age_group or "AGE_2_4"
    children_count = cls.enrolled_children_count if hasattr(cls, 'enrolled_children_count') and cls.enrolled_children_count else 0
    try:
        count = validators.calculate_required_supervisors(age_group, children_count)
    except (validators.ValidationError, ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"required_supervisors": count, "age_group": age_group, "children_count": children_count, "class_id": class_id}


@router.get("/classes/required-supervisors")
def get_required_supervisors(
    age_group: str = Query(...),
    children_count: int = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Preview policy-based required supervisor count for an age group and children count."""
    validators.validate_manager_role(current_user)
    try:
        count = validators.calculate_required_supervisors(age_group, children_count)
    except (validators.ValidationError, ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"required_supervisors": count, "age_group": age_group, "children_count": children_count}


@router.get("/classes/eligible-supervisors")
def get_eligible_supervisors(
    kindergarten_id: int = Query(...),
    class_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List supervisors eligible for assignment. Filters out those already assigned to another class."""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)

    today = datetime.now(_JORDAN_TZ).date()
    # Get all supervisors in this kindergarten
    supervisors = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE
    ).all()

    # Get IDs of supervisors currently assigned to any class (active assignments)
    assigned_query = db.query(models.SupervisorAssignment.supervisor_id).filter(
        models.SupervisorAssignment.start_date <= today,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= today)
    )
    # If class_id specified, exclude assignments TO that class (they remain eligible)
    if class_id is not None:
        assigned_query = assigned_query.filter(models.SupervisorAssignment.class_id != class_id)
    assigned_ids = {row[0] for row in assigned_query.all()}

    result = [
        {"id": s.id, "username": s.username, "email": s.email}
        for s in supervisors if s.id not in assigned_ids
    ]
    return {"supervisors": result}


@router.get("/classes/{class_id}/capacity-status")
def get_class_capacity_status(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current enrollment vs capacity for a class"""
    class_obj = db.query(models.Class).filter(
        models.Class.id == class_id
    ).first()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Count active enrollments assigned to this class
    enrolled_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    return {
        "class_id": class_id,
        "class_name": class_obj.name_en or class_obj.name_ar,
        "capacity_total": class_obj.capacity_total,
        "enrolled_count": enrolled_count,
        "available_spots": class_obj.capacity_total - enrolled_count,
        "utilization_percent": round((enrolled_count / class_obj.capacity_total) * 100, 2) if class_obj.capacity_total > 0 else 0
    }


@router.get("/classes/{class_id}", response_model=ClassResponse)
def get_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific class by ID"""
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Check permissions - admin can see all, others only their kindergarten's classes
    if current_user.role != models.UserRole.ADMIN:
        if class_obj.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return class_obj


@router.put("/classes/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: int,
    class_data: ClassUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update class details (Manager or Admin)"""
    validators.validate_manager_role(current_user)

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    # Validate age range if provided
    if hasattr(class_data, 'max_age_months') and hasattr(class_data, 'min_age_months'):
        if class_data.max_age_months is not None and class_data.min_age_months is not None:
            if class_data.max_age_months < class_data.min_age_months:
                raise HTTPException(status_code=400, detail="Max age must be >= min age")

    # Validate supervisor belongs to same kindergarten
    if class_data.supervisor_id is not None:
        supervisor = db.query(models.User).filter(
            models.User.id == class_data.supervisor_id,
            models.User.role == models.UserRole.SUPERVISOR
        ).first()
        if not supervisor:
            raise HTTPException(status_code=400, detail="Supervisor not found")
        if supervisor.kindergarten_id != class_obj.kindergarten_id:
            raise HTTPException(status_code=400, detail="Supervisor must belong to the same kindergarten as the class")

    # Update fields
    update_data = class_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(class_obj, field, value)

    db.commit()
    db.refresh(class_obj)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_UPDATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return class_obj


@router.put("/classes/{class_id}/deactivate")
def deactivate_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate class (soft delete - Manager or Admin)"""
    validators.validate_manager_role(current_user)

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    if not class_obj.is_active:
        raise HTTPException(status_code=400, detail="Class is already inactive")

    active_like_statuses = [
        models.EnrollmentStatus[status]
        for status in settings.ACTIVE_LIKE_ENROLLMENT_STATUSES
        if status in models.EnrollmentStatus.__members__
    ]
    if not active_like_statuses:
        active_like_statuses = [models.EnrollmentStatus.ACTIVE]

    active_like_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status.in_(active_like_statuses)
    ).count()

    if active_like_enrollments > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot deactivate class with {active_like_enrollments} active enrollment(s). Move children to other classes first."
        )

    class_obj.is_active = False
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_DEACTIVATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return {"message": "Class deactivated successfully", "class_id": class_id}


@router.delete("/classes/{class_id}")
def delete_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Hard delete class (Admin only, when no dependencies exist)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required for permanent deletion")

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Check for any dependencies
    enrollment_count = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id
    ).count()

    supervisor_assignment_count = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.class_id == class_id
    ).count()

    if enrollment_count > 0 or supervisor_assignment_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete class with existing dependencies: {enrollment_count} enrollment(s), {supervisor_assignment_count} supervisor assignment(s)"
        )

    db.delete(class_obj)
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_DELETED",
        entity_type="Class",
        entity_id=class_id,
        sensitivity_level=3
    )

    return {"message": "Class permanently deleted", "class_id": class_id}


# ============================================================================
# Class Assignment Endpoint
# ============================================================================

@router.post("/enrollments/{enrollment_id}/assign-class")
def assign_child_to_class(
    enrollment_id: int,
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign an active enrollment to a specific class (Manager only)"""
    validators.validate_manager_role(current_user)

    # Get enrollment
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()

    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")


    # Validate enrollment is active
    if enrollment.status != models.EnrollmentStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Can only assign active enrollments")

    # Validate kindergarten scope
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)

    # Auto-mark profiles complete if all required data is present
    profile_complete, missing_fields = validators.mark_profile_complete_if_ready(db, enrollment.child_id)
    if not profile_complete:
        raise HTTPException(status_code=400, detail={"message": "Child profile incomplete", "missing_fields": missing_fields})

    # Get class — row-level lock prevents double-booking (see api/enrollment.py review_enrollment)
    class_obj = db.query(models.Class).filter(
        models.Class.id == class_id
    ).with_for_update().first()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Validate class belongs to same kindergarten
    if class_obj.kindergarten_id != enrollment.kindergarten_id:
        raise HTTPException(status_code=400, detail="Class must belong to same kindergarten")

    # Validate age band eligibility
    child = enrollment.child
    try:
        validators.validate_age_band_eligibility(
            child.date_of_birth,
            class_obj.min_age_months,
            class_obj.max_age_months
        )
    except validators.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check capacity
    enrolled_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    if enrolled_count >= class_obj.capacity_total:
        raise HTTPException(status_code=400, detail="Class is at full capacity")

    # Assign to class
    before_state = {
        "class_id": enrollment.class_id,
        "class_assignment_date": enrollment.class_assignment_date.isoformat() if enrollment.class_assignment_date else None,
    }
    enrollment.class_id = class_id
    enrollment.class_assignment_date = datetime.now(_JORDAN_TZ).date()

    db.commit()
    db.refresh(enrollment)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CHILD_ASSIGNED_TO_CLASS",
        entity_type="EnrollmentApplication",
        entity_id=enrollment.id,
        details=f"Child {child.first_name} {child.last_name} assigned to class {class_obj.name_en}",
        sensitivity_level=2,
        old_data=before_state,
        new_data={"class_id": enrollment.class_id, "class_assignment_date": enrollment.class_assignment_date.isoformat()}
    )

    return {
        "enrollment_id": enrollment.id,
        "child_id": enrollment.child_id,
        "class_id": class_id,
        "class_name": class_obj.name_en or class_obj.name_ar,
        "assignment_date": enrollment.class_assignment_date
    }
