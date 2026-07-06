"""
Manager Data Scoping Service
Provides reusable role/kindergarten-access validation for manager-scoped
operations. Used by manager_analytics_endpoints.py.
"""

from fastapi import HTTPException, status
import models


class ManagerScopeError(Exception):
    """Exception raised for manager scoping violations"""
    def __init__(self, message: str, status_code: int = status.HTTP_403_FORBIDDEN):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ManagerScope:
    """
    Centralized manager role/kindergarten-access validation.
    """

    @staticmethod
    def validate_manager(user: models.User) -> None:
        """Ensure user is a manager with a kindergarten assigned"""
        if user.role != models.UserRole.MANAGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This operation requires manager role"
            )
        if not user.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager must be assigned to a kindergarten"
            )

    @staticmethod
    def validate_kindergarten_access(user: models.User, target_kindergarten_id: int) -> None:
        """
        Validate that a manager can access a specific kindergarten.
        Prevents IDOR by ensuring manager can only access their assigned kindergarten.
        """
        if user.role == models.UserRole.ADMIN:
            return  # Admins can access all kindergartens

        if user.role != models.UserRole.MANAGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only managers and admins can access kindergarten data"
            )

        if not user.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager must be assigned to a kindergarten"
            )

        if user.kindergarten_id != target_kindergarten_id:
            # Return 404 instead of 403 to avoid leaking information
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )

    @staticmethod
    def get_manager_kindergarten_id(user: models.User) -> int:
        """Get and validate manager's kindergarten ID"""
        if user.role == models.UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admins do not have a single assigned kindergarten"
            )

        if not user.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager must be assigned to a kindergarten"
            )

        return user.kindergarten_id


# Export for use in routers
__all__ = ['ManagerScope', 'ManagerScopeError']
