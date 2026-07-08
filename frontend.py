"""Compatibility wrapper that preserves legacy frontend routes and adds modular Admin pages."""
from __future__ import annotations

from fastapi import APIRouter

from frontend_orig import *  # noqa: F401,F403
from frontend_orig import router as _legacy_router
from frontend_agency_reports import router as _agency_reports_frontend_router

router = APIRouter(include_in_schema=False)
router.include_router(_legacy_router)
router.include_router(_agency_reports_frontend_router)
