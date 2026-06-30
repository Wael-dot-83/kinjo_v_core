"""
Kindergartens domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from audit_actions import AuditAction
import validators
from config import settings
from database import get_db
from dependencies import get_current_user
from api.users import DUPLICATE_ERROR_MAP

router = APIRouter(tags=["Kindergartens"])


@router.get("/reference/governorates")
def get_governorates(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return list of governorates and their districts from AdministrativeDivision."""
    divisions = db.query(models.AdministrativeDivision).all()
    
    gov_map = {}
    for div in divisions:
        gov = div.governorate
        dist = div.district
        if not gov:
            continue
        try:
            normalized = validators.validate_jordan_governorate(gov)
        except validators.ValidationError:
            normalized = gov
            
        if normalized not in gov_map:
            english_label = None
            if normalized in settings.JORDAN_GOVERNORATES:
                idx = settings.JORDAN_GOVERNORATES.index(normalized)
                if idx < len(settings.JORDAN_GOVERNORATES_ENGLISH):
                    english_label = settings.JORDAN_GOVERNORATES_ENGLISH[idx]
            gov_map[normalized] = {
                "id": normalized,
                "name_ar": normalized,
                "name_en": english_label or normalized,
                "cities": set() # we will use 'cities' for backwards compatibility with frontend
            }
        
        if dist:
            gov_map[normalized]["cities"].add(dist)
            
    govs = []
    for g in gov_map.values():
        g["cities"] = sorted(list(g["cities"]))
        govs.append(g)
        
    return {"governorates": sorted(govs, key=lambda x: x["name_ar"])}


@router.get("/governorates/{gov}/districts")
def get_districts_by_governorate(
    gov: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return distinct districts for a governorate, from DB records."""
    # Normalise alias
    alias_map = settings.JORDAN_GOVERNORATE_ALIASES
    normalised = alias_map.get(gov, alias_map.get(gov.lower(), gov))

    districts = (
        db.query(models.Kindergarten.district)
        .filter(models.Kindergarten.governorate == normalised)
        .distinct()
        .all()
    )
    return {"governorate": gov, "districts": [d[0] for d in districts if d[0]]}


class KindergartenCreate(BaseModel):
    name_ar: str
    name_en: Optional[str] = None
    governorate: str
    district: str
    area: str
    address_line: str
    contact_phone: str
    contact_email: Optional[EmailStr] = None
    operating_hours_start: Optional[str] = None
    operating_hours_end: Optional[str] = None
    license_number: Optional[str] = None
    license_valid_until: Optional[date] = None

    @field_validator("contact_email", mode="before")
    def normalize_email(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
            value = value.lower()
        return value

    @field_validator("license_number", "license_valid_until", mode="before")
    def blank_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("contact_phone")
    def strip_phone(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("governorate")
    def validate_governorate(cls, value):
        try:
            return validators.validate_jordan_governorate(value)
        except validators.ValidationError as e:
            raise ValueError(str(e))


def detect_kindergarten_duplicate(db: Session, data: KindergartenCreate, exclude_id: Optional[int] = None) -> Optional[str]:
    filters = [
        models.Kindergarten.name_ar == data.name_ar,
        models.Kindergarten.contact_phone == data.contact_phone,
    ]
    if data.name_en:
        filters.append(models.Kindergarten.name_en == data.name_en)
    if data.contact_email:
        filters.append(models.Kindergarten.contact_email == data.contact_email)
    if data.license_number:
        filters.append(models.Kindergarten.license_number == data.license_number)

    if not filters:
        return None

    query = db.query(models.Kindergarten).filter(or_(*filters))
    if exclude_id:
        query = query.filter(models.Kindergarten.id != exclude_id)

    duplicate = query.first()
    if not duplicate:
        return None

    # Return the most relevant conflicting field for a clearer message
    if duplicate.contact_phone == data.contact_phone:
        return "contact_phone"
    if data.contact_email and duplicate.contact_email == data.contact_email:
        return "contact_email"
    if data.license_number and duplicate.license_number == data.license_number:
        return "license_number"
    if duplicate.name_ar == data.name_ar:
        return "name_ar"
    if data.name_en and duplicate.name_en == data.name_en:
        return "name_en"
    return "name_ar"

class KindergartenResponse(KindergartenCreate):
    id: int
    status: models.KindergartenStatus

    model_config = ConfigDict(from_attributes=True)

@router.post("/kindergartens", status_code=status.HTTP_201_CREATED, response_model=KindergartenResponse)
def create_kindergarten(
    kindergarten_data: KindergartenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new kindergarten (Admin only)"""

    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can create kindergartens")

    duplicate_field = detect_kindergarten_duplicate(db, kindergarten_data)
    if duplicate_field:
        raise HTTPException(
            status_code=400,
            detail=DUPLICATE_ERROR_MAP.get(duplicate_field, {"code": "error_duplicate_entry", "message": "Duplicate record found."})
        )

    kindergarten = models.Kindergarten(
        **kindergarten_data.model_dump(),
        status=models.KindergartenStatus.DRAFT
    )

    db.add(kindergarten)
    db.commit()
    db.refresh(kindergarten)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_CREATED,
        entity_type="Kindergarten",
        entity_id=kindergarten.id,
        sensitivity_level=2
    )

    return kindergarten


