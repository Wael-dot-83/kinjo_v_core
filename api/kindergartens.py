"""
Kindergartens domain endpoints
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from audit_actions import AuditAction
from admin_security import log_audit_event
import validators
from config import settings
from database import get_db
from dependencies import get_current_user
from api.users import DUPLICATE_ERROR_MAP
from auth import get_password_hash
from services.jordan_locations import (
    get_all_governorates,
    get_areas_for_governorate,
    get_governorate_by_key,
    get_governorate_by_name,
    governorate_filter,
)

_JORDAN_TZ = timezone(timedelta(hours=3))
logger = logging.getLogger(__name__)

from rate_limiter import limiter

router = APIRouter(tags=["Kindergartens"])


@router.get("/reference/governorates")
def get_governorates(
    db: Session = Depends(get_db),
):
    """Return all Jordan governorates and their areas from the canonical
    jordan_locations source, augmented with any districts already present in
    kindergarten data so real values still surface.

    Public reference data (no auth) — matches the unified location-filter API.
    """
    governorates = []
    for gov in get_all_governorates():
        cities = {a["name_ar"] for a in get_areas_for_governorate(gov["key"])}
        governorates.append({
            "id": gov["key"],
            "name_ar": gov["name_ar"],
            "name_en": gov["name_en"],
            "_cities": cities,
        })
    by_name = {g["name_ar"]: g for g in governorates}
    # Augment with distinct districts stored on kindergartens (preserves the
    # data-driven behaviour verified by tests/test_reference_governorates.py).
    # Degrade gracefully to the canonical list if the data isn't queryable.
    try:
        kg_rows = (
            db.query(models.Kindergarten.governorate, models.Kindergarten.district)
            .filter(models.Kindergarten.governorate.isnot(None))
            .distinct()
            .all()
        )
    except Exception:
        kg_rows = []
    for gov, dist in kg_rows:
        if not gov or not dist:
            continue
        try:
            normalized = validators.validate_jordan_governorate(gov)
        except validators.ValidationError:
            normalized = gov
        entry = by_name.get(normalized)
        if entry:
            entry["_cities"].add(dist)
    for g in governorates:
        g["cities"] = sorted(g.pop("_cities"))
    return {"governorates": sorted(governorates, key=lambda x: x["name_ar"])}


@router.get("/governorates/{gov}/districts")
def get_districts_by_governorate(gov: str):
    """Return areas for a governorate, from canonical source."""
    gov_obj = get_governorate_by_key(gov)
    if not gov_obj:
        gov_obj = get_governorate_by_name(gov)
    if not gov_obj:
        alias_map = settings.JORDAN_GOVERNORATE_ALIASES
        normalised = alias_map.get(gov, alias_map.get(gov.lower(), gov))
        gov_obj = get_governorate_by_key(normalised)
        if not gov_obj:
            gov_obj = get_governorate_by_name(normalised)
    if not gov_obj:
        raise HTTPException(status_code=404, detail="Governorate not found")
    areas = get_areas_for_governorate(gov_obj["key"])
    return {"governorate": gov_obj["name_ar"], "districts": [a["name_ar"] for a in areas]}



# ============================================================================
# Management Module API (spec-compliant: {success,data,message}, admin-only,
# Arabic messages, soft-delete, freeze/activate).
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query, Request, Body  # noqa: F401
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, case
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from audit_actions import AuditAction
import validators
from database import get_db
from dependencies import get_current_user
from api.users import DUPLICATE_ERROR_MAP
from auth import get_password_hash  # noqa: F401

_JORDAN_TZ = timezone(timedelta(hours=3))


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class KindergartenCreate(BaseModel):
    name_ar: str = Field(..., min_length=1, max_length=255)
    name_en: Optional[str] = None
    legal_name: Optional[str] = None
    type: Optional[str] = None
    governorate: str
    district: str
    area: str
    address_line: str
    contact_phone: str
    mobile: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    website: Optional[str] = None
    manager_name: Optional[str] = None
    manager_id: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_email: Optional[EmailStr] = None
    owner_name: Optional[str] = None
    ownership_type: Optional[str] = None
    total_capacity: Optional[int] = Field(None, ge=0)
    current_child_count: Optional[int] = Field(None, ge=0)
    number_of_classes: Optional[int] = Field(None, ge=0)
    teacher_count: Optional[int] = Field(None, ge=0)
    working_hours_start: Optional[str] = None
    working_hours_end: Optional[str] = None
    working_days: Optional[str] = None
    age_group: Optional[str] = None
    registration_fees: Optional[float] = Field(None, ge=0)
    monthly_fees: Optional[float] = Field(None, ge=0)
    license_number: Optional[str] = None
    license_valid_until: Optional[date] = None
    license_status: Optional[str] = None
    administrative_notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @field_validator("contact_email", "manager_email", mode="before")
    def normalize_email(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value.lower() if value else None
        return value

    @field_validator("license_number", "legal_name", "manager_name", "owner_name",
                     "working_hours_start", "working_hours_end", "working_days",
                     "age_group", "license_status", "type", "ownership_type", mode="before")
    def blank_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("contact_phone", "mobile", "manager_phone")
    def strip_phone(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("governorate")
    def validate_governorate(cls, value):
        try:
            return validators.validate_jordan_governorate(value)
        except validators.ValidationError as e:
            raise ValueError(str(e))


class KindergartenUpdate(BaseModel):
    name_ar: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = None
    legal_name: Optional[str] = None
    type: Optional[str] = None
    governorate: Optional[str] = None
    district: Optional[str] = None
    area: Optional[str] = None
    address_line: Optional[str] = None
    contact_phone: Optional[str] = None
    mobile: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    website: Optional[str] = None
    manager_name: Optional[str] = None
    manager_id: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_email: Optional[EmailStr] = None
    owner_name: Optional[str] = None
    ownership_type: Optional[str] = None
    total_capacity: Optional[int] = Field(None, ge=0)
    current_child_count: Optional[int] = Field(None, ge=0)
    number_of_classes: Optional[int] = Field(None, ge=0)
    teacher_count: Optional[int] = Field(None, ge=0)
    working_hours_start: Optional[str] = None
    working_hours_end: Optional[str] = None
    working_days: Optional[str] = None
    age_group: Optional[str] = None
    registration_fees: Optional[float] = Field(None, ge=0)
    monthly_fees: Optional[float] = Field(None, ge=0)
    license_number: Optional[str] = None
    license_valid_until: Optional[date] = None
    license_status: Optional[str] = None
    administrative_notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @field_validator("contact_email", "manager_email", mode="before")
    def normalize_email_u(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value.lower() if value else None
        return value

    @field_validator("license_number", "governorate", "district", "area", "legal_name",
                     "manager_name", "owner_name", "working_hours_start", "working_hours_end",
                     "working_days", "age_group", "license_status", "type", "ownership_type",
                     "name_en", "address_line", "contact_phone", "mobile", "website",
                     "manager_id", "manager_phone", "administrative_notes", mode="before")
    def blank_to_none_u(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("governorate")
    def validate_governorate_u(cls, value):
        if value is None:
            return value
        try:
            return validators.validate_jordan_governorate(value)
        except validators.ValidationError as e:
            raise ValueError(str(e))


class FreezeRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=255)

class ManagerCreateData(BaseModel):
    full_name: str
    phone_number: str
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    username: str
    email: Optional[EmailStr] = None
    password: str

class KindergartenWithManagerCreate(BaseModel):
    kindergarten: KindergartenCreate
    manager: ManagerCreateData

class AssignManagerRequest(BaseModel):
    user_id: int
    replace: bool = False

def detect_kindergarten_duplicate(db: Session, data, exclude_id: Optional[int] = None) -> Optional[str]:
    filters = [
        models.Kindergarten.name_ar == data.name_ar,
        models.Kindergarten.contact_phone == data.contact_phone,
    ]
    if getattr(data, "name_en", None):
        filters.append(models.Kindergarten.name_en == data.name_en)
    if getattr(data, "contact_email", None):
        filters.append(models.Kindergarten.contact_email == data.contact_email)
    if getattr(data, "license_number", None):
        filters.append(models.Kindergarten.license_number == data.license_number)
    if getattr(data, "legal_name", None):
        filters.append(models.Kindergarten.legal_name == data.legal_name)
    if getattr(data, "manager_id", None):
        filters.append(models.Kindergarten.manager_id == data.manager_id)

    if not filters:
        return None
    query = db.query(models.Kindergarten).filter(or_(*filters))
    if exclude_id:
        query = query.filter(models.Kindergarten.id != exclude_id)
    dup = query.first()
    if not dup:
        return None
    if dup.contact_phone == data.contact_phone:
        return "contact_phone"
    if getattr(data, "license_number", None) and dup.license_number == data.license_number:
        return "license_number"
    if getattr(data, "contact_email", None) and dup.contact_email == data.contact_email:
        return "contact_email"
    if dup.name_ar == data.name_ar:
        return "name_ar"
    if getattr(data, "legal_name", None) and dup.legal_name == data.legal_name:
        return "legal_name"
    return "name_ar"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _envelope(success: bool, data=None, message: str = "", code: int = 200):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=code, content={"success": success, "data": data, "message": message})


def _normalize_status(value: str) -> models.KindergartenStatus:
    v = (value or "").strip().upper()
    mapping = {
        "ACTIVE": models.KindergartenStatus.ACTIVE,
        "FROZEN": models.KindergartenStatus.FROZEN,
        "DELETED": models.KindergartenStatus.DELETED,
        "INACTIVE": models.KindergartenStatus.INACTIVE,
        "DRAFT": models.KindergartenStatus.DRAFT,
    }
    if v not in mapping:
        raise ValueError("invalid_status")
    return mapping[v]


def _stats_subqueries(db: Session):
    from models import EnrollmentApplication, EnrollmentStatus, AttendanceLog, AttendanceStatus, Class
    child_count = (
        db.query(
            EnrollmentApplication.kindergarten_id,
            func.count(EnrollmentApplication.id),
        )
        .filter(EnrollmentApplication.status == EnrollmentStatus.ACTIVE)
        .group_by(EnrollmentApplication.kindergarten_id)
        .subquery()
    )
    attendance = (
        db.query(
            Class.kindergarten_id,
            func.sum(case((AttendanceLog.status == AttendanceStatus.PRESENT, 1), else_=0)),
            func.count(AttendanceLog.id),
        )
        .join(Class, Class.id == AttendanceLog.class_id)
        .group_by(Class.kindergarten_id)
        .subquery()
    )
    return child_count, attendance


# The public API exposes the operating-hours columns under their historical
# `working_hours_*` names (request schemas above, and _serialize below). The
# columns themselves are `operating_hours_*`, so a request payload cannot be
# spread onto the model unchanged — translate it on the way in. This is the
# write-side counterpart of the mapping _serialize performs on the way out.
_MODEL_FIELD_ALIASES = {
    "working_hours_start": "operating_hours_start",
    "working_hours_end": "operating_hours_end",
}


def _to_model_fields(data: dict) -> dict:
    """Rename public API field names to their SQLAlchemy column names."""
    return {_MODEL_FIELD_ALIASES.get(key, key): value for key, value in data.items()}


def _serialize(kg: models.Kindergarten, child_count: Optional[int] = None,
               attendance_present: Optional[int] = None, attendance_total: Optional[int] = None):
    d = {
        "id": kg.id,
        "name_ar": kg.name_ar,
        "name_en": kg.name_en,
        "legal_name": kg.legal_name,
        "type": kg.type,
        "governorate": kg.governorate,
        "district": kg.district,
        "area": kg.area,
        "address_line": kg.address_line,
        "contact_phone": kg.contact_phone,
        "mobile": kg.mobile,
        "contact_email": kg.contact_email,
        "website": kg.website,
        "manager_name": kg.manager_name,
        "manager_id": kg.manager_id,
        "manager_phone": kg.manager_phone,
        "manager_email": kg.manager_email,
        "owner_name": kg.owner_name,
        "ownership_type": kg.ownership_type,
        "total_capacity": kg.total_capacity,
        "current_child_count": kg.current_child_count,
        "number_of_classes": kg.number_of_classes,
        "teacher_count": kg.teacher_count,
        "working_hours_start": kg.operating_hours_start,
        "working_hours_end": kg.operating_hours_end,
        "working_days": kg.working_days,
        "age_group": kg.age_group,
        "registration_fees": kg.registration_fees,
        "monthly_fees": kg.monthly_fees,
        "license_number": kg.license_number,
        "license_valid_until": kg.license_valid_until.isoformat() if kg.license_valid_until else None,
        "license_status": kg.license_status,
        "administrative_notes": kg.administrative_notes,
        "latitude": kg.latitude,
        "longitude": kg.longitude,
        "status": kg.status.value.lower(),
        "frozen_at": kg.frozen_at.isoformat() if kg.frozen_at else None,
        "frozen_reason": kg.frozen_reason,
        "frozen_by": kg.frozen_by,
        "deleted_at": kg.deleted_at.isoformat() if kg.deleted_at else None,
        "created_at": kg.created_at.isoformat() if kg.created_at else None,
        "updated_at": kg.updated_at.isoformat() if kg.updated_at else None,
    }
    active = child_count if child_count is not None else (kg.current_child_count or 0)
    d["child_count"] = active
    d["occupancy_pct"] = round((active / kg.total_capacity) * 100, 1) if kg.total_capacity else None
    if attendance_total:
        d["attendance_pct"] = round((attendance_present / attendance_total) * 100, 1) if attendance_total else None
    else:
        d["attendance_pct"] = None
    return d


def _admin_only(user: models.User):
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access only")


def _public_kindergarten_projection(item: dict) -> dict:
    """Return the enrollment-safe projection exposed outside Admin/Manager."""
    allowed = {
        "id", "name_ar", "name_en", "governorate", "district", "area",
        "address_line", "contact_phone", "contact_email", "status",
        "total_capacity", "current_child_count",
    }
    return {key: value for key, value in item.items() if key in allowed}


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.get("/kindergartens")
def list_kindergartens(
    request: Request,
    q: Optional[str] = Query(None, description="search by name"),
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[str] = None,
    min_children: Optional[int] = None,
    max_children: Optional[int] = None,
    min_occupancy: Optional[float] = None,
    max_occupancy: Optional[float] = None,
    min_attendance: Optional[float] = None,
    max_attendance: Optional[float] = None,
    include_deleted: bool = False,
    skip: int = Query(0, ge=0),
    # Cap must cover the platform's real scale: 635 active kindergartens today,
    # and admin filter UIs load the full list client-side (daily-reports
    # organization page, new-message modal). 1000 keeps a sane bound above that.
    limit: int = Query(20, ge=1, le=1000),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Kindergarten)
    role = current_user.role
    if include_deleted and role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators may include deleted kindergartens")
    if not include_deleted:
        query = query.filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)

    if role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        if not current_user.kindergarten_id:
            query = query.filter(models.Kindergarten.id == -1)
        else:
            query = query.filter(models.Kindergarten.id == current_user.kindergarten_id)
    elif role == models.UserRole.PARENT:
        query = query.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    elif role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    if q:
        query = query.filter(
            or_(
                models.Kindergarten.name_ar.ilike(f"%{q}%"),
                models.Kindergarten.name_en.ilike(f"%{q}%"),
                models.Kindergarten.legal_name.ilike(f"%{q}%"),
            )
        )
    if governorate:
        query = query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
    if district:
        query = query.filter(models.Kindergarten.district == district)
    if status:
        try:
            query = query.filter(models.Kindergarten.status == _normalize_status(status))
        except ValueError:
            return _envelope(False, None, "قيمة الحالة غير صالحة / Invalid status value", 400)

    child_count_sq, attendance_sq = _stats_subqueries(db)
    child_count_expr = func.coalesce(
        child_count_sq.c[1], models.Kindergarten.current_child_count, 0
    )
    occupancy_expr = case(
        (
            models.Kindergarten.total_capacity > 0,
            child_count_expr * 100.0 / models.Kindergarten.total_capacity,
        ),
        else_=None,
    )
    attendance_expr = case(
        (
            attendance_sq.c[2] > 0,
            attendance_sq.c[1] * 100.0 / attendance_sq.c[2],
        ),
        else_=None,
    )

    # Metric filters must participate in the SQL result set before count/offset/limit.
    # Filtering a single page in Python produced sparse pages and totals describing
    # the unfiltered population.
    query = query.outerjoin(
        child_count_sq,
        child_count_sq.c.kindergarten_id == models.Kindergarten.id,
    ).outerjoin(
        attendance_sq,
        attendance_sq.c.kindergarten_id == models.Kindergarten.id,
    )
    if min_children is not None:
        query = query.filter(child_count_expr >= min_children)
    if max_children is not None:
        query = query.filter(child_count_expr <= max_children)
    if min_occupancy is not None:
        query = query.filter(occupancy_expr >= min_occupancy)
    if max_occupancy is not None:
        query = query.filter(occupancy_expr <= max_occupancy)
    if min_attendance is not None:
        query = query.filter(attendance_expr >= min_attendance)
    if max_attendance is not None:
        query = query.filter(attendance_expr <= max_attendance)

    total = query.count()
    kgs = query.order_by(models.Kindergarten.id.desc()).offset(skip).limit(limit).all()

    cc_map = dict(db.query(child_count_sq.c.kindergarten_id, child_count_sq.c[1]).all())
    att_map = {r[0]: (r[1], r[2]) for r in db.query(attendance_sq.c.kindergarten_id, attendance_sq.c[1], attendance_sq.c[2]).all()}

    items = []
    for kg in kgs:
        cc = cc_map.get(kg.id, kg.current_child_count or 0)
        pres, tot = att_map.get(kg.id, (0, 0))
        item = _serialize(kg, child_count=cc, attendance_present=pres, attendance_total=tot)
        items.append(item)

    if role in (models.UserRole.PARENT, models.UserRole.SUPERVISOR):
        items = [_public_kindergarten_projection(item) for item in items]

    return _envelope(
        True,
        {"items": items, "total": total, "skip": skip, "limit": limit, "returned": len(items)},
        "تم جلب قائمة الحضانات بنجاح",
    )


@router.get("/public/kindergartens/search")
@limiter.limit(settings.RATE_LIMIT_PUBLIC_SEARCH)
def public_kindergarten_search(
    request: Request,
    q: Optional[str] = Query(None, description="search by name"),
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Kindergarten)
    query = query.filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)

    if q:
        query = query.filter(
            or_(
                models.Kindergarten.name_ar.ilike(f"%{q}%"),
                models.Kindergarten.name_en.ilike(f"%{q}%"),
                models.Kindergarten.legal_name.ilike(f"%{q}%"),
            )
        )
    if governorate:
        query = query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
    if district:
        query = query.filter(models.Kindergarten.district == district)
    if status:
        try:
            query = query.filter(models.Kindergarten.status == _normalize_status(status))
        except ValueError:
            return _envelope(False, None, "قيمة الحالة غير صالحة / Invalid status value", 400)

    total = query.count()
    kgs = query.order_by(models.Kindergarten.id.desc()).offset(skip).limit(limit).all()

    items = []
    for kg in kgs:
        item = _serialize(kg)
        items.append(_public_kindergarten_projection(item))

    return _envelope(
        True,
        {"items": items, "total": total, "skip": skip, "limit": limit, "returned": len(items)},
        "تم جلب قائمة الحضانات بنجاح",
    )


@router.get("/admin/kindergartens/stats")
def admin_kindergarten_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)

    status_rows = (
        db.query(models.Kindergarten.status, func.count(models.Kindergarten.id))
        .group_by(models.Kindergarten.status)
        .all()
    )
    counts = {
        status.value.lower() if hasattr(status, "value") else str(status).lower(): int(count)
        for status, count in status_rows
    }
    active = counts.get("active", 0)
    frozen = counts.get("frozen", 0)
    draft = counts.get("draft", 0)
    inactive = counts.get("inactive", 0)
    deleted = counts.get("deleted", 0)
    total = active + frozen + draft + inactive

    child_count_sq, _attendance_sq = _stats_subqueries(db)
    children_by_kg = dict(db.query(child_count_sq.c.kindergarten_id, child_count_sq.c[1]).all())
    total_children = int(sum(children_by_kg.values()))

    active_capacity_rows = (
        db.query(models.Kindergarten.id, models.Kindergarten.total_capacity)
        .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        .all()
    )
    total_capacity = int(sum(capacity or 0 for _kg_id, capacity in active_capacity_rows))
    active_children = int(sum(children_by_kg.get(kg_id, 0) for kg_id, _capacity in active_capacity_rows))
    # Keep numerator and denominator on the same ACTIVE-kindergarten population.
    # Using children from frozen/draft kindergartens over active capacity inflated
    # the network occupancy card and made the percentage impossible to interpret.
    avg_occupancy = round((active_children / total_capacity) * 100, 1) if total_capacity else None

    return _envelope(
        True,
        {
            "total": total,
            "active": active,
            "frozen": frozen,
            "draft": draft,
            "inactive": inactive,
            "deleted": deleted,
            "avg_occupancy": avg_occupancy,
            "total_children": total_children,
            "active_children": active_children,
            "total_capacity": total_capacity,
        },
        "Kindergarten statistics loaded successfully",
    )


@router.get("/kindergartens/{kindergarten_id}")
def get_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kg = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id == kindergarten_id)
        .first()
    )
    if not kg or kg.status == models.KindergartenStatus.DELETED:
        return _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)

    # Access control (the envelope refactor dropped this — restored):
    #  - ADMIN: any kindergarten.
    #  - MANAGER: only their own; a cross-tenant id returns 404, never 403, so we
    #    don't leak that another tenant's kindergarten exists.
    #  - PARENT: only ACTIVE kindergartens (they browse open KGs for enrollment);
    #    DRAFT/INACTIVE are hidden as 404.
    #  - SUPERVISOR: not permitted here — supervisors use their own scoped views.
    _not_found = _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)
    role = current_user.role
    if role == models.UserRole.SUPERVISOR:
        return _envelope(False, None, "غير مصرح بالوصول / Not authorized", 403)
    if role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kg.id:
            return _not_found
    elif role == models.UserRole.PARENT:
        if kg.status != models.KindergartenStatus.ACTIVE:
            return _not_found

    child_count_sq, attendance_sq = _stats_subqueries(db)
    cc = db.query(child_count_sq.c[1]).filter(child_count_sq.c.kindergarten_id == kg.id).scalar() or kg.current_child_count or 0
    att = db.query(attendance_sq.c[1], attendance_sq.c[2]).filter(attendance_sq.c.kindergarten_id == kg.id).first()
    pres, tot = (att[0], att[1]) if att else (0, 0)
    serialized = _serialize(kg, child_count=cc, attendance_present=pres, attendance_total=tot)
    if role == models.UserRole.PARENT:
        serialized = _public_kindergarten_projection(serialized)
    return _envelope(True, serialized,
                     "تم جلب بيانات الحضانة بنجاح")


@router.post("/admin/kindergartens", status_code=201)
def create_kindergarten(
    data: KindergartenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    dup = detect_kindergarten_duplicate(db, data)
    if dup:
        msg = {
            "contact_phone": "رقم الهاتف مسجل مسبقاً / Phone number already registered",
            "license_number": "رقم الترخيص مستخدم مسبقاً / License number already used",
            "contact_email": "البريد الإلكتروني مستخدم مسبقاً / Email already registered",
            "name_ar": "يوجد حضانة بنفس الاسم / A kindergarten with this name already exists",
            "legal_name": "الاسم القانوني مستخدم مسبقاً / Legal name already used",
            "manager_id": "رقم المدير مستخدم مسبقاً / Manager ID already used",
        }.get(dup, "سجل مكرر / Duplicate record")
        return _envelope(False, None, msg, 400)

    # A kindergarten without an authenticated manager is not operational yet.
    # Create it as DRAFT; assigning its first manager activates it atomically.
    kg = models.Kindergarten(**_to_model_fields(data.model_dump(exclude_none=True)), status=models.KindergartenStatus.DRAFT)
    db.add(kg)
    db.flush()
    validators.log_audit_action(
        db=db, user_id=current_user.id, action=AuditAction.KINDERGARTEN_CREATED,
        entity_type="Kindergarten", entity_id=kg.id,
        details=f"Created kindergarten {kg.name_ar}", sensitivity_level=2,
    )
    db.commit()
    db.refresh(kg)
    return _envelope(True, _serialize(kg), "تم إنشاء الحضانة بنجاح / Kindergarten created successfully", 201)


@router.put("/admin/kindergartens/{kindergarten_id}")
def update_kindergarten(
    kindergarten_id: int,
    data: KindergartenUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg or kg.status == models.KindergartenStatus.DELETED:
        return _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)

    dup = detect_kindergarten_duplicate(db, data, exclude_id=kg.id)
    if dup:
        msg = {
            "contact_phone": "رقم الهاتف مسجل مسبقاً / Phone number already registered",
            "license_number": "رقم الترخيص مستخدم مسبقاً / License number already used",
            "contact_email": "البريد الإلكتروني مستخدم مسبقاً / Email already registered",
            "name_ar": "يوجد حضانة بنفس الاسم / A kindergarten with this name already exists",
            "legal_name": "الاسم القانوني مستخدم مسبقاً / Legal name already used",
        }.get(dup, "سجل مكرر / Duplicate record")
        return _envelope(False, None, msg, 400)

    for field, value in _to_model_fields(data.model_dump(exclude_none=True)).items():
        setattr(kg, field, value)
    kg.updated_at = datetime.now(_JORDAN_TZ)
    validators.log_audit_action(
        db=db, user_id=current_user.id, action=AuditAction.KINDERGARTEN_UPDATED,
        entity_type="Kindergarten", entity_id=kg.id,
        details=f"Updated kindergarten {kg.name_ar}", sensitivity_level=2,
    )
    db.commit()
    db.refresh(kg)
    return _envelope(True, _serialize(kg), "تم تحديث بيانات الحضانة بنجاح / Kindergarten updated successfully")


@router.patch("/admin/kindergartens/{kindergarten_id}/freeze")
def freeze_kindergarten(
    kindergarten_id: int,
    body: FreezeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg or kg.status == models.KindergartenStatus.DELETED:
        return _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)
    if kg.status == models.KindergartenStatus.FROZEN:
        return _envelope(False, None, "الحضانة مجمدة بالفعل / Already frozen", 400)

    kg.status = models.KindergartenStatus.FROZEN
    kg.frozen_at = datetime.now(_JORDAN_TZ)
    kg.frozen_reason = body.reason
    kg.frozen_by = current_user.id
    suspended = (
        db.query(models.User)
        .filter(models.User.kindergarten_id == kg.id,
                models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
                models.User.status == models.UserStatus.ACTIVE)
        .update({"status": models.UserStatus.SUSPENDED})
    )
    validators.log_audit_action(
        db=db, user_id=current_user.id, action=AuditAction.KINDERGARTEN_FROZEN,
        entity_type="Kindergarten", entity_id=kg.id,
        details=f"Frozen (reason={body.reason}); suspended {suspended} staff", sensitivity_level=3,
    )
    db.commit()
    db.refresh(kg)
    return _envelope(True, _serialize(kg), "تم تجميد الحضانة بنجاح / Kindergarten frozen")


@router.patch("/admin/kindergartens/{kindergarten_id}/activate")
def activate_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    kg = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id == kindergarten_id)
        .with_for_update()
        .first()
    )
    if not kg or kg.status == models.KindergartenStatus.DELETED:
        return _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)
    if kg.status != models.KindergartenStatus.FROZEN:
        return _envelope(False, None, "الحضانة غير مجمدة / Not frozen", 400)

    managers = (
        db.query(models.User)
        .filter(
            models.User.kindergarten_id == kg.id,
            models.User.role == models.UserRole.MANAGER,
            models.User.deleted_at.is_(None),
            models.User.status.in_([models.UserStatus.ACTIVE, models.UserStatus.SUSPENDED]),
        )
        .with_for_update()
        .all()
    )
    if len(managers) != 1:
        return _envelope(
            False,
            None,
            "Kindergarten activation requires exactly one assigned manager",
            409,
        )

    kg.status = models.KindergartenStatus.ACTIVE
    kg.frozen_at = None
    kg.frozen_reason = None
    kg.frozen_by = None
    restored = (
        db.query(models.User)
        .filter(models.User.kindergarten_id == kg.id,
                models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
                models.User.status == models.UserStatus.SUSPENDED)
        .update({"status": models.UserStatus.ACTIVE})
    )
    validators.log_audit_action(
        db=db, user_id=current_user.id, action=AuditAction.KINDERGARTEN_UNFROZEN,
        entity_type="Kindergarten", entity_id=kg.id,
        details=f"Activated; reactivated {restored} staff", sensitivity_level=3,
    )
    db.commit()
    db.refresh(kg)
    return _envelope(True, _serialize(kg), "تم تفعيل الحضانة بنجاح / Kindergarten activated")


@router.delete("/admin/kindergartens/{kindergarten_id}")
def delete_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    kg = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id == kindergarten_id)
        .with_for_update()
        .first()
    )
    if not kg or kg.status == models.KindergartenStatus.DELETED:
        return _envelope(False, None, "الحضانة غير موجودة / Kindergarten not found", 404)

    active_enroll = (
        db.query(models.EnrollmentApplication)
        .filter(models.EnrollmentApplication.kindergarten_id == kg.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
        .count()
    )
    active_staff = (
        db.query(models.User)
        .filter(models.User.kindergarten_id == kg.id,
                models.User.status == models.UserStatus.ACTIVE,
                models.User.deleted_at.is_(None))
        .count()
    )
    if active_enroll > 0 or active_staff > 0:
        return _envelope(False, None, f"لا يمكن الحذف. يوجد {active_enroll} طلب تسجيل نشط و {active_staff} موظف نشط / Cannot delete. Has active enrollments or staff", 400)

    kg.status = models.KindergartenStatus.DELETED
    kg.deleted_at = datetime.now(_JORDAN_TZ)
    kg.deleted_by = current_user.id
    validators.log_audit_action(
        db=db, user_id=current_user.id, action=AuditAction.KINDERGARTEN_DELETED,
        entity_type="Kindergarten", entity_id=kg.id,
        details="Soft deleted", sensitivity_level=3,
    )
    db.commit()
    return _envelope(True, None, "تم حذف الحضانة بنجاح / Kindergarten deleted successfully")

@router.post("/admin/kindergartens/with-manager", status_code=201)
def create_kindergarten_with_manager(
    payload: KindergartenWithManagerCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _admin_only(current_user)
    
    dup_kg = detect_kindergarten_duplicate(db, payload.kindergarten)
    if dup_kg:
        return _envelope(False, None, f"KG Duplicate: {dup_kg}", 409)
        
    filters = [models.User.username == payload.manager.username]
    if payload.manager.email:
        filters.append(models.User.email == payload.manager.email)
    existing = db.query(models.User).filter(or_(*filters)).first()
    if existing:
        return _envelope(False, None, "Username or email already exists", 409)
        
    try:
        kg = models.Kindergarten(**_to_model_fields(payload.kindergarten.model_dump(exclude_none=True)), status=models.KindergartenStatus.ACTIVE)
        db.add(kg)
        db.flush()
        
        mgr = models.User(
            username=payload.manager.username,
            email=payload.manager.email,
            hashed_password=get_password_hash(payload.manager.password),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id,
            must_change_password=True,
            full_name=payload.manager.full_name,
            phone_number=payload.manager.phone_number,
            national_id=payload.manager.national_id,
            nationality=payload.manager.nationality,
        )
        db.add(mgr)
        db.flush()

        log_audit_event(
            db=db,
            action=AuditAction.KINDERGARTEN_CREATED,
            actor=current_user,
            target_type="Kindergarten",
            target_ids=kg.id,
            after_state={
                "name_ar": kg.name_ar,
                "name_en": kg.name_en,
                "status": kg.status.value,
            },
            metadata={"manager_id": mgr.id},
            sensitivity_level=2,
        )
        log_audit_event(
            db=db,
            action=AuditAction.USER_CREATED,
            actor=current_user,
            target_type="User",
            target_ids=mgr.id,
            after_state={
                "role": mgr.role.value,
                "kindergarten_id": kg.id,
                "status": mgr.status.value,
                "must_change_password": mgr.must_change_password,
            },
            sensitivity_level=2,
        )
        db.commit()
        db.refresh(kg)
        db.refresh(mgr)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=201, content={
            "kindergarten": _serialize(kg),
            "manager": {
                "id": mgr.id,
                "must_change_password": mgr.must_change_password,
                "username": mgr.username
            }
        })
        
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to create kindergarten with manager for admin_user_id=%s",
            current_user.id,
        )
        return _envelope(
            False,
            None,
            "تعذر إنشاء الحضانة والمدير. / Unable to create nursery and manager.",
            500,
        )

@router.post("/admin/kindergartens/{kindergarten_id}/assign-manager")
def assign_manager_to_kg(
    kindergarten_id: int,
    payload: AssignManagerRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _admin_only(current_user)
    kg = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id == kindergarten_id)
        .with_for_update()
        .first()
    )
    if not kg:
        raise HTTPException(status_code=404, detail="Not Found")
    if kg.status == models.KindergartenStatus.DELETED:
        raise HTTPException(status_code=404, detail="Kindergarten not found")
    if kg.status == models.KindergartenStatus.FROZEN:
        raise HTTPException(
            status_code=409,
            detail="Managers cannot be assigned while the kindergarten is frozen.",
        )
    
    user = (
        db.query(models.User)
        .filter(
            models.User.id == payload.user_id,
            models.User.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == models.UserRole.ADMIN:
        raise HTTPException(
            status_code=409,
            detail="Administrator accounts cannot be assigned as kindergarten managers.",
        )
        
    from manager_assignment_service import assign_user_as_manager, ManagerAssignmentError
    from sqlalchemy.exc import IntegrityError
    try:
        assign_user_as_manager(db, user, kg.id, actor_id=current_user.id, allow_replace=payload.replace)
        if kg.status in (models.KindergartenStatus.DRAFT, models.KindergartenStatus.INACTIVE):
            kg.status = models.KindergartenStatus.ACTIVE
        db.commit()
        return {"success": True, "message": "Manager assigned"}
    except ManagerAssignmentError as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except IntegrityError as e:
        db.rollback()
        if "uq_users_active_manager_per_kindergarten" in str(e.orig):
            raise HTTPException(
                status_code=409,
                detail="This kindergarten already has an active manager.",
            )
        raise

