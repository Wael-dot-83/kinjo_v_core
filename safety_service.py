"""
Safety and Health Module
- Incident Reporting
- Health Alerts
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta, timezone
_JORDAN_TZ = timezone(timedelta(hours=3))
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
    close_incident: Optional[bool] = None  # set True to close; server sets closed_at

class HealthAlertCreate(BaseModel):
    alert_type: str # Allergy, Condition, Medication, etc.
    description: str
    severity: str # Low, Medium, High

# -----------------------------------------------------------------------------
# Incidents
# -----------------------------------------------------------------------------

@router.post("/incidents", status_code=status.HTTP_201_CREATED)
def create_incident(
    incident_data: IncidentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create incident report with JSON body"""
    if current_user.role not in (models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Only staff can report incidents")

    # If parent was not informed, a reason is required
    if not incident_data.parent_informed and not (incident_data.parent_not_informed_reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason required when parent is not informed")

    kindergarten_id = current_user.kindergarten_id
    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID required")

    # Verify child belongs to this kindergarten
    child_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == incident_data.child_id,
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()

    if not child_enrollment:
        child_exists = db.query(models.Child).filter(models.Child.id == incident_data.child_id).first()
        if not child_exists:
            raise HTTPException(status_code=404, detail="Child not found")
        raise HTTPException(status_code=403, detail="Child is not enrolled in this kindergarten")

    if incident_data.occurred_at > datetime.now(_JORDAN_TZ).replace(tzinfo=None): # naive comparison if possible
        pass # Handle tz properly below
    _now = datetime.now(_JORDAN_TZ) if incident_data.occurred_at.tzinfo else datetime.now()
    if incident_data.occurred_at > _now:
        raise HTTPException(status_code=400, detail="occurred_at cannot be in the future")

    incident = models.Incident(
        child_id=incident_data.child_id,
        kindergarten_id=kindergarten_id,
        type=incident_data.type,
        severity_level=incident_data.severity_level,
        description=incident_data.description,
        occurred_at=incident_data.occurred_at,
        followup_required_flag=incident_data.followup_required_flag,
        notify_parent_at=incident_data.notify_parent_at or datetime.now(_JORDAN_TZ),
        reported_by=current_user.id,
        class_id=child_enrollment.class_id,
        parent_informed=incident_data.parent_informed,
        parent_not_informed_reason=incident_data.parent_not_informed_reason,
        status=models.IncidentStatus.OPEN,
    )
    
    if incident.followup_required_flag:
        incident.followup_sla_deadline = datetime.now(_JORDAN_TZ) + timedelta(hours=48)
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    return incident


@router.get("/incidents")
def list_incidents(
    child_id: Optional[int] = None,
    kindergarten_id: Optional[int] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List incidents with optional filtering"""
    from sqlalchemy.orm import joinedload
    
    query = db.query(models.Incident).options(
        joinedload(models.Incident.child),
        joinedload(models.Incident.reported_by_user),
        joinedload(models.Incident.owner)
    )
    
    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Incident.kindergarten_id == current_user.kindergarten_id)
        if current_user.role == models.UserRole.SUPERVISOR:
            # Supervisor can only see incidents for children in their class
            # But the incident has class_id
            supervisor_classes = [sa.class_id for sa in current_user.supervisor_assignments]
            query = query.filter(models.Incident.class_id.in_(supervisor_classes))
    elif kindergarten_id:
        query = query.filter(models.Incident.kindergarten_id == kindergarten_id)
    
    if child_id:
        query = query.filter(models.Incident.child_id == child_id)
    
    if severity:
        query = query.filter(models.Incident.severity_level == models.SeverityLevel(severity.upper()))
        
    if status:
        query = query.filter(models.Incident.status == models.IncidentStatus(status))
        
    if search:
        search_term = f"%{search}%"
        query = query.join(models.Child, models.Incident.child_id == models.Child.id, isouter=True)
        query = query.filter(
            or_(
                models.Incident.description.ilike(search_term),
                models.Child.first_name.ilike(search_term),
                models.Child.last_name.ilike(search_term)
            )
        )
        
    if date_from:
        try:
            from_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=_JORDAN_TZ)
            query = query.filter(models.Incident.occurred_at >= from_dt)
        except ValueError:
            pass
            
    if date_to:
        try:
            to_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=_JORDAN_TZ)
            # Add one day to include the end date fully
            to_dt = to_dt + timedelta(days=1)
            query = query.filter(models.Incident.occurred_at < to_dt)
        except ValueError:
            pass

    total_count = query.count()
    incidents = query.order_by(models.Incident.occurred_at.desc()).offset(skip).limit(limit).all()
    
    items = [
        {
            "id": i.id,
            "child_id": i.child_id,
            "child_name": f"{i.child.first_name} {i.child.last_name}" if i.child else "Unknown",
            "kindergarten_id": i.kindergarten_id,
            "type": i.type.value,
            "severity_level": i.severity_level.value,
            "status": i.status.value,
            "description": i.description,
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
            "followup_required_flag": i.followup_required_flag,
            "reported_by_name": f"{i.reported_by_user.first_name} {i.reported_by_user.last_name}" if i.reported_by_user else None,
            "owner_name": f"{i.owner.first_name} {i.owner.last_name}" if i.owner else None,
            "attachment_url": i.attachment_url,
        }
        for i in incidents
    ]
    return {"items": items, "total_count": total_count}

@router.get("/incidents/summary")
def get_incidents_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summary statistics for incidents"""
    query = db.query(models.Incident)
    
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Incident.kindergarten_id == current_user.kindergarten_id)
        if current_user.role == models.UserRole.SUPERVISOR:
            supervisor_classes = [sa.class_id for sa in current_user.supervisor_assignments]
            query = query.filter(models.Incident.class_id.in_(supervisor_classes))
            
    total_open = query.filter(models.Incident.status == models.IncidentStatus.OPEN).count()
    high_severity = query.filter(
        models.Incident.status != models.IncidentStatus.CLOSED,
        models.Incident.status != models.IncidentStatus.RESOLVED,
        or_(
            models.Incident.severity_level == models.SeverityLevel.HIGH,
            models.Incident.severity_level == models.SeverityLevel.CRITICAL
        )
    ).count()
    resolved = query.filter(models.Incident.status == models.IncidentStatus.RESOLVED).count()
    closed = query.filter(models.Incident.status == models.IncidentStatus.CLOSED).count()
    
    return {
        "total_open": total_open,
        "high_severity": high_severity,
        "resolved": resolved,
        "closed": closed
    }


class IncidentUpdate(BaseModel):
    description: Optional[str] = None
    followup_sla_deadline: Optional[datetime] = None
    status: Optional[models.IncidentStatus] = None
    owner_id: Optional[int] = None
    close_incident: Optional[bool] = None

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
        
    history = models.IncidentHistory(
        incident_id=incident.id,
        changed_by=current_user.id,
        status_from=incident.status,
        owner_from_id=incident.owner_id
    )
    changed = False

    if update_data.description:
        incident.description = update_data.description
        changed = True
    if update_data.followup_sla_deadline:
        incident.followup_sla_deadline = update_data.followup_sla_deadline
        changed = True
    if update_data.status and update_data.status != incident.status:
        incident.status = update_data.status
        history.status_to = update_data.status
        changed = True
    else:
        history.status_to = incident.status
        
    if update_data.owner_id is not None and update_data.owner_id != incident.owner_id:
        incident.owner_id = update_data.owner_id
        history.owner_to_id = update_data.owner_id
        changed = True
    else:
        history.owner_to_id = incident.owner_id

    if update_data.close_incident and incident.status != models.IncidentStatus.CLOSED:
        incident.closed_at = datetime.now(_JORDAN_TZ)
        incident.closed_by = current_user.id
        incident.status = models.IncidentStatus.CLOSED
        history.status_to = models.IncidentStatus.CLOSED
        changed = True

    if changed:
        db.add(history)
        db.commit()
        db.refresh(incident)
        
    return incident

@router.get("/incidents/{incident_id}/history")
def get_incident_history(
    incident_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    incident = db.query(models.Incident).filter(
        models.Incident.id == incident_id,
        models.Incident.kindergarten_id == current_user.kindergarten_id
    ).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    history = db.query(models.IncidentHistory).filter(models.IncidentHistory.incident_id == incident_id).order_by(models.IncidentHistory.timestamp.desc()).all()
    return history


@router.post("/incidents/{incident_id}/attachment")
def upload_incident_attachment(
    incident_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi import UploadFile, File
    import storage_service
    
    validators.validate_manager_role(current_user)
    
    incident = db.query(models.Incident).filter(
        models.Incident.id == incident_id,
        models.Incident.kindergarten_id == current_user.kindergarten_id
    ).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    try:
        provider, storage_key, size = storage_service.save_attachment(file)
        incident.attachment_url = storage_key
        db.commit()
        db.refresh(incident)
        return {"attachment_url": incident.attachment_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Health alert endpoints are now handled by api/portfolio.py
# (create_health_alert and get_child_health_alerts) with improved scope checks.

@router.get("/health-alerts/summary")
def get_health_alerts_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all health alerts and children with medical conditions for the user's scope"""
    from sqlalchemy.orm import joinedload
    
    # 1. Get explicit HealthAlerts
    alerts_query = db.query(models.HealthAlert).join(models.Child)
    
    # 2. Get Children with medical/allergy notes but maybe no explicit HealthAlert
    children_query = db.query(models.Child).filter(
        or_(
            models.Child.has_medical_condition == True,
            models.Child.medical_notes.isnot(None),
            models.Child.allergy_notes.isnot(None)
        )
    )

    if current_user.role != models.UserRole.ADMIN:
        # Filter by kindergarten enrollment
        kindergarten_id = current_user.kindergarten_id
        
        alerts_query = alerts_query.join(
            models.EnrollmentApplication, 
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES)
        )
        
        children_query = children_query.join(
            models.EnrollmentApplication, 
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES)
        )

    alerts = alerts_query.options(joinedload(models.HealthAlert.child)).all()
    children_with_conditions = children_query.all()
    
    # Format the results
    results = []
    
    # Add explicit alerts
    child_alert_map = {}
    for alert in alerts:
        if alert.child_id not in child_alert_map:
            child_alert_map[alert.child_id] = {
                "child_id": alert.child.id,
                "child_name": f"{alert.child.first_name} {alert.child.last_name}",
                "alerts": []
            }
        child_alert_map[alert.child_id]["alerts"].append({
            "type": alert.alert_type,
            "description": alert.description,
            "severity": alert.severity
        })
        
    # Add children with conditions but no explicit alerts
    for child in children_with_conditions:
        if child.id not in child_alert_map:
            alerts_list = []
            if child.allergy_notes:
                alerts_list.append({
                    "type": "Allergy",
                    "description": child.allergy_notes,
                    "severity": "MEDIUM"
                })
            if child.medical_notes or child.has_medical_condition:
                alerts_list.append({
                    "type": "Condition",
                    "description": child.medical_notes or "Has medical condition",
                    "severity": "MEDIUM"
                })
                
            if alerts_list:
                child_alert_map[child.id] = {
                    "child_id": child.id,
                    "child_name": f"{child.first_name} {child.last_name}",
                    "alerts": alerts_list
                }
                
    return list(child_alert_map.values())


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

    now = datetime.now(_JORDAN_TZ)
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
