"""
Children domain endpoints
"""
import csv
import io
import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, timezone
_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user
from i18n import gettext as _api
from storage_service import compress_image_in_place
from virus_scan_service import VirusFoundError, VirusScanUnavailable, scan_bytes, scan_error_message


def _ulang(user) -> str:
    """Return the user's preferred UI language, defaulting to Arabic."""
    return getattr(user, "preferred_language", None) or "ar"

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Children"])
MAX_CHILD_EXPORT_ROWS = 10_000


def _authorize_child_access(
    db: Session,
    child: models.Child,
    current_user: models.User,
    *,
    allow_supervisor: bool = True,
) -> None:
    """Enforce child ownership / kindergarten scope for every child subresource.

    Staff lookups deliberately return 404 outside their kindergarten so numeric
    child IDs cannot be used to discover another tenant's records.
    """
    if current_user.role == models.UserRole.ADMIN:
        return
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized for this child")
        return
    if current_user.role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        if current_user.role == models.UserRole.SUPERVISOR and not allow_supervisor:
            raise HTTPException(status_code=403, detail="Manager access required")
        enrollment = db.query(models.EnrollmentApplication.id).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
        ).first()
        if not enrollment:
            raise HTTPException(status_code=404, detail="Child not found")
        return
    raise HTTPException(status_code=403, detail="Not authorized for this child")

class ParentProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    second_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    home_governorate: Optional[str] = None
    home_district: Optional[str] = None
    home_area: Optional[str] = None
    home_address_line: Optional[str] = None
    work_address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    relationship_to_child: Optional[str] = None
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
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    # Authorization — only the profile owner may update their own profile
    if parent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail=_api("Not authorized to update this profile", _ulang(current_user)))

    # Apply updates
    changed = False
    for field in ['first_name','second_name','last_name','phone_number','home_governorate','home_district','home_area','home_address_line','work_address','emergency_contact_name','emergency_contact_phone','emergency_contact_relationship','relationship_to_child','correspondence_preference']:
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

    _authorize_child_access(db, child, current_user, allow_supervisor=False)

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
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid gender")
    if payload.date_of_birth is not None:
        try:
            child.date_of_birth = date.fromisoformat(payload.date_of_birth)
            changed = True
        except ValueError:
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





# ──────────────────────────────────────────────────────────────────
# Photo Upload
# ──────────────────────────────────────────────────────────────────

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}

# Maps content-type to safe extension — never trust client-supplied filename extension
_IMAGE_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

ALLOWED_DOCUMENT_TYPES_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_DOC_TYPE_TO_EXT = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


@router.post("/children/{child_id}/photo")
def upload_child_photo(
    child_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    _authorize_child_access(db, child, current_user)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type. Allowed: png, jpeg, gif, webp")

    # Save file — derive extension from validated content-type, never from client filename.
    upload_dir = os.path.join(settings.BASE_DIR, settings.STATIC_DIR, "uploads", "photos")
    os.makedirs(upload_dir, exist_ok=True)
    ext = _IMAGE_TYPE_TO_EXT.get(file.content_type or "", ".png")
    filename = f"{child_id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB} MB.")

    lang = _ulang(current_user)
    try:
        scan_bytes(content)
    except VirusFoundError:
        raise HTTPException(status_code=400, detail=scan_error_message(lang, infected=True))
    except VirusScanUnavailable:
        raise HTTPException(status_code=503, detail=scan_error_message(lang, infected=False))

    with open(filepath, "wb") as f:
        f.write(content)
    compress_image_in_place(filepath, ext)

    photo_url = f"/{settings.STATIC_DIR}/uploads/photos/{filename}"
    child.photo_url = photo_url
    db.commit()

    return {"photo_url": photo_url}


# ──────────────────────────────────────────────────────────────────
# Document Management
# ──────────────────────────────────────────────────────────────────

VALID_DOCUMENT_TYPES = {
    "birth_certificate", "health_certificate", "permission_form",
    "id_copy", "photo", "other",
}


