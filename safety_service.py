"""
Safety and Health Module
- Incident Reporting
- Health Alerts
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta, timezone
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
    type: models.IncidentType
    severity_level: models.SeverityLevel
    description: str
    occurred_at: datetime
    notify_parent_at: Optional[datetime] = None
    followup_required_flag: bool = False
    parent_informed: bool = True
    parent_not_informed_reason: Optional[str] = None

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

# POST /incidents and GET /incidents are now handled by api/children.py
# (create_incident_json and list_incidents) with improved scope checks.

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
        incident.closed_by = current_user.id
        
    db.commit()
    db.refresh(incident)
    return incident

# Health alert endpoints are now handled by api/portfolio.py
# (create_health_alert and get_child_health_alerts) with improved scope checks.

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

    now = datetime.now(timezone.utc)
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
