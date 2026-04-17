"""
Supervisor domain endpoints
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

router = APIRouter(tags=["Supervisor"])

class SupervisorAssignmentRequest(BaseModel):
    supervisor_id: int
    class_id: int
    start_date: str
    is_primary: bool = False


@router.post("/supervisor/assign", status_code=status.HTTP_201_CREATED)
def assign_supervisor(
    assignment_data: Optional[SupervisorAssignmentRequest] = Body(None),
    supervisor_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    is_primary: bool = Query(False),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign supervisor to class (Manager only). Accepts either JSON body or query params for compatibility."""
    validators.validate_manager_role(current_user)

    # Build assignment_data from query params if body not provided
    if assignment_data is None:
        if supervisor_id is None or class_id is None or start_date is None:
            raise HTTPException(status_code=422, detail="Missing required assignment parameters")
        assignment_data = SupervisorAssignmentRequest(
            supervisor_id=supervisor_id,
            class_id=class_id,
            start_date=start_date,
            is_primary=is_primary
        )

    # Verify class exists
    class_obj = db.query(models.Class).filter(models.Class.id == assignment_data.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")
    
    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)
    
    # Verify supervisor exists and has correct role
    supervisor = db.query(models.User).filter(
        models.User.id == assignment_data.supervisor_id,
        models.User.role == models.UserRole.SUPERVISOR
    ).first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    # Check if supervisor is already assigned to any class on this date
    new_start = date.fromisoformat(assignment_data.start_date)
    existing = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == assignment_data.supervisor_id,
        models.SupervisorAssignment.start_date <= new_start,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= new_start)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Supervisor already assigned to a class on this date")
    
    assignment = models.SupervisorAssignment(
        class_id=assignment_data.class_id,
        supervisor_id=assignment_data.supervisor_id,
        start_date=date.fromisoformat(assignment_data.start_date),
        is_primary=assignment_data.is_primary
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return {
        "id": assignment.id,
        "supervisor_id": assignment.supervisor_id,
        "class_id": assignment.class_id,
        "is_primary": assignment.is_primary,
        "start_date": assignment.start_date.isoformat()
    }


@router.post("/supervisor/assign-replacement", status_code=status.HTTP_201_CREATED)
def assign_replacement_supervisor(
    class_id: int = Query(...),
    replacement_supervisor_id: int = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    reason: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a replacement supervisor for a class (Manager only)"""
    validators.validate_manager_role(current_user)

    # Verify class exists
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    # Verify replacement supervisor exists and has correct role
    supervisor = db.query(models.User).filter(
        models.User.id == replacement_supervisor_id,
        models.User.role == models.UserRole.SUPERVISOR
    ).first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Replacement supervisor not found")

    assignment = models.SupervisorAssignment(
        class_id=class_id,
        supervisor_id=replacement_supervisor_id,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date)
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "id": assignment.id,
        "replacement_supervisor_id": assignment.supervisor_id,
        "class_id": assignment.class_id,
        "start_date": assignment.start_date.isoformat(),
        "end_date": assignment.end_date.isoformat() if assignment.end_date else None
    }


class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str
    mastery_level: Optional[str] = None


@router.post("/observations", status_code=status.HTTP_201_CREATED)
def create_observation(
    observation_data: ObservationRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new observation (Supervisor/Manager/Admin only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create observations")
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == observation_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    # Parse observed_at from ISO string if provided
    observed_at = datetime.now()
    if hasattr(observation_data, 'observed_at') and observation_data.observed_at:
        try:
            observed_at = datetime.fromisoformat(observation_data.observed_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=observed_at
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value,
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }


@router.get("/children/{child_id}/observations")
def get_child_observations(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all observations for a specific child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Parents can only see their own child's observations
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Supervisors can only see observations for children in their assigned class
    if current_user.role == models.UserRole.SUPERVISOR:
        active_enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()
        if active_enrollment:
            today = date.today()
            assignment = db.query(models.SupervisorAssignment).filter(
                models.SupervisorAssignment.supervisor_id == current_user.id,
                models.SupervisorAssignment.class_id == active_enrollment.class_id,
                models.SupervisorAssignment.start_date <= today,
                or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= today)
            ).first()
            if not assignment:
                raise HTTPException(status_code=403, detail="Not assigned to child's class")
        else:
            raise HTTPException(status_code=403, detail="Child not enrolled in any active class")

    observations = db.query(models.Observation).filter(
        models.Observation.child_id == child_id
    ).order_by(models.Observation.observed_at.desc()).all()

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": o.id,
            "child_id": o.child_id,
            "domain": o.domain.value,
            "observation_text": o.observation_text,
            "mastery_level": o.mastery_level.value if o.mastery_level else None,
            "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            "observed_by": o.observed_by
        }
        for o in observations
    ]


class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str
    mastery_level: Optional[str] = None
    observed_at: Optional[str] = None  # ISO format datetime string


@router.post("/supervisor/observations/record", status_code=status.HTTP_201_CREATED)
def record_observation(
    observation_data: Optional[ObservationRecordRequest] = Body(None),
    child_id: Optional[int] = Query(None),
    domain: Optional[str] = Query(None),
    observation_text: Optional[str] = Query(None),
    mastery_level: Optional[str] = Query(None),
    observed_at: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record child observation (Supervisor only). Accepts either JSON body or query params for compatibility."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can record observations")

    # Build observation_data from query params if body not provided
    if observation_data is None:
        if child_id is None or domain is None or observation_text is None:
            raise HTTPException(status_code=422, detail="Missing required observation parameters")
        observation_data = ObservationRecordRequest(
            child_id=child_id,
            domain=domain,
            observation_text=observation_text,
            mastery_level=mastery_level,
            observed_at=observed_at
        )
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == observation_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify active enrollment and supervisor scope
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child.id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    if not active_enrollment:
        raise HTTPException(status_code=400, detail="Child not active in any class")

    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)

    # Verify supervisor is assigned to the child's class
    today = date.today()
    assignment = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        models.SupervisorAssignment.class_id == active_enrollment.class_id,
        models.SupervisorAssignment.start_date <= today,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= today)
    ).first()
    if not assignment:
        raise HTTPException(status_code=403, detail="Not assigned to child's class")

    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=datetime.now()
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value.lower(),
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }


@router.get("/supervisor/children")
def get_supervisor_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all children in classes assigned to current supervisor"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")

    from supervisor_service import SupervisorService
    children = SupervisorService.get_supervisor_children(db, current_user)
    
    # Enrich with today's attendance status
    today = date.today()
    results = []
    
    for child in children:
        # Get active enrollment for class info
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        attendance = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == child.id,
            models.AttendanceLog.date == today
        ).first()
        
        status = "absent"
        check_in_time = None
        check_out_time = None
        
        if attendance:
            status = "present" if not attendance.check_out_at else "checked_out"
            check_in_time = attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None
            check_out_time = attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None
            
        results.append({
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value,
            "photo_url": child.photo_url,
            "class_id": enrollment.class_id if enrollment else None,
            "attendance_status": status,
            "check_in_time": check_in_time,
            "check_out_time": check_out_time,
            "name": f"{child.first_name} {child.last_name}" # Full name
        })
        
    return {"children": results}


@router.get("/children")
def list_children(
    kindergarten_id: Optional[int] = None,
    class_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List children with optional filtering by kindergarten or class"""
    query = db.query(models.Child).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )

    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

    if class_id:
        query = query.filter(models.EnrollmentApplication.class_id == class_id)

    children = query.all()

    result = []
    for child in children:
        # Get enrollment info
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        child_info = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "first_name_ar": child.first_name_ar,
            "last_name_ar": child.last_name_ar,
            "gender": child.gender.value if child.gender else None,
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "photo_url": child.photo_url,
        }
        if enrollment:
            child_info["enrollment_id"] = enrollment.id
            child_info["class_id"] = enrollment.class_id
            child_info["kindergarten_id"] = enrollment.kindergarten_id
            
        result.append(child_info)

    return {"children": result}