@router.post("/children/{child_id}/documents")
def upload_child_document(
    child_id: int,
    document_type: str = Query(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    _authorize_child_access(db, child, current_user)

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {', '.join(sorted(VALID_DOCUMENT_TYPES))}")

    if file.content_type not in ALLOWED_DOCUMENT_TYPES_MIME:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PDF, image (png/jpeg), Word document")

    # Save file — derive extension from validated content-type, never from client filename
    upload_dir = os.path.join(settings.BASE_DIR, settings.UPLOADS_DIR, "documents")
    os.makedirs(upload_dir, exist_ok=True)
    ext = _DOC_TYPE_TO_EXT.get(file.content_type or "", ".bin")
    filename = f"{child_id}_{document_type}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB} MB.")

    lang = _ulang(current_user)
    try:
        scan_bytes(content)
    except VirusFoundError:
        raise HTTPException(status_code=400, detail=scan_error_message(lang, infected=True))
    except VirusScanUnavailable:
        raise HTTPException(status_code=503, detail=scan_error_message(lang, infected=False))

    with open(filepath, "wb") as f:
        f.write(content)

    doc = models.ChildDocument(
        child_id=child_id,
        document_type=document_type,
        file_name=file.filename or filename,
        file_path=filepath,
        content_type=file.content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
        verified=False,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "file_name": doc.file_name,
        "verified": doc.verified,
    }


@router.get("/children/{child_id}/documents")
def list_child_documents(
    child_id: int,
    document_type: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    _authorize_child_access(db, child, current_user)

    query = db.query(models.ChildDocument).filter(models.ChildDocument.child_id == child_id)
    if document_type:
        query = query.filter(models.ChildDocument.document_type == document_type)

    docs = query.all()
    return {
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "verified": d.verified,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.put("/children/documents/{doc_id}/verify")
def verify_child_document(
    doc_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parents cannot verify documents")

    doc = db.query(models.ChildDocument).filter(models.ChildDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Non-admin staff can only verify documents for children enrolled in their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == doc.child_id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
        ).first()
        if not enrollment:
            raise HTTPException(status_code=403, detail="Document not in your kindergarten scope")

    doc.verified = True
    doc.verified_by = current_user.id
    doc.verified_at = datetime.now(_JORDAN_TZ)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "verified": doc.verified,
    }


@router.delete("/children/documents/{doc_id}")
def delete_child_document(
    doc_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(models.ChildDocument).filter(models.ChildDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    child = db.query(models.Child).filter(models.Child.id == doc.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Document not found")
    _authorize_child_access(db, child, current_user, allow_supervisor=False)

    # Remove file if it exists
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()

    return {"detail": "Document deleted"}


# ──────────────────────────────────────────────────────────────────
# Bulk Export
# ──────────────────────────────────────────────────────────────────

EXPORTABLE_FIELDS = [
    "first_name", "last_name", "gender", "date_of_birth",
    "nationality", "national_id", "passport_number",
    "health_notes", "educational_notes", "media_consent",
    "father_name", "mother_first_name", "mother_last_name",
]


@router.get("/children/export")
def export_children(
    format: str = Query("csv"),
    fields: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parents cannot export children data")

    # Get active children scoped to the caller's kindergarten (admins see all)
    enrollment_q = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )
    if current_user.role != models.UserRole.ADMIN:
        enrollment_q = enrollment_q.filter(
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id
        )
    child_ids = [e.child_id for e in enrollment_q.all()]
    children = (
        db.query(models.Child)
        .filter(models.Child.id.in_(child_ids))
        .limit(MAX_CHILD_EXPORT_ROWS)
        .all()
    )

    # Determine which fields to export
    if fields:
        selected = [f.strip() for f in fields.split(",") if f.strip() in EXPORTABLE_FIELDS]
    else:
        selected = EXPORTABLE_FIELDS

    rows = []
    for child in children:
        row = {}
        for f in selected:
            val = getattr(child, f, None)
            if isinstance(val, date):
                val = val.isoformat()
            elif isinstance(val, models.Gender):
                val = val.value
            elif val is None:
                val = ""
            else:
                val = str(val)
            row[f] = val
        rows.append(row)

    if format == "json":
        return JSONResponse(content=rows)

    # CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=selected)
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=children_export.csv"},
    )


# --- Migrated from api/supervisor.py ---
@router.get("/children")
def list_children(
    kindergarten_id: Optional[int] = None,
    class_id: Optional[int] = None,
    enrollment_status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    page: int = 1,
    page_size: int = 50,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List children with optional filtering by kindergarten or class"""
    query = db.query(models.Child).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    )

    # Status filter
    if enrollment_status:
        try:
            status_enum = models.EnrollmentStatus(enrollment_status)
        except ValueError:
            status_enum = models.EnrollmentStatus.ACTIVE
        query = query.filter(models.EnrollmentApplication.status == status_enum)
    else:
        query = query.filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )

    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        if current_user.role == models.UserRole.PARENT:
            raise HTTPException(status_code=403, detail="Parents cannot access this endpoint")
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

    if class_id:
        query = query.filter(models.EnrollmentApplication.class_id == class_id)

    # Search
    if search:
        query = query.filter(
            or_(
                models.Child.first_name.ilike(f"%{search}%"),
                models.Child.last_name.ilike(f"%{search}%"),
            )
        )

    # Sorting
    if sort_by == "name":
        order_col = models.Child.first_name
    elif sort_by == "date_of_birth":
        order_col = models.Child.date_of_birth
    else:
        order_col = models.Child.id

    if sort_order == "desc":
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col.asc())

    # Pagination
    total_count = query.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    children = query.offset((page - 1) * page_size).limit(page_size).all()

    child_ids = [c.id for c in children]
    enrollments_by_child = {}
    if child_ids:
        enrollments_by_child = {
            e.child_id: e
            for e in db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.child_id.in_(child_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            ).all()
        }

    result = []
    for child in children:
        enrollment = enrollments_by_child.get(child.id)

        child_info = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "first_name_ar": getattr(child, "first_name_ar", None),
            "last_name_ar": getattr(child, "last_name_ar", None),
            "gender": child.gender.value if child.gender else None,
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "photo_url": child.photo_url,
        }
        if enrollment:
            child_info["enrollment_id"] = enrollment.id
            child_info["class_id"] = enrollment.class_id
            child_info["kindergarten_id"] = enrollment.kindergarten_id

        result.append(child_info)

    return {
        "children": result,
        "pagination": {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }

@router.get("/children/{child_id}/observations")
def get_child_observations(
    child_id: int,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    response: Response = None,
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
            today = datetime.now(_JORDAN_TZ).date()
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

    # Managers are scoped to their own kindergarten.
    #
    # There was no MANAGER branch here at all: parents and supervisors were
    # checked, admins are unrestricted by design, and a manager fell straight
    # through to the unfiltered query below. Verified against the seed data —
    # manager1 (kindergarten 1) read all four developmental observations for
    # child 7, who is enrolled in kindergarten 3, including assessment text and
    # mastery level.
    #
    # Supervisors keep the stricter class-assignment rule above; this only adds
    # the kindergarten boundary a manager was missing. Same guard shape as
    # api/portfolio.py's child-scoped reads.
    # 404 rather than 403, and the same wording _authorize_child_access uses at
    # the top of this file: "Staff lookups deliberately return 404 outside their
    # kindergarten so numeric child IDs cannot be used to discover another
    # tenant's records." A 403 reading "not in your kindergarten scope" would
    # confirm the child exists somewhere else, which is the enumeration oracle
    # tests/test_analytics_tenant_isolation.py exists to prevent.
    if current_user.role == models.UserRole.MANAGER:
        enrollment = db.query(models.EnrollmentApplication.id).filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
        ).first()
        if not enrollment:
            raise HTTPException(status_code=404, detail="Child not found")

    observations_query = db.query(models.Observation).filter(
        models.Observation.child_id == child_id
    )
    total_count = observations_query.count()
    observations = observations_query.order_by(models.Observation.observed_at.desc()).offset(offset).limit(limit).all()

    if response is not None:
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Limit"] = str(limit)
        response.headers["X-Offset"] = str(offset)

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