@router.get("/kindergartens")
def list_kindergartens(
    status: Optional[str] = None,
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List kindergartens with filtering"""
    query = db.query(models.Kindergarten)

    if status:
        query = query.filter(models.Kindergarten.status == models.KindergartenStatus(status))
    if governorate:
        normalized_governorate = governorate
        try:
            normalized_governorate = validators.validate_jordan_governorate(governorate)
        except validators.ValidationError:
            normalized_governorate = governorate
        query = query.filter(models.Kindergarten.governorate.ilike(f"%{normalized_governorate}%"))
    if district:
        query = query.filter(models.Kindergarten.district.ilike(f"%{district}%"))
    if phone:
        query = query.filter(models.Kindergarten.contact_phone.ilike(f"%{phone}%"))
    if name:
        query = query.filter(
            or_(
                models.Kindergarten.name_ar.ilike(f"%{name}%"),
                models.Kindergarten.name_en.ilike(f"%{name}%")
            )
        )

    # For non-admins, only show active kindergartens unless explicitly requested
    if current_user.role != models.UserRole.ADMIN and not include_inactive:
        query = query.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)

    kindergartens = query.offset(skip).limit(limit).all()
    total = query.count()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "kindergartens": kindergartens
    }


@router.get("/kindergartens/{kindergarten_id}")
def get_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get kindergarten details"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Role-based access control
    if current_user.role == models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Supervisors cannot view kindergarten details")
    if current_user.role == models.UserRole.PARENT:
        if kindergarten.status != models.KindergartenStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Kindergarten not found")

    return kindergarten


@router.put("/kindergartens/{kindergarten_id}")
def update_kindergarten(
    kindergarten_id: int,
    kindergarten_data: KindergartenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update kindergarten (Admin or Manager)"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check permissions
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kindergarten_id:
            raise HTTPException(status_code=403, detail="Can only update own kindergarten")
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    duplicate_field = detect_kindergarten_duplicate(db, kindergarten_data, exclude_id=kindergarten_id)
    if duplicate_field:
        raise HTTPException(
            status_code=400,
            detail=DUPLICATE_ERROR_MAP.get(duplicate_field, {"code": "error_duplicate_entry", "message": "Duplicate record found."})
        )

    for field, value in kindergarten_data.model_dump().items():
        setattr(kindergarten, field, value)

    db.commit()
    db.refresh(kindergarten)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_UPDATED,
        entity_type="Kindergarten",
        entity_id=kindergarten.id,
        sensitivity_level=2
    )

    return {
        "id": kindergarten.id,
        "name_ar": kindergarten.name_ar,
        "name_en": kindergarten.name_en,
        "governorate": kindergarten.governorate,
        "district": kindergarten.district,
        "area": kindergarten.area,
        "address_line": kindergarten.address_line,
        "contact_phone": kindergarten.contact_phone,
        "contact_email": kindergarten.contact_email,
        "status": kindergarten.status.value if kindergarten.status else None,
    }


@router.delete("/kindergartens/{kindergarten_id}")
def delete_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete or archive kindergarten based on dependencies"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check permissions
    if current_user.role != models.UserRole.ADMIN:
        if current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id == kindergarten_id:
            # Managers can archive their own kindergarten
            pass
        else:
            raise HTTPException(status_code=403, detail="Access denied.")

    # Check for dependent records
    active_children = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).count()
    active_classes = db.query(models.Class).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active == True
    ).count()
    active_staff = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE
    ).count()

    has_dependencies = active_children > 0 or active_classes > 0 or active_staff > 0

    if has_dependencies:
        if current_user.role != models.UserRole.ADMIN:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete kindergarten with active data. Please archive it instead."
            )
        # Admin can force archive even with dependencies
        kindergarten.status = models.KindergartenStatus.INACTIVE
        action = "archived"
        message = "Kindergarten archived successfully"
        audit_action = "KINDERGARTEN_ARCHIVED"
    else:
        # No dependencies - allow hard delete
        db.delete(kindergarten)
        action = "deleted"
        message = "Kindergarten permanently deleted"
        audit_action = "KINDERGARTEN_DELETED"

    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=audit_action,
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        details=f"Action: {action}, Dependencies: children={active_children}, classes={active_classes}, staff={active_staff}",
        sensitivity_level=3
    )

    return {
        "action": action,
        "message": message,
        "kindergarten_id": kindergarten_id
    }


@router.post("/kindergartens/{kindergarten_id}/archive")
def archive_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive kindergarten (soft delete)"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check permissions
    if current_user.role != models.UserRole.ADMIN:
        if current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id == kindergarten_id:
            # Managers can archive their own kindergarten
            pass
        else:
            raise HTTPException(status_code=403, detail="Access denied.")

    if kindergarten.status == models.KindergartenStatus.INACTIVE:
        raise HTTPException(status_code=400, detail="Kindergarten is already archived.")

    kindergarten.status = models.KindergartenStatus.INACTIVE
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_ARCHIVED,
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        sensitivity_level=2
    )

    return {
        "action": "archived",
        "message": "Kindergarten archived successfully",
        "kindergarten_id": kindergarten_id
    }


@router.post("/kindergartens/{kindergarten_id}/restore")
def restore_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore archived kindergarten"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access only")

    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    if kindergarten.status != models.KindergartenStatus.INACTIVE:
        raise HTTPException(status_code=400, detail="Kindergarten is not archived.")

    kindergarten.status = models.KindergartenStatus.ACTIVE
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_RESTORED,
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        sensitivity_level=2
    )

    return {
        "action": "restored",
        "message": "Kindergarten restored successfully",
        "kindergarten_id": kindergarten_id
    }


# ============================================================================
# Class CRUD Endpoints
# ============================================================================

# ============================================================================
# Kindergarten Services/Facilities CRUD Endpoints
# ============================================================================

class KindergartenServiceCreate(BaseModel):
    kindergarten_id: int
    service_name: str
    description: str
    enabled_flag: Optional[bool] = True

class KindergartenServiceResponse(KindergartenServiceCreate):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class KindergartenServiceUpdate(BaseModel):
    service_name: Optional[str] = None
    description: Optional[str] = None
    enabled_flag: Optional[bool] = None

@router.get("/kindergartens/{kindergarten_id}/services", response_model=List[KindergartenServiceResponse])
def list_kindergarten_services(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all services/facilities for a kindergarten"""
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    services = db.query(models.KindergartenService).filter(models.KindergartenService.kindergarten_id == kindergarten_id).all()
    return services

@router.post("/kindergartens/{kindergarten_id}/services", status_code=status.HTTP_201_CREATED, response_model=KindergartenServiceResponse)
def create_kindergarten_service(
    kindergarten_id: int,
    service_data: KindergartenServiceCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new service/facility for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = models.KindergartenService(
        kindergarten_id=kindergarten_id,
        service_name=service_data.service_name,
        description=service_data.description,
        enabled_flag=service_data.enabled_flag if service_data.enabled_flag is not None else True
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_SERVICE_CREATED,
        entity_type="KindergartenService",
        entity_id=service.id,
        sensitivity_level=2
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=201, content=KindergartenServiceResponse.model_validate(service).model_dump())

@router.put("/kindergartens/{kindergarten_id}/services/{service_id}", response_model=KindergartenServiceResponse)
def update_kindergarten_service(
    kindergarten_id: int,
    service_id: int,
    service_data: KindergartenServiceUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a service/facility for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = db.query(models.KindergartenService).filter(
        models.KindergartenService.id == service_id,
        models.KindergartenService.kindergarten_id == kindergarten_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in service_data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_SERVICE_UPDATED,
        entity_type="KindergartenService",
        entity_id=service.id,
        sensitivity_level=2
    )
    return service

@router.delete("/kindergartens/{kindergarten_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kindergarten_service(
    kindergarten_id: int,
    service_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a service/facility from a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = db.query(models.KindergartenService).filter(
        models.KindergartenService.id == service_id,
        models.KindergartenService.kindergarten_id == kindergarten_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.KINDERGARTEN_SERVICE_DELETED,
        entity_type="KindergartenService",
        entity_id=service_id,
        sensitivity_level=2
    )
    return Response(status_code=204)
