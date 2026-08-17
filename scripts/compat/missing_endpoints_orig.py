"""
Missing endpoints required by test_missing_endpoints.py.
All routes are registered under the /api prefix in main.py.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

import auth
import models
import validators
from api.absence_requests import MAX_ABSENCE_SPAN_DAYS
from database import get_db
from dependencies import get_current_user
from utils.time_utils import today_amman

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas (request bodies only – responses are plain dicts)
# ---------------------------------------------------------------------------

class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str


class AttendanceMarkBody(BaseModel):
    child_id: int
    status: str  # PRESENT | ABSENT


class BulkAttendanceBody(BaseModel):
    child_ids: list[int]
    status: str


class AbsenceRequestBody(BaseModel):
    child_id: int
    from_date: date
    to_date: date
    reason: str


class CorrespondingAssignBody(BaseModel):
    contact_name: str
    contact_phone: str
    relationship: Optional[str] = None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.put("/users/me/password")
def change_own_password(
    body: PasswordChangeBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    errors = auth.validate_password_complexity(body.new_password)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    auth.change_user_password(db, current_user, body.new_password)
    return {"message": "Password updated successfully"}


@router.get("/users/me/parent-info")
def get_parent_info(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id,
        models.ParentProfile.deleted_at.is_(None),
    ).first()
    if not profile:
        return {"parent_type": None}
    return {
        "parent_type": profile.parent_type,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "full_name": f"{profile.first_name} {profile.last_name}",
        "phone_number": profile.phone_number,
    }


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Use raw SQL without payload column to avoid JSON hydration errors on malformed stored values
    total = db.execute(
        text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid"),
        {"uid": current_user.id},
    ).scalar() or 0

    rows = db.execute(
        text(
            "SELECT id, notification_type, status, created_at "
            "FROM notifications WHERE user_id = :uid "
            "ORDER BY created_at DESC LIMIT :lim"
        ),
        {"uid": current_user.id, "lim": limit},
    ).fetchall()

    items = []
    for row in rows:
        notif_type = row[1]
        title = str(notif_type) if notif_type else "إشعار"
        created_raw = row[3]
        if created_raw is None:
            created_str = None
        elif hasattr(created_raw, "isoformat"):
            created_str = created_raw.isoformat()
        else:
            created_str = str(created_raw)

        items.append({
            "id": row[0],
            "title": title,
            "status": row[2],
            "created_at": created_str,
        })

    return {"items": items, "total": total}


@router.get("/notifications/unread-count")
def unread_notification_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.status == models.NotificationStatus.PENDING,
    ).scalar() or 0
    return {"count": count}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.status == models.NotificationStatus.PENDING,
        )
        .update({"status": models.NotificationStatus.SENT})
    )
    db.commit()
    return {"updated": updated}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark one notification read.

    templates/user/notifications.html has always rendered a per-notification control
    calling this, but only /read-all existed, so the request 404'd — and the caller
    never checked `response.ok`, so it reloaded the list and the notification simply
    stayed unread with no error. "Nothing happens when I click it" is the whole bug.

    `user_id == current_user.id` is in the UPDATE itself, not a fetch-then-check: the
    id comes from the URL, so without it any user could mark anyone's notification
    read by guessing an integer.
    """
    updated = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
            # PENDING only, matching /read-all. Without it a FAILED notification would
            # flip to SENT — this endpoint would be claiming a delivery that failed.
            models.Notification.status == models.NotificationStatus.PENDING,
        )
        .update({"status": models.NotificationStatus.SENT})
    )
    db.commit()
    if not updated:
        # Nothing changed: either the row is not ours/absent, or it was not PENDING.
        # The existence probe is itself ownership-scoped, so it cannot be used to test
        # whether an id exists — a missing row and someone else's row both 404.
        owned = (
            db.query(models.Notification.id)
            .filter(
                models.Notification.id == notification_id,
                models.Notification.user_id == current_user.id,
            )
            .first()
        )
        if not owned:
            raise HTTPException(status_code=404, detail="Notification not found")
        # Ours, but already SENT or FAILED. The caller wanted it not-pending and it is
        # not pending, so this is a no-op success rather than an error.
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search")
def global_search(
    q: str = Query(..., min_length=2),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    results: list[dict[str, Any]] = []
    term = f"%{q}%"

    if current_user.role == models.UserRole.ADMIN:
        # Users
        users = db.query(models.User).filter(
            models.User.role != models.UserRole.ADMIN,
            models.User.username.ilike(term) | models.User.email.ilike(term),
        ).limit(20).all()
        for u in users:
            results.append({"type": "user", "id": u.id, "name": u.username})

        # Kindergartens
        kgs = db.query(models.Kindergarten).filter(
            models.Kindergarten.name_ar.ilike(term)
            | models.Kindergarten.name_en.ilike(term)
        ).limit(20).all()
        for kg in kgs:
            results.append({"type": "kindergarten", "id": kg.id, "name": kg.name_en or kg.name_ar})

        # Children
        children = (
            db.query(models.Child)
            .filter(
                models.Child.first_name.ilike(term)
                | models.Child.last_name.ilike(term)
            )
            .limit(20)
            .all()
        )
        for c in children:
            results.append({"type": "child", "id": c.id, "name": f"{c.first_name} {c.last_name}"})

    elif current_user.role == models.UserRole.MANAGER:
        kg_id = current_user.kindergarten_id
        children = (
            db.query(models.Child)
            .join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id,
            )
            .filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                models.Child.first_name.ilike(term)
                | models.Child.last_name.ilike(term),
            )
            .limit(20)
            .all()
        )
        for c in children:
            results.append({"type": "child", "id": c.id, "name": f"{c.first_name} {c.last_name}"})

    else:
        # Parent — own children only
        profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id,
            models.ParentProfile.deleted_at.is_(None),
        ).first()
        if profile:
            children = (
                db.query(models.Child)
                .filter(
                    models.Child.parent_id == profile.id,
                    models.Child.first_name.ilike(term)
                    | models.Child.last_name.ilike(term),
                )
                .limit(20)
                .all()
            )
            for c in children:
                results.append({"type": "child", "id": c.id, "name": f"{c.first_name} {c.last_name}"})

    return {"results": results}