@router.get("/supervisor/my-classes")
def get_supervisor_classes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get classes assigned to current supervisor"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")
    
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= date.today()
        )
    ).all()
    
    classes = []
    for assignment in assignments:
        class_obj = assignment.class_
        classes.append({
            "id": class_obj.id,
            "name_ar": class_obj.name_ar,
            "name_en": class_obj.name_en,
            "kindergarten_id": class_obj.kindergarten_id,
            "is_primary": assignment.is_primary
        })
    
    return {"classes": classes}


@router.get("/supervisor/dashboard")
def get_supervisor_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get supervisor dashboard data"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access dashboard")
    
    # Get supervisor's classes
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= date.today()
        )
    ).all()
    
    class_ids = [a.class_id for a in assignments]
    
    # Count children in assigned classes
    total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0
    
    # Count today's attendance
    today = date.today()
    today_attendance = db.query(func.count(models.AttendanceLog.id)).join(
        models.EnrollmentApplication,
        models.AttendanceLog.child_id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.AttendanceLog.date == today
    ).scalar() or 0
    
    # Pending daily reports
    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.submitted_by == current_user.id,
        models.DailyReport.status == models.DailyReportStatus.DRAFT
    ).scalar() or 0
    
    # Build class details list
    classes_detail = []
    for a in assignments:
        class_obj = db.query(models.Class).filter(models.Class.id == a.class_id).first()
        if class_obj:
            classes_detail.append({
                "id": class_obj.id,
                "name_ar": class_obj.name_ar,
                "name_en": class_obj.name_en,
                "kindergarten_id": class_obj.kindergarten_id,
                "is_primary": a.is_primary
            })

    return {
        "supervisor_id": current_user.id,
        "classes": classes_detail,
        "attendance_summary": {"today": today_attendance},
        "total_children": total_children,
        "pending_reports": pending_reports,
        "date": today.isoformat()
    }
