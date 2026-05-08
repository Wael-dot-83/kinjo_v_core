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

# All curriculum endpoints (observations, portfolios, outcomes) are implemented
# with full validation in missing_endpoints.py, which is registered first.
# This router is kept to satisfy the import in main.py.
