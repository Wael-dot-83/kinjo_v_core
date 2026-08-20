"""Admin routers (ADMIN-002).

Aggregates the admin-facing routers. Section 1.1 of the specification calls
for every admin endpoint to live here and mount under ``/api/v1/admin``; that
migration lands in Phase 6. Today this package holds the routers that have
already moved, and re-exports them under their historical names so existing
mount points in main.py keep working.
"""

from .impersonation import router as impersonation_router

__all__ = ["impersonation_router"]
