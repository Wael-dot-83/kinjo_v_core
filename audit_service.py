from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today


MAX_AUDIT_EXPORT_ROWS = 5000
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
        # `period` is pattern-validated at the Query (see export_audit_logs), so
        # by here it is 'all' or 1-5 ASCII digits. int() alone was not enough:
        #   '-5'        -> timedelta(days=-5) -> a cutoff in the FUTURE -> zero
        #                  rows with a 200, while the audit record wrote
        #                  period='-5'. The same silent lie as a dropped filter.
        #   '999999999' -> OverflowError ("date value out of range") -> 500.
        #   ' 7 ', '+7', '٧' -> silently accepted by int(), which is not the
        #                  "number of days" contract the error message states.
        days = int(period)
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

    # Fetch one sentinel row in the same ordered statement used for the export.
    # COUNT followed by an unbounded SELECT had both a TOCTOU window (new rows
    # could arrive between statements) and twice the database work.
    data = (
        query.order_by(
            desc(models.AuditLog.created_at),
            desc(models.AuditLog.id),
        )
        .limit(MAX_AUDIT_EXPORT_ROWS + 1)
        .all()
    )
    if len(data) > MAX_AUDIT_EXPORT_ROWS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Audit export would return more than {MAX_AUDIT_EXPORT_ROWS:,} rows. "
                "Apply period or field filters to narrow the export."
            ),
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
        response = Response(
            content=json.dumps(export_data, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{_today()}.json"}
        )
    else:
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

        response = export_service.generate_csv_response(
            headers=headers,
            data=rows,
            filename=f"audit_logs_{_today()}.csv"
        )

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
    # Export/read events have no business mutation to share a transaction with,
    # but they still need an explicit durability boundary.  get_db() closes the
    # session after the response and would otherwise roll this flushed row back.
    db.commit()
    return response


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
    # 'all' or 1-5 ASCII digits, validated here rather than in the handler so a
    # bad value is a 422 before any query runs — matching `format` above.
    # Explicit [0-9] because Python's \d also matches Arabic-Indic digits.
    # Excludes '-5' (a negative shifts the cutoff into the FUTURE -> zero rows
    # with a 200) and '999999999' (timedelta OverflowError -> 500). The 5-digit
    # cap is ~273 years, well past any real retention window; 'all' is the
    # supported way to ask for everything.
    period: str = Query("7", pattern="^(all|[0-9]{1,5})$"),
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
