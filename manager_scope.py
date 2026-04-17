"""
Manager Data Scoping Service
Provides reusable validation and filtering for manager-scoped operations.
Ensures strict data isolation at kindergarten level.
"""

from typing import Optional, List, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import models


class ManagerScopeError(Exception):
    """Exception raised for manager scoping violations"""
    def __init__(self, message: str, status_code: int = status.HTTP_403_FORBIDDEN):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ManagerScope:
    """
    Centralized manager data scoping enforcement.
    
    Provides:
    - Kindergarten access validation
    - Query filtering
    - Cross-kindergarten data access prevention (IDOR)
    - Permission checks
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

    @staticmethod
    def filter_user_by_kindergarten(query, user: models.User):
        """
        Filter a user query to respect manager scope.
        
        Managers see only users in their kindergarten.
        Admins see all non-admin users.
        """
        if user.role == models.UserRole.ADMIN:
            # Admins cannot see other admins
            query = query.filter(models.User.role != models.UserRole.ADMIN)
        elif user.role == models.UserRole.MANAGER:
            # Managers see only their kindergarten's staff + parents with children there
            query = query.filter(
                or_(
                    models.User.kindergarten_id == user.kindergarten_id,
                    # Also include parents with children in this KG
                    models.User.id.in_(
                        db.query(models.ParentProfile.user_id)
                        .join(models.Child)
                        .join(models.EnrollmentApplication)
                        .filter(models.EnrollmentApplication.kindergarten_id == user.kindergarten_id)
                        .distinct()
                    )
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list users"
            )
        return query

    @staticmethod
    def filter_class_by_kindergarten(query, user: models.User):
        """
        Filter a class query to respect manager scope.
        
        Managers see only classes in their kindergarten.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            return query.filter(models.Class.kindergarten_id == user.kindergarten_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list classes"
            )

    @staticmethod
    def filter_enrollment_by_kindergarten(query, user: models.User):
        """
        Filter enrollment query to respect manager scope.
        
        Managers see only enrollments in their kindergarten.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            return query.filter(
                models.EnrollmentApplication.kindergarten_id == user.kindergarten_id
            )
        elif user.role == models.UserRole.SUPERVISOR:
            # Supervisor sees only enrollments for their assigned classes
            return query.filter(
                models.EnrollmentApplication.class_id.in_(
                    db.query(models.Class.id)
                    .filter(models.Class.supervisor_id == user.id)
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list enrollments"
            )

    @staticmethod
    def filter_incident_by_kindergarten(query, user: models.User):
        """
        Filter incident query to respect manager scope.
        
        Managers see only incidents in their kindergarten.
        Supervisors see incidents for children in their classes.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            return query.filter(models.Incident.kindergarten_id == user.kindergarten_id)
        elif user.role == models.UserRole.SUPERVISOR:
            # Supervisor sees incidents for children in their assigned classes
            return query.filter(
                models.Incident.child_id.in_(
                    db.query(models.Child.id)
                    .join(models.EnrollmentApplication)
                    .filter(
                        models.EnrollmentApplication.class_id.in_(
                            db.query(models.Class.id)
                            .filter(models.Class.supervisor_id == user.id)
                        )
                    )
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list incidents"
            )

    @staticmethod
    def filter_daily_report_by_kindergarten(query, user: models.User):
        """
        Filter daily report query to respect manager scope.
        
        Managers see only reports for their kindergarten.
        Supervisors see reports for children in their classes.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            # Manager sees reports for children in their kindergarten
            return query.filter(
                models.DailyReport.child_id.in_(
                    db.query(models.Child.id)
                    .join(models.EnrollmentApplication)
                    .filter(models.EnrollmentApplication.kindergarten_id == user.kindergarten_id)
                )
            )
        elif user.role == models.UserRole.SUPERVISOR:
            # Supervisor sees reports for children in their assigned classes
            return query.filter(
                models.DailyReport.child_id.in_(
                    db.query(models.Child.id)
                    .join(models.EnrollmentApplication)
                    .filter(
                        models.EnrollmentApplication.class_id.in_(
                            db.query(models.Class.id)
                            .filter(models.Class.supervisor_id == user.id)
                        )
                    )
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list daily reports"
            )

    @staticmethod
    def filter_child_by_kindergarten(query, user: models.User):
        """
        Filter child query to respect manager scope.
        
        Managers see children enrolled in their kindergarten.
        Supervisors see children in their assigned classes.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            # Manager sees children enrolled in their kindergarten
            return query.filter(
                models.Child.id.in_(
                    db.query(models.Child.id)
                    .join(models.EnrollmentApplication)
                    .filter(models.EnrollmentApplication.kindergarten_id == user.kindergarten_id)
                )
            )
        elif user.role == models.UserRole.SUPERVISOR:
            # Supervisor sees children in their assigned classes
            return query.filter(
                models.Child.id.in_(
                    db.query(models.Child.id)
                    .join(models.EnrollmentApplication)
                    .filter(
                        models.EnrollmentApplication.class_id.in_(
                            db.query(models.Class.id)
                            .filter(models.Class.supervisor_id == user.id)
                        )
                    )
                )
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list children"
            )

    @staticmethod
    def filter_supervisor_by_kindergarten(query, user: models.User):
        """
        Filter supervisor query to respect manager scope.
        
        Managers see supervisors in their kindergarten.
        """
        if user.role == models.UserRole.ADMIN:
            return query  # Admins see all
        elif user.role == models.UserRole.MANAGER:
            return query.filter(models.User.kindergarten_id == user.kindergarten_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to list supervisors"
            )

    @staticmethod
    def validate_supervisor_assignment(
        db: Session,
        user: models.User,
        supervisor_id: int,
        kindergarten_id: int
    ) -> models.User:
        """
        Validate that a manager can assign a supervisor to a class.
        
        Returns the supervisor user object if valid.
        Raises HTTPException on validation failure.
        """
        ManagerScope.validate_kindergarten_access(user, kindergarten_id)

        # Get supervisor (managers can also act as supervisors)
        supervisor = db.query(models.User).filter(
            models.User.id == supervisor_id,
            models.User.role.in_([models.UserRole.SUPERVISOR, models.UserRole.MANAGER]),
        ).first()

        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found"
            )

        # Ensure supervisor is in same kindergarten
        if supervisor.kindergarten_id != kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supervisor must be in the same kindergarten"
            )

        return supervisor

    @staticmethod
    def validate_child_enrollment(
        db: Session,
        user: models.User,
        child_id: int,
        kindergarten_id: int
    ) -> models.Child:
        """
        Validate that a manager can operate on a child.
        
        Returns the child object if valid.
        Raises HTTPException if child is not in manager's kindergarten.
        """
        ManagerScope.validate_kindergarten_access(user, kindergarten_id)

        # Get child
        child = db.query(models.Child).filter(models.Child.id == child_id).first()

        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child not found"
            )

        # Ensure child has enrollment in this kindergarten
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        ).first()

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child is not enrolled in this kindergarten"
            )

        return child

    @staticmethod
    def validate_class_ownership(
        db: Session,
        user: models.User,
        class_id: int,
        kindergarten_id: int
    ) -> models.Class:
        """
        Validate that a manager can operate on a class.
        
        Returns the class object if valid.
        Raises HTTPException if class is not in manager's kindergarten.
        """
        ManagerScope.validate_kindergarten_access(user, kindergarten_id)

        # Get class
        class_obj = db.query(models.Class).filter(
            models.Class.id == class_id,
            models.Class.kindergarten_id == kindergarten_id
        ).first()

        if not class_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found or belongs to different kindergarten"
            )

        return class_obj

    @staticmethod
    def validate_daily_report_ownership(
        db: Session,
        user: models.User,
        report_id: int
    ) -> models.DailyReport:
        """
        Validate that a manager can operate on a daily report.
        
        Returns the report object if valid.
        Raises HTTPException if report child is not in manager's kindergarten.
        """
        # Get report with child and enrollments
        report = db.query(models.DailyReport).filter(
            models.DailyReport.id == report_id
        ).first()

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Daily report not found"
            )

        # Ensure child is in manager's kindergarten
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == report.child_id,
            models.EnrollmentApplication.kindergarten_id == user.kindergarten_id
        ).first()

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report belongs to different kindergarten"
            )

        return report

    @staticmethod
    def validate_incident_ownership(
        db: Session,
        user: models.User,
        incident_id: int
    ) -> models.Incident:
        """
        Validate that a manager can operate on an incident.
        
        Returns the incident object if valid.
        Raises HTTPException if incident is not in manager's kindergarten.
        """
        incident = db.query(models.Incident).filter(
            models.Incident.id == incident_id
        ).first()

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Incident not found"
            )

        # Ensure incident is in manager's kindergarten
        if user.role == models.UserRole.MANAGER:
            if incident.kindergarten_id != user.kindergarten_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Incident belongs to different kindergarten"
                )

        return incident


# Export for use in routers
__all__ = ['ManagerScope', 'ManagerScopeError']