# ---------------------------------------------------------------------------
# Communication stats
# ---------------------------------------------------------------------------

@router.get("/communication/stats")
def communication_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kg_id = current_user.kindergarten_id

    msg_q = db.query(models.Message)
    if kg_id:
        msg_q = msg_q.filter(models.Message.kindergarten_id == kg_id)
    unread_messages = msg_q.count()

    recent_activity: list[dict] = []

    events_q = db.query(models.Event)
    if kg_id:
        events_q = events_q.filter(models.Event.kindergarten_id == kg_id)
    for e in events_q.order_by(models.Event.start_at.desc()).limit(5).all():
        recent_activity.append({
            "type": "event",
            "title": e.title,
            "at": e.start_at.isoformat() if e.start_at else None,
        })

    surveys_q = db.query(models.Survey)
    if kg_id:
        surveys_q = surveys_q.filter(models.Survey.kindergarten_id == kg_id)
    for s in surveys_q.order_by(models.Survey.created_at.desc()).limit(5).all():
        recent_activity.append({
            "type": "survey",
            "title": s.title,
            "at": s.created_at.isoformat() if s.created_at else None,
        })

    return {
        "unread_messages": unread_messages,
        "recent_activity": recent_activity,
    }


# ---------------------------------------------------------------------------
# Kindergartens — KPI snapshot
# ---------------------------------------------------------------------------

