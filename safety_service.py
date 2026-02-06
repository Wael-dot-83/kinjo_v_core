"""
Safety and Health Module
- Incident Reporting
- Health Alerts
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

import models
import validators
from database import get_db
from dependencies import get_current_user

router = APIRouter()

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class IncidentCreate(BaseModel):
    child_id: int
    type: str # INJURY, BEHAVIOR, ILLNESS, OTHER
    severity_level: str # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    occurred_at: datetime
    notify_parent_at: Optional[datetime] = None
    followup_required_flag: bool = False

class IncidentUpdate(BaseModel):
    description: Optional[str] = None
    followup_sla_deadline: Optional[datetime] = None
    closed_at: Optional[datetime] = None

class HealthAlertCreate(BaseModel):
    alert_type: str # Allergy, Condition, Medication, etc.
    description: str
    severity: str # Low, Medium, High

# -----------------------------------------------------------------------------
# Incidents
# -----------------------------------------------------------------------------

@router.post("/incidents", status_code=status.HTTP_201_CREATED)
def report_incident(
    incident_data: IncidentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Report a new incident"""
    # Supervisors and Managers can report
    validators.validate_supervisor_role(current_user)
    
    # Verify child exists and belongs to user's kindergarten scope
    child = db.query(models.Child).filter(models.Child.id == incident_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
        
    # Check enrollment to map to kindergarten if not obvious (but User has kindergarten_id)
    # Ideally should check if child is enrolled in current_user.kindergarten_id
    if current_user.role != models.UserRole.ADMIN:
        # Check active enrollment in user's KG
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()
        
        if not enrollment and current_user.role != models.UserRole.ADMIN:
             # Fallback: maybe just check if child parent profile is linked? 
             # Sticking to: Child MUST be enrolled in the reporter's KG to report incident there.
             raise HTTPException(status_code=400, detail="Child is not currently enrolled in your kindergarten")

    incident = models.Incident(
        child_id=incident_data.child_id,
        kindergarten_id=current_user.kindergarten_id,
        type=models.IncidentType(incident_data.type),
        severity_level=models.SeverityLevel(incident_data.severity_level),
        description=incident_data.description,
        occurred_at=incident_data.occurred_at,
        notify_parent_at=incident_data.notify_parent_at,
        followup_required_flag=incident_data.followup_required_flag
    )
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident

@router.get("/incidents")
def list_incidents(
    child_id: Optional[int] = None,
    unresolved_only: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List incidents for the kindergarten"""
    validators.validate_supervisor_role(current_user)
    
    query = db.query(models.Incident).filter(
        models.Incident.kindergarten_id == current_user.kindergarten_id
    )
    
    if child_id:
        query = query.filter(models.Incident.child_id == child_id)
        
    if unresolved_only:
        query = query.filter(models.Incident.closed_at == None)
        
    return query.order_by(desc(models.Incident.occurred_at)).all()

@router.put("/incidents/{incident_id}")
def update_incident(
    incident_id: int,
    update_data: IncidentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update incident details or close it"""
    validators.validate_manager_role(current_user) # Only managers can update/close for now
    
    incident = db.query(models.Incident).filter(
        models.Incident.id == incident_id,
        models.Incident.kindergarten_id == current_user.kindergarten_id
    ).first()
    
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    if update_data.description:
        incident.description = update_data.description
    if update_data.followup_sla_deadline:
        incident.followup_sla_deadline = update_data.followup_sla_deadline
    if update_data.closed_at:
        incident.closed_at = update_data.closed_at
        
    db.commit()
    db.refresh(incident)
    return incident

# -----------------------------------------------------------------------------
# Health Alerts
# -----------------------------------------------------------------------------

@router.post("/children/{child_id}/health-alerts", status_code=status.HTTP_201_CREATED)
def create_health_alert(
    child_id: int,
    alert_data: HealthAlertCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a health alert to a child (Allergy, etc.)"""
    # Parent can add? OR Manager? Let's say Manager/Supervisor + Parent (if they own the child)
    # For now, implementing for Staff side.
    validators.validate_supervisor_role(current_user)
    
    # Check access to child similar to incident
    # ... (Simplified check: assuming child exists and user has access)
    
    alert = models.HealthAlert(
        child_id=child_id,
        alert_type=alert_data.alert_type,
        description=alert_data.description,
        severity=alert_data.severity
    )
    
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

@router.get("/children/{child_id}/health-alerts")
def get_health_alerts(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get health alerts for a child"""
    # Should validate user has access to this child
    
    return db.query(models.HealthAlert).filter(models.HealthAlert.child_id == child_id).all()

# -----------------------------------------------------------------------------
# Safeguarding Cases
# -----------------------------------------------------------------------------

class SafeguardingCaseCreate(BaseModel):
    child_id: int
    case_description: str
    kindergarten_id: Optional[int] = None


@router.post("/safeguarding/create", status_code=status.HTTP_201_CREATED)
def create_safeguarding_case(
    case_data: SafeguardingCaseCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new safeguarding case.
    Only Managers and Admins can create safeguarding cases.
    SLA: 24h escalation deadline, 7 days closure deadline.
    """
    validators.validate_manager_role(current_user)

    # Resolve kindergarten
    kindergarten_id = case_data.kindergarten_id or current_user.kindergarten_id
    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID is required")

    # Scope check for managers
    if current_user.role != models.UserRole.ADMIN:
        validators.validate_kindergarten_scope(current_user, kindergarten_id)

    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == case_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify child is enrolled in this kindergarten
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == case_data.child_id,
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    if not enrollment:
        raise HTTPException(
            status_code=400,
            detail="Child is not currently enrolled in the specified kindergarten"
        )

    now = datetime.now()
    safeguarding_case = models.SafeguardingCase(
        child_id=case_data.child_id,
        kindergarten_id=kindergarten_id,
        case_description=case_data.case_description,
        opened_at=now,
        sla_escalation_deadline=now + timedelta(hours=24),
        sla_closure_deadline=now + timedelta(days=7)
    )

    db.add(safeguarding_case)
    db.commit()
    db.refresh(safeguarding_case)

    return {
        "id": safeguarding_case.id,
        "child_id": safeguarding_case.child_id,
        "kindergarten_id": safeguarding_case.kindergarten_id,
        "case_description": safeguarding_case.case_description,
        "opened_at": safeguarding_case.opened_at.isoformat(),
        "sla_escalation_deadline": safeguarding_case.sla_escalation_deadline.isoformat(),
        "sla_closure_deadline": safeguarding_case.sla_closure_deadline.isoformat()
    }
