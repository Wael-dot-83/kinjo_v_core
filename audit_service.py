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
    parsed_date = None
    if date:
        try:
            from datetime import date as date_type
            parsed_date = date_type.fromisoformat(date)
        except (ValueError, TypeError):
            parsed_date = None

    logs_with_users = (
        db.query(models.AuditLog, models.User.username)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
    )

    if action:
        logs_with_users = logs_with_users.filter(models.AuditLog.action == action)
    if entity_type:
        logs_with_users = logs_with_users.filter(models.AuditLog.entity_type == entity_type)
    if parsed_date:
        from sqlalchemy import func
        logs_with_users = logs_with_users.filter(func.date(models.AuditLog.created_at) == parsed_date)
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
        try:
            days = int(period)
            cutoff = datetime.now(_JORDAN_TZ).replace(tzinfo=None) - timedelta(days=days)
            query = query.filter(models.AuditLog.created_at >= cutoff)
        except ValueError:
            pass

    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))
    if date:
        try:
            from sqlalchemy import func
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(func.date(models.AuditLog.created_at) == parsed_date)
        except (ValueError, TypeError):
            pass

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
