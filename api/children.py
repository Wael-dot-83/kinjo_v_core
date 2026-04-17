"""
Children domain endpoints
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

router = APIRouter(tags=["Children"])

class ParentProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    second_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    home_governorate: Optional[str] = None
    home_city: Optional[str] = None
    home_area: Optional[str] = None
    home_address_line: Optional[str] = None
    correspondence_preference: Optional[bool] = None


@router.put("/parent-profiles/{parent_id}")
def update_parent_profile(
    parent_id: int,
    payload: ParentProfileUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update parent profile. Parents may update their own profile; Admin can update any."""
    parent = db.query(models.ParentProfile).filter(models.ParentProfile.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    # Authorization
    if current_user.role == models.UserRole.PARENT and parent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    # Apply updates
    changed = False
    for field in ['first_name','second_name','last_name','phone_number','home_governorate','home_city','home_area','home_address_line','correspondence_preference']:
        val = getattr(payload, field)
        if val is not None:
            setattr(parent, field, val)
            changed = True

    if changed:
        db.commit()
        db.refresh(parent)

    # After update, try to mark profiles complete for any children of this parent
    children = db.query(models.Child).filter(models.Child.parent_id == parent.id).all()
    completed_children = []
    missing_map = {}
    for child in children:
        ok, missing = validators.mark_profile_complete_if_ready(db, child.id)
        if ok:
            completed_children.append(child.id)
        else:
            missing_map[child.id] = missing

    return {
        "parent_id": parent.id,
        "profile_complete": bool(parent.profile_complete),
        "completed_children": completed_children,
        "children_missing_fields": missing_map
    }


class ChildUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None  # ISO date
    father_name: Optional[str] = None
    mother_first_name: Optional[str] = None
    mother_second_name: Optional[str] = None
    mother_last_name: Optional[str] = None
    mother_nationality: Optional[str] = None
    mother_national_id: Optional[str] = None
    mother_passport_number: Optional[str] = None


@router.put("/children/{child_id}")
def update_child_profile(
    child_id: int,
    payload: ChildUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update child profile. Parent can update their child; Admin/Manager can as well."""
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Authorization: parent owns child or admin/manager
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this child")

    if current_user.role not in [models.UserRole.PARENT, models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized to update child profiles")

    # Apply updates
    changed = False
    if payload.first_name is not None:
        child.first_name = payload.first_name
        changed = True
    if payload.last_name is not None:
        child.last_name = payload.last_name
        changed = True
    if payload.gender is not None:
        try:
            child.gender = models.Gender(payload.gender.upper())
            changed = True
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid gender")
    if payload.date_of_birth is not None:
        try:
            child.date_of_birth = date.fromisoformat(payload.date_of_birth)
            changed = True
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date_of_birth")
    for field in ['father_name','mother_first_name','mother_second_name','mother_last_name','mother_nationality','mother_national_id','mother_passport_number']:
        val = getattr(payload, field)
        if val is not None:
            setattr(child, field, val)
            changed = True

    if changed:
        db.commit()
        db.refresh(child)

    # After update, attempt to mark profile complete
    ok, missing = validators.mark_profile_complete_if_ready(db, child.id)

    return {
        "child_id": child.id,
        "profile_complete": bool(child.profile_complete),
        "missing_fields": missing
    }


# ============================================================================
# Incidents Endpoints
# ============================================================================

class IncidentCreateRequest(BaseModel):
    child_id: int
    kindergarten_id: Optional[int] = None
    type: str
    severity_level: str
    description: str
    occurred_at: str
    followup_required_flag: Optional[bool] = False


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
def create_incident_json(
    incident_data: IncidentCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create incident report with JSON body"""
    validators.validate_supervisor_role(current_user)
    
    # Use user's kindergarten if not provided
    kindergarten_id = incident_data.kindergarten_id or current_user.kindergarten_id
    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID required")
    
    validators.validate_kindergarten_scope(current_user, kindergarten_id)

    # Verify child belongs to this kindergarten
    child_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == incident_data.child_id,
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()

    if not child_enrollment:
        # Check if child exists at all first to give better error
        child_exists = db.query(models.Child).filter(models.Child.id == incident_data.child_id).first()
        if not child_exists:
            raise HTTPException(status_code=404, detail="Child not found")
        raise HTTPException(status_code=403, detail="Child is not enrolled in this kindergarten")

    incident = models.Incident(
        child_id=incident_data.child_id,
        kindergarten_id=kindergarten_id,
        type=models.IncidentType(incident_data.type.upper()),
        severity_level=models.SeverityLevel(incident_data.severity_level.upper()),
        description=incident_data.description,
        occurred_at=datetime.fromisoformat(incident_data.occurred_at.replace('Z', '+00:00')),
        followup_required_flag=incident_data.followup_required_flag or False,
        notify_parent_at=datetime.now()
    )
    
    if incident.followup_required_flag:
        # Set 48 hour SLA
        incident.followup_sla_deadline = datetime.now() + timedelta(hours=48)
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    return {
        "id": incident.id,
        "child_id": incident.child_id,
        "kindergarten_id": incident.kindergarten_id,
        "type": incident.type.value,
        "severity_level": incident.severity_level.value,
        "followup_required_flag": incident.followup_required_flag
    }


@router.get("/incidents")
def list_incidents(
    child_id: Optional[int] = None,
    kindergarten_id: Optional[int] = None,
    severity: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List incidents with optional filtering"""
    query = db.query(models.Incident)
    
    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Incident.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.Incident.kindergarten_id == kindergarten_id)
    
    if child_id:
        query = query.filter(models.Incident.child_id == child_id)
    
    if severity:
        try:
            severity_enum = models.SeverityLevel(severity.upper())
            query = query.filter(models.Incident.severity_level == severity_enum)
        except ValueError:
            pass
    
    incidents = query.order_by(models.Incident.occurred_at.desc()).all()
    
    return [
        {
            "id": i.id,
            "child_id": i.child_id,
            "kindergarten_id": i.kindergarten_id,
            "type": i.type.value,
            "severity_level": i.severity_level.value,
            "description": i.description,
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
            "followup_required_flag": i.followup_required_flag
        }
        for i in incidents
    ]


@router.post("/incidents/create", status_code=status.HTTP_201_CREATED)
def create_incident(
    kindergarten_id: int,
    child_id: int,
    incident_type: str,
    severity_level: str,
    description: str,
    occurred_at: str,
    followup_required: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create incident report (Manager only)"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    incident = models.Incident(
        child_id=child_id,
        kindergarten_id=kindergarten_id,
        type=models.IncidentType(incident_type.upper()),
        severity_level=models.SeverityLevel(severity_level.upper()),
        description=description,
        occurred_at=datetime.fromisoformat(occurred_at),
        followup_required_flag=followup_required,
        notify_parent_at=datetime.now()
    )
    
    if followup_required:
        # Set 48 hour SLA
        incident.followup_sla_deadline = datetime.now() + timedelta(hours=48)
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    return {
        "id": incident.id,
        "type": incident.type.value,
        "severity_level": incident.severity_level.value,
        "followup_required": incident.followup_required_flag
    }
