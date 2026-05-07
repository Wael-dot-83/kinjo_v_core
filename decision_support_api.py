"""
Decision Support API - stub module
Provides minimal router so the application can start.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/decision-support", tags=["Decision Support"])