@router.get("/kindergartens/{kindergarten_id}/kpi-snapshot")
def kpi_snapshot(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied to this kindergarten")

    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    total_capacity = (
        db.query(func.sum(models.Class.capacity_total))
        .filter(models.Class.kindergarten_id == kindergarten_id, models.Class.is_active.is_(True))
        .scalar()
        or 0
    )
    enrolled = (
        db.query(func.count(models.EnrollmentApplication.id))
        .filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .scalar()
        or 0
    )

    occupancy_pct = round((enrolled / total_capacity * 100), 1) if total_capacity else 0.0

    return {
        "kindergarten_id": kindergarten_id,
        "occupancy_pct": occupancy_pct,
        "total_capacity": total_capacity,
        "enrolled": enrolled,
    }


# ---------------------------------------------------------------------------
# Classes — children and supervisors
# ---------------------------------------------------------------------------

@router.get("/classes/{class_id}/children")
def get_class_children(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cls = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != cls.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied to this class")

    enrollments = (
        db.query(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.class_id == class_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .all()
    )
    child_ids = [e.child_id for e in enrollments if e.child_id]
    child_map = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}

    children = []
    for e in enrollments:
        child = child_map.get(e.child_id)
        if child:
            children.append({
                "child_id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
                "enrollment_id": e.id,
            })

    return {"children": children}


@router.get("/classes/{class_id}/supervisors")
def get_class_supervisors(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cls = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != cls.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied to this class")

    assignments = (
        db.query(models.SupervisorAssignment)
        .filter(
            models.SupervisorAssignment.class_id == class_id,
            models.SupervisorAssignment.deleted_at.is_(None),
        )
        .all()
    )
    sup_ids = [a.supervisor_id for a in assignments if a.supervisor_id]
    sup_map = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(sup_ids)).all()}

    supervisors = []
    for a in assignments:
        sup = sup_map.get(a.supervisor_id)
        if sup:
            supervisors.append({
                "user_id": sup.id,
                "username": sup.username,
                "email": sup.email,
                "is_primary": a.is_primary,
                "start_date": a.start_date.isoformat() if a.start_date else None,
            })

    return {"supervisors": supervisors}




# ---------------------------------------------------------------------------
# Reports (DailyReports)
# ---------------------------------------------------------------------------

@router.get("/reports")
def get_reports(
    child_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id,
            models.ParentProfile.deleted_at.is_(None),
        ).first()
        if not profile:
            return {"reports": []}

        # Get children belonging to this parent
        children = db.query(models.Child).filter(models.Child.parent_id == profile.id).all()
        child_ids = [c.id for c in children]
        if child_id and child_id in child_ids:
            child_ids = [child_id]
        elif child_id:
            return {"reports": []}

        q = db.query(models.DailyReport).filter(models.DailyReport.child_id.in_(child_ids))
    else:
        q = db.query(models.DailyReport)
        if child_id:
            q = q.filter(models.DailyReport.child_id == child_id)

    reports = q.order_by(models.DailyReport.date.desc()).limit(100).all()
    return {
        "reports": [
            {
                "id": r.id,
                "child_id": r.child_id,
                "date": r.date.isoformat() if r.date else None,
                "status": r.status.value if r.status else None,
            }
            for r in reports
        ]
    }


# ---------------------------------------------------------------------------
# Attendance — mark (single) and bulk
# ---------------------------------------------------------------------------

@router.post("/attendance")
def mark_attendance(
    body: AttendanceMarkBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validators.validate_supervisor_role(current_user)

    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == body.child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    ).first()

    if not enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")

    today = today_amman()

    if body.status.upper() == "PRESENT":
        attendance = models.AttendanceLog(
            child_id=body.child_id,
            class_id=enrollment.class_id,
            date=today,
            status=models.AttendanceStatus.PRESENT,
            check_in_at=datetime.now(_JORDAN_TZ),
            recorded_by=current_user.id,
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        return {
            "id": attendance.id,
            "child_id": attendance.child_id,
            "date": attendance.date.isoformat(),
            "check_in_at": attendance.check_in_at.isoformat() if attendance.check_in_at else None,
            "check_out_at": None,
        }
    else:
        # ABSENT
        attendance = models.AttendanceLog(
            child_id=body.child_id,
            class_id=enrollment.class_id,
            date=today,
            status=models.AttendanceStatus.ABSENT,
            recorded_by=current_user.id,
        )
        db.add(attendance)
        db.commit()
        return {"status": "absent", "child_id": body.child_id}


@router.post("/attendance/bulk")
def bulk_attendance(
    body: BulkAttendanceBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validators.validate_supervisor_role(current_user)

    updated = 0
    errors: list[dict] = []
    today = today_amman()
    _now = datetime.now(_JORDAN_TZ)

    try:
        status_val = models.AttendanceStatus(body.status.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")

    # Batch-fetch enrollments for all child_ids to avoid N queries
    enrollment_map = {
        e.child_id: e
        for e in db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id.in_(body.child_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).all()
    }

    for cid in body.child_ids:
        enrollment = enrollment_map.get(cid)
        if not enrollment:
            errors.append({"child_id": cid, "error": "No active enrollment"})
            continue

        attendance = models.AttendanceLog(
            child_id=cid,
            class_id=enrollment.class_id,
            date=today,
            status=status_val,
            check_in_at=_now if status_val == models.AttendanceStatus.PRESENT else None,
            recorded_by=current_user.id,
        )
        db.add(attendance)
        updated += 1

    db.commit()
    return {"updated": updated, "errors": errors}


# ---------------------------------------------------------------------------
# Attendance — absence requests (new path)
# ---------------------------------------------------------------------------

@router.post("/attendance/absence-requests", status_code=status.HTTP_201_CREATED)
def create_absence_request(
    body: AbsenceRequestBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parents only")

    if body.to_date < body.from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")

    # This handler writes the same absence_requests row as POST /api/absence-requests,
    # and the same approve loop consumes it — one SELECT + one INSERT per day in the
    # span. Bounding only the other door left this one open: to_date=9999-12-31 was
    # accepted here (201) while the bounded path rejected it (422), and approving it
    # would run ~2.9M statements. Same constant, not a second copy, so the two doors
    # cannot drift apart.
    span_days = (body.to_date - body.from_date).days + 1
    if span_days > MAX_ABSENCE_SPAN_DAYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"absence span must not exceed {MAX_ABSENCE_SPAN_DAYS} days "
                f"(requested {span_days})"
            ),
        )

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id,
        models.ParentProfile.deleted_at.is_(None),
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    child = db.query(models.Child).filter(
        models.Child.id == body.child_id,
        models.Child.parent_id == profile.id,
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == body.child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")

    # Use raw SQL for overlap — avoids SQLAlchemy enum error on raw 'PENDING' stored by tests
    overlap_count = db.execute(
        text(
            "SELECT COUNT(*) FROM absence_requests "
            "WHERE child_id = :cid "
            "AND start_date <= :to_d "
            "AND end_date >= :from_d "
            "AND status NOT IN ('REJECTED', 'CANCELLED')"
        ),
        {"cid": body.child_id, "to_d": body.to_date, "from_d": body.from_date},
    ).scalar() or 0
    if overlap_count > 0:
        raise HTTPException(status_code=409, detail="Overlapping absence request exists")

    req = models.AbsenceRequest(
        parent_id=profile.id,
        child_id=body.child_id,
        kindergarten_id=enrollment.kindergarten_id,
        class_id=enrollment.class_id,
        start_date=body.from_date,
        end_date=body.to_date,
        reason=body.reason,
        status=models.AbsenceRequestStatus.SUBMITTED,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"id": req.id, "status": "pending"}


# ---------------------------------------------------------------------------
# Daily reports — supervisor's enrolled children
# ---------------------------------------------------------------------------

@router.get("/daily-reports/supervisor/my-children")
def supervisor_my_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Supervisor role required")

    assignments = (
        db.query(models.SupervisorAssignment)
        .filter(
            models.SupervisorAssignment.supervisor_id == current_user.id,
            models.SupervisorAssignment.deleted_at.is_(None),
        )
        .all()
    )
    class_ids = [a.class_id for a in assignments]
    if not class_ids:
        return {"children": []}

    enrollments = (
        db.query(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .all()
    )

    child_ids = [e.child_id for e in enrollments if e.child_id]
    child_map = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}

    children = []
    for e in enrollments:
        child = child_map.get(e.child_id)
        if child:
            children.append({
                "child_id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "class_id": e.class_id,
            })

    return {"children": children}


# ---------------------------------------------------------------------------
# Curriculum — observations
# ---------------------------------------------------------------------------

@router.get("/curriculum/observations")
def list_observations(
    child_id: Optional[int] = None,
    class_id: Optional[int] = None,
    domain: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Observation)

    if current_user.role == models.UserRole.PARENT:
        profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id,
            models.ParentProfile.deleted_at.is_(None),
        ).first()
        if not profile:
            return {"observations": []}
        child_ids = [
            c.id for c in db.query(models.Child).filter(models.Child.parent_id == profile.id).all()
        ]
        if not child_ids:
            return {"observations": []}
        q = q.filter(models.Observation.child_id.in_(child_ids))

    elif current_user.role == models.UserRole.MANAGER:
        kg_id = current_user.kindergarten_id
        enrolled_child_ids = [
            e.child_id for e in db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            ).all()
        ]
        q = q.filter(models.Observation.child_id.in_(enrolled_child_ids))

    if child_id is not None:
        q = q.filter(models.Observation.child_id == child_id)

    if class_id is not None:
        enrolled_in_class = [
            e.child_id for e in db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.class_id == class_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            ).all()
        ]
        q = q.filter(models.Observation.child_id.in_(enrolled_in_class))

    if domain is not None:
        domain_upper = domain.upper()
        if domain_upper == "SOCIAL":
            domain_upper = "SOCIAL_EMOTIONAL"
        try:
            domain_val = models.LearningDomain(domain_upper)
            q = q.filter(models.Observation.domain == domain_val)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")

    observations = q.order_by(models.Observation.observed_at.desc()).limit(200).all()
    return {
        "observations": [
            {
                "id": o.id,
                "child_id": o.child_id,
                "domain": o.domain.value if o.domain else None,
                "mastery_level": o.mastery_level.value if o.mastery_level else None,
                "observation_text": o.observation_text,
                "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            }
            for o in observations
        ]
    }


# ---------------------------------------------------------------------------
# Curriculum — outcomes
# ---------------------------------------------------------------------------

@router.get("/curriculum/outcomes")
def list_curriculum_outcomes(
    domain: Optional[str] = None,
    age_band_min: Optional[int] = None,
    age_band_max: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.CurriculumOutcome)

    if domain is not None:
        domain_upper = domain.upper()
        if domain_upper == "SOCIAL":
            domain_upper = "SOCIAL_EMOTIONAL"
        try:
            domain_val = models.LearningDomain(domain_upper)
            q = q.filter(models.CurriculumOutcome.domain == domain_val)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")

    if age_band_min is not None:
        # outcome overlaps: outcome.max >= query.min
        q = q.filter(models.CurriculumOutcome.age_band_max_months >= age_band_min)

    if age_band_max is not None:
        # outcome overlaps: outcome.min <= query.max
        q = q.filter(models.CurriculumOutcome.age_band_min_months <= age_band_max)

    outcomes = q.order_by(models.CurriculumOutcome.age_band_min_months).all()
    return {
        "outcomes": [
            {
                "id": o.id,
                "domain": o.domain.value if o.domain else None,
                "age_band_min_months": o.age_band_min_months,
                "age_band_max_months": o.age_band_max_months,
                "indicator_code": o.indicator_code,
                "description": o.description,
            }
            for o in outcomes
        ]
    }


@router.get("/curriculum/outcomes/{outcome_id}")
def get_curriculum_outcome(
    outcome_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outcome = db.query(models.CurriculumOutcome).filter(models.CurriculumOutcome.id == outcome_id).first()
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return {
        "id": outcome.id,
        "domain": outcome.domain.value if outcome.domain else None,
        "age_band_min_months": outcome.age_band_min_months,
        "age_band_max_months": outcome.age_band_max_months,
        "indicator_code": outcome.indicator_code,
        "description": outcome.description,
    }


# ---------------------------------------------------------------------------
# Manager — corresponding guardian assignment
# ---------------------------------------------------------------------------

@router.get("/manager/pending-corresponding")
def get_pending_corresponding(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validators.validate_manager_role(current_user)

    kg_id = current_user.kindergarten_id

    enrolled_child_ids = [
        e.child_id for e in db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).all()
    ] if kg_id else []

    children = (
        db.query(models.Child)
        .filter(
            models.Child.id.in_(enrolled_child_ids),
            models.Child.corresponding_type == "PENDING_MANAGER",
        )
        .all()
    ) if enrolled_child_ids else []

    return {
        "count": len(children),
        "children": [
            {
                "child_id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "corresponding_pending_reason": c.corresponding_pending_reason,
            }
            for c in children
        ],
    }


@router.patch("/children/{child_id}/corresponding")
def assign_corresponding(
    child_id: int,
    body: CorrespondingAssignBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validators.validate_manager_role(current_user)

    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    if child.corresponding_type != "PENDING_MANAGER":
        raise HTTPException(status_code=400, detail="Child is not pending corresponding guardian assignment")

    child.corresponding_type = "GUARDIAN"
    child.corresponding_phone = body.contact_phone
    child.corresponding_pending_reason = None
    db.commit()
    db.refresh(child)

    return {
        "child_id": child.id,
        "corresponding_type": child.corresponding_type,
        "corresponding_phone": child.corresponding_phone,
    }
