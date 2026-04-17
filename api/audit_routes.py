"""
Audit domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Audit"])

@router.get("/audit-logs")
def list_audit_logs(
    page: int = 1,
    limit: int = 25,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    date: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List audit logs (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to view audit logs")

    query = db.query(
        models.AuditLog,
        models.User.username.label('user_name')
    ).outerjoin(
        models.User, models.AuditLog.user_id == models.User.id
    )

    # Apply filters
    if action:
        query = query.filter(models.AuditLog.action == action)

    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)

    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))

    if date:
        query = query.filter(func.date(models.AuditLog.created_at) == date)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * limit
    results = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    # Format results
    logs = []
    for audit_log, user_name in results:
        logs.append({
            "id": audit_log.id,
            "user_id": audit_log.user_id,
            "user_name": user_name,
            "action": audit_log.action,
            "entity_type": audit_log.entity_type,
            "entity_id": audit_log.entity_id,
            "details": audit_log.details,
            "ip_address": audit_log.ip_address,
            "sensitivity_level": audit_log.sensitivity_level,
            "created_at": audit_log.created_at.isoformat() if audit_log.created_at else None
        })

    total_pages = (total + limit - 1) // limit

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


# NOTE: /audit-logs and /audit-logs/export routes live in audit_service.py
# (which includes proper audit logging). Do not duplicate them here.
