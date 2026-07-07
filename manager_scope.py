"""
Manager Data Scoping Service (compatibility shim).

The canonical kindergarten-scope logic now lives in dependencies.ManagerScope
(single source of truth — S2). This module re-exports it so existing importers
(manager_analytics_endpoints.py) keep working. A backward-compatible
`validate_kindergarten_access` alias is provided.
"""

from fastapi import status

from dependencies import ManagerScope

__all__ = ["ManagerScope", "ManagerScopeError"]


class ManagerScopeError(Exception):
    """Exception raised for manager scoping violations."""
    def __init__(self, message: str, status_code: int = status.HTTP_403_FORBIDDEN):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Backward-compatible alias for the pre-consolidation method name.
if not hasattr(ManagerScope, "validate_kindergarten_access"):
    ManagerScope.validate_kindergarten_access = staticmethod(  # type: ignore[attr-defined]
        ManagerScope.assert_kindergarten_access
    )
