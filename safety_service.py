"""
Safety and Health Module
- Incident Reporting
- Health Alerts
 - Safeguarding Cases
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

# Health Alerts CRUD is implemented in missing_endpoints.py with full scope validation.
# Only unique endpoints (not covered by missing_endpoints.py) live here.

# -----------------------------------------------------------------------------
# Safeguarding Cases
# -----------------------------------------------------------------------------

class SafeguardingCreate(BaseModel):
    child_id: int
    kindergarten_id: int
    description: str


@router.post("/safeguarding/create", status_code=status.HTTP_201_CREATED)
def create_safeguarding_case(
    child_id: int,
    kindergarten_id: int,
    description: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a safeguarding case (Manager/Admin only)."""
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Parents are not authorised to create safeguarding cases"
        )
    if current_user.role == models.UserRole.SUPERVISOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisors must escalate through their manager"
        )
    validators.validate_kindergarten_scope(current_user, kindergarten_id)

    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    now = datetime.utcnow()
    case = models.SafeguardingCase(
        child_id=child_id,
        kindergarten_id=kindergarten_id,
        case_description=description,
        status=models.SafeguardingStatus.OPEN,
        opened_at=now,
        sla_escalation_deadline=now + timedelta(hours=24),
        sla_closure_deadline=now + timedelta(days=30),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return {
        "id": case.id,
        "child_id": case.child_id,
        "kindergarten_id": case.kindergarten_id,
        "status": case.status.value,
        "opened_at": case.opened_at.isoformat(),
    }
