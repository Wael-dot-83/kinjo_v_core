"""Compatibility wrapper that preserves legacy missing endpoints.

The agency reports API router was previously included here as a compat
addition; it is now mounted directly in main.py under /api/admin to give it
a clean namespace.  This wrapper retains only the legacy missing-endpoints
routes.
"""
from __future__ import annotations

from fastapi import APIRouter

from scripts.compat.missing_endpoints_orig import *  # noqa: F401,F403
from scripts.compat.missing_endpoints_orig import router as _legacy_router

router = APIRouter()
router.include_router(_legacy_router)
