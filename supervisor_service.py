"""
Supervisor Service Module
Handles all supervisor-specific operations and class management
"""
from datetime import date, datetime, timezone, timedelta
_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
import models
from dependencies import has_role
import validators
from audit_actions import AuditAction
from validators import ValidationError


def _ensure_no_assignment_overlap(
    db: Session,
    supervisor_id: int,
    start_date: date,
    end_date: Optional[date],
) -> None:
    query = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == supervisor_id,
        models.SupervisorAssignment.deleted_at.is_(None),
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= start_date,
        ),
    )
    if end_date is not None:
        query = query.filter(models.SupervisorAssignment.start_date <= end_date)
    if query.first():
        raise ValidationError("Supervisor assignment overlaps an existing class assignment", level=3)


class SupervisorService:
    """Service for supervisor operations and class management"""

    @staticmethod
    def get_supervisor_assigned_classes(
        db: Session,
        supervisor_user: models.User
    ) -> List[models.Class]:
        """
        Get all classes assigned to a supervisor
        """
        if not has_role(supervisor_user, models.UserRole.SUPERVISOR):
            raise ValidationError("User is not a supervisor", level=4)

        # Get current date
        today = _today()

        # Find active assignments
        assignments = db.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.supervisor_id == supervisor_user.id,
            models.SupervisorAssignment.deleted_at.is_(None),
            models.SupervisorAssignment.start_date <= today,
            or_(
                models.SupervisorAssignment.end_date.is_(None),
                models.SupervisorAssignment.end_date >= today
            )
        ).all()

        # Get classes
        class_ids = [a.class_id for a in assignments]
        classes = db.query(models.Class).filter(
            models.Class.id.in_(class_ids),
            models.Class.is_active == True,
            models.Class.deleted_at.is_(None),
        ).all()

        return classes

    @staticmethod
    def get_supervisor_children(
        db: Session,
        supervisor_user: models.User
    ) -> List[models.Child]:
        """
        Get all children in supervisor's assigned classes
        """
        classes = SupervisorService.get_supervisor_assigned_classes(db, supervisor_user)

        if not classes:
            return []

        class_ids = [c.id for c in classes]

        # Restrict strictly to active enrollments in supervisor assigned classes.
        enrollments = db.query(models.EnrollmentApplication).options(
            joinedload(models.EnrollmentApplication.child).joinedload(models.Child.parent)
        ).filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
            models.EnrollmentApplication.child.has(models.Child.deleted_at.is_(None)),
        ).all()

        children_by_id = {}
        for enrollment in enrollments:
            if enrollment.child and enrollment.child.id not in children_by_id:
                children_by_id[enrollment.child.id] = enrollment.child

        return list(children_by_id.values())

    @staticmethod
    def assign_supervisor_to_class(
        db: Session,
        manager_user: models.User,
        supervisor_id: int,
        class_id: int,
        start_date: date,
        end_date: Optional[date] = None,
        is_primary: bool = True
    ) -> models.SupervisorAssignment:
        """
        Manager assigns supervisor to a class
        """
        # L4: Validate manager role
        validators.validate_manager_role(manager_user)

        # Get supervisor user
        supervisor = db.query(models.User).filter(
            models.User.id == supervisor_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.deleted_at.is_(None),
        ).with_for_update().first()

        if not supervisor:
            raise ValidationError("Supervisor not found", level=4)

        # Get class
        class_obj = db.query(models.Class).filter(
            models.Class.id == class_id,
            models.Class.is_active.is_(True),
            models.Class.deleted_at.is_(None),
        ).first()

        if not class_obj:
            raise ValidationError("Class not found", level=4)

        # L4: Validate kindergarten scope
        validators.validate_kindergarten_scope(manager_user, class_obj.kindergarten_id)

        if supervisor.kindergarten_id != class_obj.kindergarten_id:
            raise ValidationError(
                "Supervisor must belong to the same kindergarten as the class",
                level=4
            )

        # L3: Validate no double assignment
        _ensure_no_assignment_overlap(db, supervisor_id, start_date, end_date)

        # Create assignment
        assignment = models.SupervisorAssignment(
            class_id=class_id,
            supervisor_id=supervisor_id,
            is_primary=is_primary,
            start_date=start_date,
            end_date=end_date
        )

        db.add(assignment)
        db.flush()
        db.add(models.AuditLog(
            user_id=manager_user.id,
            action=AuditAction.SUPERVISOR_ASSIGNED,
            entity_type="SupervisorAssignment",
            entity_id=assignment.id,
            details=f"Supervisor {supervisor_id} assigned to Class {class_id}",
            sensitivity_level=3,
        ))
        db.commit()
        db.refresh(assignment)

        return assignment

    @staticmethod
    def assign_replacement_supervisor(
        db: Session,
        manager_user: models.User,
        class_id: int,
        replacement_supervisor_id: int,
        start_date: date,
        end_date: date,
        reason: Optional[str] = None
    ) -> models.SupervisorAssignment:
        """
        Assign replacement supervisor during approved leave
        """
        # L4: Validate manager role
        validators.validate_manager_role(manager_user)

        if not end_date:
            raise ValidationError("Replacement assignment requires end date", level=1)

        if end_date <= start_date:
            raise ValidationError("End date must be after start date", level=2)

        # Get replacement supervisor
        replacement = db.query(models.User).filter(
            models.User.id == replacement_supervisor_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.deleted_at.is_(None),
        ).with_for_update().first()

        if not replacement:
            raise ValidationError("Replacement supervisor not found", level=4)

        # Get class
        class_obj = db.query(models.Class).filter(
            models.Class.id == class_id,
            models.Class.is_active.is_(True),
            models.Class.deleted_at.is_(None),
        ).first()

        if not class_obj:
            raise ValidationError("Class not found", level=4)

        # L4: Validate kindergarten scope
        validators.validate_kindergarten_scope(manager_user, class_obj.kindergarten_id)

        if replacement.kindergarten_id != class_obj.kindergarten_id:
            raise ValidationError(
                "Replacement supervisor must be from the same kindergarten",
                level=4
            )

        # L3: Validate replacement doesn't overlap with another assignment
        _ensure_no_assignment_overlap(
            db, replacement_supervisor_id, start_date, end_date
        )

        # Create replacement assignment
        assignment = models.SupervisorAssignment(
            class_id=class_id,
            supervisor_id=replacement_supervisor_id,
            is_primary=False,  # Replacement is not primary
            start_date=start_date,
            end_date=end_date
        )

        db.add(assignment)
        db.flush()
        db.add(models.AuditLog(
            user_id=manager_user.id,
            action=AuditAction.REPLACEMENT_SUPERVISOR_ASSIGNED,
            entity_type="SupervisorAssignment",
            entity_id=assignment.id,
            details=f"Replacement supervisor {replacement_supervisor_id} for Class {class_id}. Reason: {reason}",
            sensitivity_level=3,
        ))
        db.commit()
        db.refresh(assignment)

        return assignment

    @staticmethod
    def get_class_roster(
        db: Session,
        supervisor_user: models.User,
        class_id: int
    ) -> List[dict]:
        """
        Get roster of children in supervisor's class with key information
        """
        # Verify supervisor has access to this class
        classes = SupervisorService.get_supervisor_assigned_classes(db, supervisor_user)
        class_ids = [c.id for c in classes]

        if class_id not in class_ids:
            raise ValidationError(
                "Supervisor does not have access to this class",
                level=4
            )

        # Get active enrollments for this specific class only.
        enrollments = db.query(models.EnrollmentApplication).options(
            joinedload(models.EnrollmentApplication.child).joinedload(models.Child.parent)
        ).filter(
            models.EnrollmentApplication.class_id == class_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
            models.EnrollmentApplication.child.has(models.Child.deleted_at.is_(None)),
        ).all()

        roster = []
        for enrollment in enrollments:
            child = enrollment.child
            if not child:
                continue

            # Calculate age
            age_months = validators.validate_age_months(child.date_of_birth)

            parent_name = "-"
            parent_phone = None
            if child.parent:
                parent_name = f"{child.parent.first_name} {child.parent.last_name}"
                parent_phone = child.parent.phone_number

            roster.append({
                "child_id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "gender": child.gender.value if child.gender else None,
                "age_months": age_months,
                "parent_name": parent_name,
                "parent_phone": parent_phone,
                "media_consent": child.media_consent,
                "enrollment_start_date": enrollment.enrollment_start_date
            })

        return roster

    @staticmethod
    def get_daily_attendance_status(
        db: Session,
        supervisor_user: models.User,
        target_date: date = None
    ) -> dict:
        """
        Get attendance status for all children in supervisor's classes
        """
        if not target_date:
            target_date = _today()

        children = SupervisorService.get_supervisor_children(db, supervisor_user)

        attendance_status = {
            "date": target_date,
            "total_children": len(children),
            "checked_in": 0,
            "checked_out": 0,
            "absent": 0,
            "children": []
        }

        for child in children:
            attendance = db.query(models.AttendanceLog).filter(
                models.AttendanceLog.child_id == child.id,
                models.AttendanceLog.date == target_date
            ).first()

            if attendance:
                status = "checked_out" if attendance.check_out_at else "checked_in"
                if status == "checked_in":
                    attendance_status["checked_in"] += 1
                else:
                    attendance_status["checked_out"] += 1
            else:
                status = "absent"
                attendance_status["absent"] += 1

            attendance_status["children"].append({
                "child_id": child.id,
                "name": f"{child.first_name} {child.last_name}",
                "status": status,
                "check_in_time": attendance.check_in_at.strftime("%H:%M") if attendance and attendance.check_in_at else None,
                "check_out_time": attendance.check_out_at.strftime("%H:%M") if attendance and attendance.check_out_at else None
            })

        return attendance_status

    @staticmethod
    def get_pending_daily_reports(
        db: Session,
        supervisor_user: models.User,
        report_date: date = None
    ) -> List[dict]:
        """
        Get list of children who need daily reports for the given date
        """
        if not report_date:
            report_date = _today()

        children = SupervisorService.get_supervisor_children(db, supervisor_user)
        child_ids = [c.id for c in children]

        # Get existing reports for this date
        existing_reports = db.query(models.DailyReport).filter(
            models.DailyReport.date == report_date,
            models.DailyReport.child_id.in_(child_ids)
        ).all()

        existing_report_child_ids = {r.child_id: r.status.value for r in existing_reports}

        pending = []
        for child in children:
            # Only include children who attended
            attendance = db.query(models.AttendanceLog).filter(
                models.AttendanceLog.child_id == child.id,
                models.AttendanceLog.date == report_date
            ).first()

            if attendance:
                report_status = existing_report_child_ids.get(child.id, "not_created")

                pending.append({
                    "child_id": child.id,
                    "name": f"{child.first_name} {child.last_name}",
                    "attendance_time": attendance.check_in_at.strftime("%H:%M"),
                    "report_status": report_status,
                    "needs_report": report_status in ["not_created", "draft", "returned"]
                })

        return pending

    @staticmethod
    def record_observation(
        db: Session,
        supervisor_user: models.User,
        child_id: int,
        domain: models.LearningDomain,
        observation_text: str,
        mastery_level: Optional[models.MasteryLevel] = None,
        observed_at: datetime = None
    ) -> models.Observation:
        """
        Record observation for a child in supervisor's class
        """
        # Verify supervisor role
        if not has_role(supervisor_user, models.UserRole.SUPERVISOR):
            raise ValidationError("Only supervisors can record observations", level=4)

        # Verify child is in supervisor's classes
        children = SupervisorService.get_supervisor_children(db, supervisor_user)
        child_ids = [c.id for c in children]

        if child_id not in child_ids:
            raise ValidationError(
                "Supervisor can only record observations for children in their class",
                level=4
            )

        if not observed_at:
            observed_at = datetime.now(_JORDAN_TZ)

        observation = models.Observation(
            child_id=child_id,
            observed_by=supervisor_user.id,
            domain=domain,
            observation_text=observation_text,
            mastery_level=mastery_level,
            observed_at=observed_at
        )

        db.add(observation)
        db.commit()
        db.refresh(observation)

        return observation

    @staticmethod
    def get_child_observations(
        db: Session,
        supervisor_user: models.User,
        child_id: int,
        domain: Optional[models.LearningDomain] = None
    ) -> List[models.Observation]:
        """
        Get observations for a child (filtered by domain if specified)
        """
        # Verify supervisor has access to this child
        children = SupervisorService.get_supervisor_children(db, supervisor_user)
        child_ids = [c.id for c in children]

        if child_id not in child_ids:
            raise ValidationError(
                "Supervisor can only view observations for children in their class",
                level=4
            )

        query = db.query(models.Observation).filter(
            models.Observation.child_id == child_id
        )

        if domain:
            query = query.filter(models.Observation.domain == domain)

        observations = query.order_by(
            models.Observation.observed_at.desc()
        ).all()

        return observations

    @staticmethod
    def get_supervisor_dashboard(
        db: Session,
        supervisor_user: models.User,
        target_date: date = None
    ) -> dict:
        """
        Get comprehensive dashboard data for supervisor
        """
        if not target_date:
            target_date = _today()

        # Get assigned classes
        classes = SupervisorService.get_supervisor_assigned_classes(db, supervisor_user)

        # Get attendance status
        attendance = SupervisorService.get_daily_attendance_status(
            db, supervisor_user, target_date
        )

        # Get pending reports
        pending_reports = SupervisorService.get_pending_daily_reports(
            db, supervisor_user, target_date
        )

        # Get recent observations count
        children = SupervisorService.get_supervisor_children(db, supervisor_user)
        child_ids = [c.id for c in children]

        observations_count = db.query(func.count(models.Observation.id)).filter(
            models.Observation.child_id.in_(child_ids),
            models.Observation.observed_by == supervisor_user.id
        ).scalar() or 0

        dashboard = {
            "supervisor": {
                "name": supervisor_user.username,
                "kindergarten_id": supervisor_user.kindergarten_id
            },
            "date": target_date,
            "classes": [
                {
                    "id": c.id,
                    "name_ar": c.name_ar,
                    "name_en": c.name_en,
                    "capacity": c.capacity_total
                }
                for c in classes
            ],
            "total_children": len(children),
            "attendance_summary": {
                "checked_in": attendance["checked_in"],
                "checked_out": attendance["checked_out"],
                "absent": attendance["absent"]
            },
            "pending_reports_count": sum(1 for r in pending_reports if r["needs_report"]),
            "total_observations": observations_count,
            "alerts": []
        }

        # Add alerts for incomplete tasks
        if dashboard["pending_reports_count"] > 0:
            dashboard["alerts"].append({
                "type": "pending_reports",
                "message": f"{dashboard['pending_reports_count']} daily reports pending",
                "priority": "high"
            })

        return dashboard
