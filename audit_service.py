from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today
import csv
import io
import json

import models
from database import get_db
from dependencies import get_current_user
from models import UserRole
from audit_actions import AuditAction
from admin_security import log_audit_event
from csv_utils import escape_csv_formula
from export_service import export_service

router = APIRouter()
admin_router = APIRouter()


def _require_admin(current_user: models.User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")


def _jordan_day_bounds(date_str: str) -> tuple[datetime, datetime]:
    """Half-open UTC bounds [start, end) for a Jordan calendar day.

    Shared by the list and the export because they are driven by the SAME
    #dateFilter input: when each carried its own copy they drifted apart, and
    the table and the exported file disagreed about what happened on a given
    day — on an audit trail, an evidentiary problem.

    Why not func.date(created_at) == parsed: created_at is stored UTC, so an
    event at 01:30 Jordan on D is 22:30 UTC on D-1 and would be filed under the
    wrong day. A range also uses idx_audit_logs_created_at, which wrapping the
    column in a function defeats.

    The bounds are timezone-AWARE on purpose. created_at is timestamptz on
    PostgreSQL, where a naive bound is interpreted in the server's session
    TimeZone rather than UTC. Verified against the real PG container: under
    `SET TIME ZONE 'America/New_York'` naive bounds returned 0 rows for a row
    inside the Jordan day, while aware bounds are correct under Etc/UTC,
    Asia/Amman and America/New_York alike.

    Raises 422 rather than dropping an unparseable filter: silently widening a
    filter returns rows the caller did not ask for with a 200, and the export's
    audit record would still claim the filter was applied.
    """
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid date filter; expected YYYY-MM-DD.",
        )
    day_start_utc = datetime.combine(
        parsed_date, datetime.min.time(), tzinfo=_JORDAN_TZ
    ).astimezone(timezone.utc)
    return day_start_utc, day_start_utc + timedelta(days=1)


def _list_audit_logs(
    *,
    page: int,
    limit: int,
    action: Optional[str],
    entity_type: Optional[str],
    user: Optional[str],
    date: Optional[str],
    current_user: models.User,
    db: Session,
):
    _require_admin(current_user)

    action = action if action else None
    entity_type = entity_type if entity_type else None
    user = user if user else None
    day_bounds = _jordan_day_bounds(date) if date else None

    logs_with_users = (
        db.query(models.AuditLog, models.User.username)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
    )

    if action:
        logs_with_users = logs_with_users.filter(models.AuditLog.action == action)
    if entity_type:
        logs_with_users = logs_with_users.filter(models.AuditLog.entity_type == entity_type)
    if day_bounds:
        logs_with_users = logs_with_users.filter(
            models.AuditLog.created_at >= day_bounds[0],
            models.AuditLog.created_at < day_bounds[1],
        )
    if user:
        logs_with_users = logs_with_users.filter(models.User.username.ilike(f"%{user}%"))

    logs_with_users = logs_with_users.order_by(desc(models.AuditLog.created_at))
    total_records = logs_with_users.count()
    total_pages = (total_records + limit - 1) // limit
    offset = (page - 1) * limit
    paged_data = logs_with_users.offset(offset).limit(limit).all()

    results = []
    for log, username in paged_data:
        results.append({
            "id": log.id,
            "created_at": log.created_at,
            "user_id": log.user_id,
            "user_name": username or "System/Deleted",
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "details": log.details,
            "ip_address": log.ip_address
        })

    return {
        "logs": results,
        "total": total_records,
        "page": page,
        "total_pages": total_pages
    }


def _export_audit_logs(
    *,
    format: str,
    period: str,
    action: Optional[str],
    entity_type: Optional[str],
    user: Optional[str],
    date: Optional[str],
    current_user: models.User,
    db: Session,
):
    _require_admin(current_user)

    query = db.query(models.AuditLog, models.User.username).outerjoin(
        models.User, models.AuditLog.user_id == models.User.id
    )

    if period != "all":
        # Same reasoning as the date filter: swallowing this returned every
        # period with a 200 while the audit record below still wrote
        # period=<garbage>. The UI select only ever sends 7/30/90/365/all.
        try:
            days = int(period)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="Invalid period; expected a number of days or 'all'.",
            )
        # Aware UTC. The old naive Jordan wall-clock cutoff
        # (datetime.now(_JORDAN_TZ).replace(tzinfo=None)) was compared against
        # UTC-stored created_at, shifting the window by 3 hours.
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(models.AuditLog.created_at >= cutoff)

    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))
    if date:
        day_start_utc, day_end_utc = _jordan_day_bounds(date)
        query = query.filter(
            models.AuditLog.created_at >= day_start_utc,
            models.AuditLog.created_at < day_end_utc,
        )

    query = query.order_by(desc(models.AuditLog.created_at))
    data = query.limit(5000).all()

    log_audit_event(
        db=db,
        action=AuditAction.AUDIT_LOG_EXPORT,
        actor=current_user,
        target_type="AuditLog",
        metadata={
            "format": format,
            "period": period,
            "action_filter": action,
            "entity_type_filter": entity_type,
            "user_filter": user,
            "date_filter": date,
            "count": len(data),
        },
        sensitivity_level=2,
    )

    if format == "json":
        export_data = []
        for log, username in data:
            export_data.append({
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "user": username or "Unknown",
                "action": log.action,
                "entity": log.entity_type,
                "details": log.details,
                "ip": log.ip_address
            })
        return Response(
            content=json.dumps(export_data, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{_today()}.json"}
        )

    headers = ["Timestamp", "User", "Action", "Entity Type", "Details", "IP Address"]
    rows = []
    for log, username in data:
        rows.append([
            log.created_at,
            username or "Unknown",
            log.action,
            log.entity_type,
            log.details,
            log.ip_address
        ])

    return export_service.generate_csv_response(
        headers=headers, 
        data=rows, 
        filename=f"audit_logs_{_today()}.csv"
    )


def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    date: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _list_audit_logs(
        page=page,
        limit=limit,
        action=action,
        entity_type=entity_type,
        user=user,
        date=date,
        current_user=current_user,
        db=db,
    )


def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    period: str = Query("7"),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    date: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _export_audit_logs(
        format=format,
        period=period,
        action=action,
        entity_type=entity_type,
        user=user,
        date=date,
        current_user=current_user,
        db=db,
    )

admin_router.add_api_route("/audit-logs", list_audit_logs, methods=["GET"])
admin_router.add_api_route("/audit-logs/export", export_audit_logs, methods=["GET"])

# Legacy aliases at /api/audit-logs — part of the public API contract
# (test_gws_round3 asserts both alias sets stay registered).
router.add_api_route("/audit-logs", list_audit_logs, methods=["GET"])
router.add_api_route("/audit-logs/export", export_audit_logs, methods=["GET"])
