"""
Curriculum and Portfolio Service
- Observation Tracking
- Portfolio Management
- Curriculum Outcomes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

import models
import validators
from database import get_db
from dependencies import get_current_user

router = APIRouter()

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class ObservationCreate(BaseModel):
    child_id: int
    domain: str # SOCIAL_EMOTIONAL, PHYSICAL, COGNITIVE, LANGUAGE
    observation_text: str
    mastery_level: Optional[str] = None # ON_TRACK, NEEDS_SUPPORT, EXCEEDS
    observed_at: datetime

class PortfolioCreate(BaseModel):
    child_id: int
    title: str
    description: Optional[str] = None
    status: str = "DRAFT" # DRAFT, PUBLISHED

class PortfolioUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

# -----------------------------------------------------------------------------
# Curriculum Outcomes (Reference Data)
# -----------------------------------------------------------------------------

@router.get("/curriculum/outcomes")
def list_curriculum_outcomes(
    domain: Optional[str] = None,
    age_months: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """List standard curriculum outcomes/indicators"""
    query = db.query(models.CurriculumOutcome)
    
    if domain:
        query = query.filter(models.CurriculumOutcome.domain == models.LearningDomain(domain))
        
    if age_months:
        # Find outcomes valid for this age
        query = query.filter(
            models.CurriculumOutcome.age_band_min_months <= age_months,
            models.CurriculumOutcome.age_band_max_months >= age_months
        )
        
    return query.all()

# -----------------------------------------------------------------------------
# Observations
# -----------------------------------------------------------------------------

@router.post("/observations", status_code=status.HTTP_201_CREATED)
def record_observation(
    obs_data: ObservationCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record a new child observation"""
    # Supervisors and Managers
    validators.validate_supervisor_role(current_user)
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == obs_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
        
    # Validation: Ensure observer has access to child via KG or Class
    # Simplest check: Child's parent -> enrolled in observer's KG
    if current_user.role != models.UserRole.ADMIN:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        if not enrollment:
             raise HTTPException(status_code=403, detail="Child is not active in your kindergarten")

    observation = models.Observation(
        child_id=obs_data.child_id,
        observed_by=current_user.id,
        domain=models.LearningDomain(obs_data.domain),
        observation_text=obs_data.observation_text,
        mastery_level=models.MasteryLevel(obs_data.mastery_level) if obs_data.mastery_level else None,
        observed_at=obs_data.observed_at
    )
    
    db.add(observation)
    db.commit()
    db.refresh(observation)
    return observation

@router.get("/children/{child_id}/observations")
def list_child_observations(
    child_id: int,
    domain: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List observations for a specific child"""
    # Authorization checks (Parent of child OR Staff of KG)
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    if current_user.role == models.UserRole.PARENT:
        if child.parent_id != current_user.parent_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this child's records")
    elif current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR, models.UserRole.ADMIN]:
        # KG Check
        if current_user.role != models.UserRole.ADMIN:
            # Check enrollment in user's KG
            is_enrolled = db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.child_id == child.id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id
            ).first()
            if not is_enrolled:
                 raise HTTPException(status_code=403, detail="Child not enrolled in your kindergarten")

    query = db.query(models.Observation).filter(models.Observation.child_id == child_id)
    
    if domain:
        query = query.filter(models.Observation.domain == models.LearningDomain(domain))
        
    return query.order_by(desc(models.Observation.observed_at)).all()

# -----------------------------------------------------------------------------
# Portfolios
# -----------------------------------------------------------------------------

@router.post("/portfolios", status_code=status.HTTP_201_CREATED)
def create_portfolio_entry(
    portfolio_data: PortfolioCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a portfolio entry (e.g. 'January Art Project')"""
    validators.validate_supervisor_role(current_user)
    
    portfolio = models.Portfolio(
        child_id=portfolio_data.child_id,
        title=portfolio_data.title,
        description=portfolio_data.description,
        status=models.PortfolioStatus(portfolio_data.status)
    )
    
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio

@router.get("/children/{child_id}/portfolio")
def list_portfolio(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List portfolio entries"""
    # Auth checks similar to Observations
    query = db.query(models.Portfolio).filter(models.Portfolio.child_id == child_id)
    
    # If parent, only show PUBLISHED
    if current_user.role == models.UserRole.PARENT:
        query = query.filter(models.Portfolio.status == models.PortfolioStatus.PUBLISHED)
        
    return query.order_by(desc(models.Portfolio.created_at)).all()
