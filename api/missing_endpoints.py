"""Compatibility wrapper that preserves legacy missing endpoints and mounts modular additions."""
from __future__ import annotations

from fastapi import APIRouter

from api.missing_endpoints_orig import *  # noqa: F401,F403
from api.missing_endpoints_orig import router as _legacy_router
from api.agency_reports_api import router as _agency_reports_router

router = APIRouter()
router.include_router(_legacy_router)
router.include_router(_agency_reports_router)
