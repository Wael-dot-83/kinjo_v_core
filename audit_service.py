from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json

import models
from database import get_db
from dependencies import get_current_user
from models import UserRole
from audit_actions import AuditAction
from admin_security import log_audit_event

router = APIRouter()

@router.get("/audit-logs")
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
    """
    List audit logs with filtering and pagination.
    Only accessible by Admins.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Normalize empty strings to None
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

    query = db.query(models.AuditLog)

    # Apply filters
    if action:
        query = query.filter(models.AuditLog.action == action)
    
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    
    if parsed_date:
        # Filter by specific date (start of day to end of day)
        from sqlalchemy import func as sqlfunc
        query = query.filter(
            sqlfunc.date(models.AuditLog.created_at) == parsed_date
        )

    if user:
        # Join with User table to filter by username
        query = query.join(models.User).filter(
            models.User.username.ilike(f"%{user}%")
        )

    # Sorting
    query = query.order_by(desc(models.AuditLog.created_at))

    # Pagination
    total_records = query.count()
    total_pages = (total_records + limit - 1) // limit
    
    offset = (page - 1) * limit
    logs = query.offset(offset).limit(limit).all()

    # Prepare response with user info enriched
    result = []
    for log in logs:
        user_name = "Unknown"
        if log.user_id:
            # We could join in the main query for efficiency, 
            # but for simple display this is okay or relying on relationship if defined.
            # Model definition didn't show relationship on AuditLog back to User explicitly in provided view,
            # but let's check if we can fetch it.
            # actually AuditLog model in `models.py` has `user_id` FK but NO relationship property defined in the snippet I saw.
            # So I will fetch manually or use a join. List join above suggests I can join.
            # Let's do a quick lookup or just join in the main query to select fields.
            pass

    # Re-writing query to include user username eagerly if possible, or just individual lookups.
    # Given the previous `models.py` view, `AuditLog` didn't seem to have `user` relationship.
    # Let's simple query join to get username.
    
    logs_with_users = (
        db.query(models.AuditLog, models.User.username)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
    )

    # Re-apply filters to this new query object
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
    
    # Pagination execution
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

@router.get("/audit-logs/export")
def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"), # PDF suppressed for now
    period: str = Query("7"), # days
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export audit logs for Admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Base query
    query = db.query(models.AuditLog, models.User.username).outerjoin(models.User, models.AuditLog.user_id == models.User.id)

    # Date Filter
    if period != "all":
        try:
            days = int(period)
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
            query = query.filter(models.AuditLog.created_at >= cutoff)
        except ValueError:
            pass # Ignore invalid period, return all or default

    # Other filters
    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))

    query = query.order_by(desc(models.AuditLog.created_at))
    
    # Limit export to avoid memory issues (e.g., last 5000)
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
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{date.today()}.json"}
        )

    else: # CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "User", "Action", "Entity Type", "Details", "IP Address"])
        
        for log, username in data:
            writer.writerow([
                log.created_at,
                username or "Unknown",
                log.action,
                log.entity_type,
                log.details,
                log.ip_address
            ])
            
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{date.today()}.csv"}
        )
