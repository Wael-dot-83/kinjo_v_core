"""Scoped access and date-range helpers for analytics endpoints."""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, Query
from sqlalchemy.orm import Session

import models

_JORDAN_TZ = timezone(timedelta(hours=3))


def get_date_range(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
) -> Tuple[date, date]:
    """Parse date range; default to the last 30 days."""
    if end_date is None:
        end_date = datetime.now(_JORDAN_TZ).date()
    if start_date is None:
        start_date = end_date - timedelta(days=30)
    return start_date, end_date


def allowed_kindergarten_ids(current_user: models.User, db: Session) -> Optional[List[int]]:
    """Return kindergarten IDs the user can access; None means unrestricted (admin)."""
    if current_user.role == models.UserRole.ADMIN:
        return None

    if current_user.role == models.UserRole.MANAGER:
        return [current_user.kindergarten_id] if current_user.kindergarten_id else []

    if current_user.role == models.UserRole.SUPERVISOR:
        assigned = (
            db.query(models.Kindergarten.id)
            .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
            .join(models.SupervisorAssignment, models.SupervisorAssignment.class_id == models.Class.id)
            .filter(models.SupervisorAssignment.supervisor_id == current_user.id)
            .distinct()
            .all()
        )
        ids = {kg_id for (kg_id,) in assigned}
        supervisor_gov = getattr(current_user, "governorate", None)
        if supervisor_gov:
            gov_rows = (
                db.query(models.Kindergarten.id)
                .filter(
                    models.Kindergarten.governorate == supervisor_gov,
                    models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                )
                .all()
            )
            ids.update({kg_id for (kg_id,) in gov_rows})
        return list(ids)

    return []


def kg_ids_for_governorate(db: Session, governorate: Optional[str]) -> Optional[List[int]]:
    """Return active kindergarten IDs for a governorate; None means no governorate filter.

    Alias-aware: a drill-down value in any accepted form (stable key "amman",
    canonical name "العاصمة", or a legacy/bookmarked form "عمان"/"Amman") matches
    rows however the governorate is stored, so old and new query values both resolve.
    """
    if not governorate:
        return None
    from services.jordan_locations import governorate_query_aliases
    match_values = governorate_query_aliases(governorate) or [governorate]
    rows = (
        db.query(models.Kindergarten.id)
        .filter(
            models.Kindergarten.governorate.in_(match_values),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        )
        .all()
    )
    return [kg_id for (kg_id,) in rows]


def allowed_governorates(current_user: models.User, db: Session) -> Optional[List[str]]:
    """Return governorates the user can access; None means unrestricted (admin)."""
    if current_user.role == models.UserRole.ADMIN:
        return None

    governorates = set()
    kg_ids = allowed_kindergarten_ids(current_user, db) or []
    if kg_ids:
        rows = (
            db.query(models.Kindergarten.governorate)
            .filter(
                models.Kindergarten.id.in_(kg_ids),
                models.Kindergarten.governorate.isnot(None),
            )
            .distinct()
            .all()
        )
        governorates.update(value for (value,) in rows if value)

    supervisor_gov = getattr(current_user, "governorate", None)
    if supervisor_gov:
        governorates.add(supervisor_gov)
    return list(governorates)


def enforce_kindergarten_scope(
    current_user: models.User,
    requested_kg_id: Optional[int],
    db: Session,
) -> Optional[int]:
    """Resolve a permitted kindergarten ID for scoped analytics."""
    allowed = allowed_kindergarten_ids(current_user, db)
    if allowed is None:
        return requested_kg_id
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    if requested_kg_id is None:
        if len(allowed) == 1:
            return allowed[0]
        raise HTTPException(status_code=400, detail="Specify kindergarten_id")
    if requested_kg_id not in allowed:
        raise HTTPException(status_code=403, detail="Not allowed to access this kindergarten")
    return requested_kg_id


def can_view_child_detail(current_user: models.User) -> bool:
    """Authorization for the ``analytics:child_detail`` capability.

    Individual-child (CHILD-layer) analytics are privacy_level=restricted PII.
    Per the production-readiness decision this is ADMIN-only; other roles receive
    suppressed values (data_state=suppressed) rather than the underlying numbers.
    Kept as a small predicate so a future permission framework can swap the body
    without touching call sites.
    """
    return current_user.role == models.UserRole.ADMIN


def enforce_analytics_rbac(
    current_user: models.User,
    db: Session,
    dimension_type: Optional[str] = None,
    dimension_id: Optional[str] = None
) -> None:
    """Enforce role and scope boundaries for analytics access."""
    if current_user.role not in {
        models.UserRole.ADMIN,
        models.UserRole.MANAGER,
        models.UserRole.SUPERVISOR,
    }:
        raise HTTPException(status_code=403, detail="Insufficient permissions for analytics access")

    if current_user.role == models.UserRole.ADMIN:
        return

    allowed = allowed_kindergarten_ids(current_user, db) or []
    if not allowed:
        raise HTTPException(status_code=400, detail="User must be assigned to a kindergarten")

    if dimension_type == "KINDERGARTEN" and dimension_id:
        if int(dimension_id) not in allowed:
            raise HTTPException(status_code=403, detail="Access denied: Cannot access other kindergartens")
    elif dimension_type == "CLASS" and dimension_id:
        class_obj = db.query(models.Class).filter(models.Class.id == int(dimension_id)).first()
        if not class_obj or class_obj.kindergarten_id not in allowed:
            raise HTTPException(status_code=403, detail="Access denied: Cannot access classes from other kindergartens")
