"""
Portfolio domain endpoints
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timezone, timedelta

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Portfolio"])


class PortfolioCreateRequest(BaseModel):
    child_id: int
    title: str
    description: Optional[str] = None
    status: Optional[str] = None  # Allow status to be provided


class PortfolioResponse(BaseModel):
    id: int
    child_id: int
    title: str
    description: Optional[str]
    status: str
    published_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


@router.get("/portfolios")
def list_portfolios(
    child_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List portfolio entries (filtered by role and status)"""
    query = db.query(models.Portfolio)

    # Parents can only see published portfolios for their own children
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()

        if not parent_profile:
            return {"portfolios": []}

        # Get child IDs
        child_ids = [c.id for c in db.query(models.Child).filter(models.Child.parent_id == parent_profile.id).all()]

        query = query.filter(
            models.Portfolio.child_id.in_(child_ids), models.Portfolio.status == models.PortfolioStatus.PUBLISHED
        )
    else:
        # Staff can see all portfolios in their kindergarten
        if child_id:
            query = query.filter(models.Portfolio.child_id == child_id)

        if status_filter:
            try:
                status_enum = models.PortfolioStatus(status_filter.upper())
                query = query.filter(models.Portfolio.status == status_enum)
            except ValueError:
                logger.warning("INVALID_FILTER status_filter=%r ignored — not a valid PortfolioStatus", status_filter)

    portfolios = query.order_by(models.Portfolio.created_at.desc()).all()

    return {
        "portfolios": [
            {
                "id": p.id,
                "child_id": p.child_id,
                "title": p.title,
                "description": p.description,
                "status": p.status.value,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in portfolios
        ]
    }


@router.get("/children/{child_id}/portfolio")
def get_child_portfolio(
    child_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all portfolio entries for a specific child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Parents can only see their own child's published portfolios
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()

        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")

        portfolios = (
            db.query(models.Portfolio)
            .filter(models.Portfolio.child_id == child_id, models.Portfolio.status == models.PortfolioStatus.PUBLISHED)
            .order_by(models.Portfolio.created_at.desc())
            .all()
        )
    else:
        # This branch read "Staff can see all portfolios" and did precisely
        # that, across tenants: a manager bound to one kindergarten could fetch
        # the portfolio of a child enrolled in another. Verified against the
        # seed data — manager1 (kindergarten 1) retrieved child 7's portfolio,
        # a child enrolled in kindergarten 3, title and all.
        #
        # Same guard get_child_health_alerts already uses further down this
        # file, so the two child-scoped reads now agree. Admins stay
        # unrestricted; every other staff role must hold an active enrolment
        # for this child in their own kindergarten.
        if current_user.role != models.UserRole.ADMIN:
            enrollment = (
                db.query(models.EnrollmentApplication.id)
                .filter(
                    models.EnrollmentApplication.child_id == child_id,
                    models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                    models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
                )
                .first()
            )
            # 404, matching api/children.py::_authorize_child_access and
            # get_child_health_alerts below. Every child-scoped read in this
            # module refuses the same way, so an out-of-scope child cannot be
            # told apart from one that does not exist.
            if not enrollment:
                raise HTTPException(status_code=404, detail="Child not found")

        portfolios = (
            db.query(models.Portfolio)
            .filter(models.Portfolio.child_id == child_id)
            .order_by(models.Portfolio.created_at.desc())
            .all()
        )

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": p.id,
            "child_id": p.child_id,
            "title": p.title,
            "description": p.description,
            "status": p.status.value,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in portfolios
    ]


@router.post("/portfolios", status_code=status.HTTP_201_CREATED)
def create_portfolio_entry(
    portfolio_data: PortfolioCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new portfolio entry (Supervisor/Manager only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create portfolio entries")

    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == portfolio_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Accept status from request, default to DRAFT
    status_value = models.PortfolioStatus.DRAFT
    if hasattr(portfolio_data, "status") and portfolio_data.status:
        try:
            status_value = models.PortfolioStatus(portfolio_data.status.upper())
        except (ValueError, AttributeError):
            logger.warning("INVALID_STATUS status=%r — defaulting to DRAFT", portfolio_data.status)

    portfolio = models.Portfolio(
        child_id=portfolio_data.child_id,
        title=portfolio_data.title,
        description=portfolio_data.description,
        status=status_value,
        published_at=datetime.now(_JORDAN_TZ) if status_value == models.PortfolioStatus.PUBLISHED else None,
    )

    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return {
        "id": portfolio.id,
        "child_id": portfolio.child_id,
        "title": portfolio.title,
        "status": portfolio.status.value,
    }


@router.post("/portfolios/{portfolio_id}/publish")
def publish_portfolio_entry(
    portfolio_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Publish a portfolio entry (makes it visible to parents)"""
    validators.validate_manager_role(current_user)

    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Cross-KG scope check: managers cannot publish portfolios outside their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        enrollment = (
            db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id == portfolio.child_id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
            )
            .first()
        )
        if not enrollment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    if portfolio.status == models.PortfolioStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Portfolio already published")

    portfolio.status = models.PortfolioStatus.PUBLISHED
    portfolio.published_at = datetime.now(_JORDAN_TZ)

    db.commit()
    db.refresh(portfolio)

    return {"id": portfolio.id, "status": portfolio.status.value, "published_at": portfolio.published_at.isoformat()}


# ============================================================================
# Health Alerts Endpoints (CRUD)
# ============================================================================


class HealthAlertCreateRequest(BaseModel):
    alert_type: str
    description: str
    severity: str


@router.get("/children/{child_id}/health-alerts")
def get_child_health_alerts(
    child_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all health alerts for a child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Role-based scope enforcement
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.role != models.UserRole.ADMIN:
        # Supervisors and managers are scoped to their own kindergarten
        enrollment = (
            db.query(models.EnrollmentApplication.id)
            .filter(
                models.EnrollmentApplication.child_id == child_id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
            )
            .first()
        )
        # 404, not 403. This scope check was already correct — it was the refusal
        # that leaked: a 403 reading "Child not in your kindergarten scope"
        # confirms the child exists in some other kindergarten, so numeric child
        # IDs could still be walked to map another tenant's roll. That is the
        # enumeration oracle dependencies.ManagerScope calls out ("404, not 403 —
        # do not reveal that another tenant's resource exists") and that
        # tests/test_analytics_tenant_isolation.py exists to prevent.
        #
        # Now identical to api/children.py::_authorize_child_access and to the
        # observations/portfolio reads, so all child-scoped reads answer the same
        # way and an out-of-scope child is indistinguishable from a missing one.
        if not enrollment:
            raise HTTPException(status_code=404, detail="Child not found")

    alerts = (
        db.query(models.HealthAlert)
        .filter(models.HealthAlert.child_id == child_id)
        .order_by(models.HealthAlert.created_at.desc())
        .all()
    )

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": a.id,
            "child_id": a.child_id,
            "alert_type": a.alert_type,
            "description": a.description,
            "severity": a.severity,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/children/{child_id}/health-alerts", status_code=status.HTTP_201_CREATED)
def create_health_alert(
    child_id: int,
    alert_data: HealthAlertCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a health alert for a child (Manager/Supervisor only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create health alerts")

    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Scope Check: Ensure child is active in user's KG
    if current_user.role != models.UserRole.ADMIN:
        enrollment = (
            db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id == child_id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .first()
        )

        if not enrollment:
            raise HTTPException(status_code=403, detail="Child is not active in your kindergarten")

    alert = models.HealthAlert(
        child_id=child_id,
        alert_type=alert_data.alert_type,
        description=alert_data.description,
        severity=alert_data.severity,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    return {"id": alert.id, "child_id": alert.child_id, "alert_type": alert.alert_type, "severity": alert.severity}


@router.delete("/health-alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_health_alert(
    alert_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a health alert (Manager only)"""
    validators.validate_manager_role(current_user)

    alert = db.query(models.HealthAlert).filter(models.HealthAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Health alert not found")

    # Cross-KG scope check: managers cannot delete alerts outside their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        enrollment = (
            db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id == alert.child_id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
            )
            .first()
        )
        if not enrollment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Health alert not found")

    db.delete(alert)
    db.commit()

    return None
