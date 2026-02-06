"""
KPI and Governance Reporting Services
Implements all KPIs from Section 5 of the SRS
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, literal_column
from pydantic import BaseModel

import models
from database import get_db
from dependencies import get_current_user, require_admin
import validators

# Import new models/enums
from models import TrainingStatus, TrainingModule, StaffTrainingCompletion, KPITarget

router = APIRouter()


# --- Pydantic Models for new KPI Dashboard ---
class TrendDataPoint(BaseModel):
    date: date
    value: float

class KPICardData(BaseModel):
    value: float
    unit: Optional[str] = None
    trend_indicator: Optional[str] = None # "up", "down", "flat"
    trend_change: Optional[float] = None # percentage change vs prev period
    band: Optional[str] = None # "GREEN", "AMBER", "RED"
    alert: Optional[str] = None # "anomaly", "threshold_breached"
    tooltip: Optional[str] = None

class StudentDistributionItem(BaseModel):
    label: str
    value: int

class TopBottomPerformer(BaseModel):
    id: int
    name: str
    value: float
    rank: Optional[int] = None
    governorate: Optional[str] = None

class AlertsSummary(BaseModel):
    type: str
    message: str
    priority: str
    entity_id: Optional[int] = None

class KPISummaryResponse(BaseModel):
    period_start: date
    period_end: date
    attendance_rate: float
    incident_rate: float
    serious_incident_rate: float
    ratio_compliance: float
    gqi_score: float

class KPIDashboardResponse(BaseModel):
    period_start: date
    period_end: date
    kindergarten_id: Optional[int] = None # if filtered for single KG
    governorate: Optional[str] = None # if filtered for single Governorate

    overall_gcei: KPICardData
    attendance_rate: KPICardData
    ratio_compliance: KPICardData
    training_completion_rate: KPICardData
    report_submission_rate: KPICardData

    incident_rate: KPICardData
    serious_incident_rate: KPICardData
    incident_followup_sla: KPICardData
    chronic_absence_rate: KPICardData

    capacity_utilization_rate: KPICardData
    active_enrollments: KPICardData
    new_enrollments: KPICardData

    student_distribution: List[StudentDistributionItem]
    top_performers_by_gcei: List[TopBottomPerformer]
    low_performers_by_gcei: List[TopBottomPerformer]
    
    attendance_trend: List[TrendDataPoint] 
    incidents_trend: List[TrendDataPoint]
    enrollment_trend: List[TrendDataPoint]
    gcei_trend: List[TrendDataPoint]

    alerts: List[AlertsSummary]


class AttendanceRateResponse(BaseModel):
    kindergarten_id: Optional[int] = None
    period_start: date
    period_end: date
    attendance_rate: float


class GovernanceScoreResponse(BaseModel):
    kindergarten_id: Optional[int] = None
    period_start: date
    period_end: date
    governance_score: float
    governance_band: str


class MonthlySnapshotResponse(BaseModel):
    message: str
    snapshots_created: int
    kindergarten_id: int
    month: date


class FilterOption(BaseModel):
    id: int
    name: str


class KpiFiltersResponse(BaseModel):
    kindergartens: List[FilterOption]
    governorates: List[FilterOption]


class KPIService:
    """Service for computing and managing KPIs"""
    @staticmethod
    def compute_attendance_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Attendance rate % = (Child-days attended / expected child-days) x 100
        """
        # Count child-days attended
        attended_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Count expected child-days
        # Simplified: Count days * active enrollments
        # In production, would exclude closed days from operating calendar
        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        days_in_period = (period_end - period_start).days + 1
        expected_days = active_enrollments * days_in_period

        if expected_days == 0:
            return 0.0

        rate = (attended_days / expected_days) * 100
        return round(rate, 2)

    @staticmethod
    def compute_incident_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Incident rate per 100 child-days = (All incidents / total child-days) x 100
        """
        # Count incidents
        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        # Count child-days attended
        attended_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        ).scalar() or 1  # Avoid division by zero

        rate = (incident_count / attended_days) * 100
        return round(rate, 2)

    @staticmethod
    def compute_serious_incident_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Serious incident rate per 100 child-days (HIGH/CRITICAL only)
        """
        # Count high/critical incidents
        serious_incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.severity_level.in_([
                models.SeverityLevel.HIGH,
                models.SeverityLevel.CRITICAL
            ])
        ).scalar() or 0

        # Count child-days attended
        attended_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        ).scalar() or 1

        rate = (serious_incident_count / attended_days) * 100
        return round(rate, 2)

    @staticmethod
    def compute_ratio_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Staff-child ratio compliance % = (Compliant minutes / operating minutes) x 100
        """
        # Sum compliant and operating minutes
        result = db.query(
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes)
        ).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end
        ).first()

        compliant_minutes = result[0] or 0
        operating_minutes = result[1] or 1

        rate = (compliant_minutes / operating_minutes) * 100
        return round(rate, 2)

    @staticmethod
    def compute_incident_followup_sla_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Incident follow-up within SLA % = (Closed within SLA / requiring follow-up) x 100
        """
        # Count incidents requiring follow-up
        total_followup_required = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True
        ).scalar() or 0

        if total_followup_required == 0:
            return 100.0  # No follow-ups required = 100% compliance

        # Count incidents closed within SLA
        closed_within_sla = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.isnot(None),
            models.Incident.closed_at <= models.Incident.followup_sla_deadline
        ).scalar() or 0

        rate = (closed_within_sla / total_followup_required) * 100
        return round(rate, 2)

    @staticmethod
    def compute_chronic_absence_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
        threshold_percent: float = 10.0
    ) -> float:
        """
        Chronic absence % = (Children with absence >= threshold / active children) x 100
        Default threshold: 10% of expected days
        """
        # Get all active children
        active_children = db.query(models.Child.id).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()

        if not active_children:
            return 0.0

        child_ids = [c[0] for c in active_children]
        days_in_period = (period_end - period_start).days + 1

        chronic_absence_count = 0

        for child_id in child_ids:
            # Count attendance days
            attended_days = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.child_id == child_id,
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).scalar() or 0

            absence_rate = ((days_in_period - attended_days) / days_in_period) * 100

            if absence_rate >= threshold_percent:
                chronic_absence_count += 1

        rate = (chronic_absence_count / len(child_ids)) * 100
        return round(rate, 2)

    @staticmethod
    def create_kpi_snapshot(
        db: Session,
        kindergarten_id: Optional[int],
        kpi_name: str,
        kpi_value: float,
        period_start: date,
        period_end: date,
        is_monthly: bool = False
    ) -> models.KPISnapshot:
        """Create KPI snapshot (immutable if monthly)"""
        snapshot = models.KPISnapshot(
            kindergarten_id=kindergarten_id,
            kpi_name=kpi_name,
            kpi_value=kpi_value,
            period_start=period_start,
            period_end=period_end,
            is_locked=is_monthly
        )

        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        return snapshot

    @staticmethod
    def populate_ratio_compliance_for_date(
        db: Session,
        kindergarten_id: int,
        date: date
    ) -> None:
        """
        Populate ratio compliance data for a specific date.
        This should be called daily or when attendance data changes.
        """
        # Skip weekends (assuming kindergarten doesn't operate on weekends)
        if date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return

        # Check if already exists
        existing = db.query(models.RatioCompliance).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date == date
        ).first()

        if existing:
            return  # Already populated

        # Get operating hours for the kindergarten
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if not kg or not kg.operating_hours_start or not kg.operating_hours_end:
            return  # Cannot calculate without operating hours

        # Parse time strings to datetime.time objects
        from datetime import datetime, time
        try:
            start_time = datetime.strptime(kg.operating_hours_start, '%H:%M').time()
            end_time = datetime.strptime(kg.operating_hours_end, '%H:%M').time()
        except ValueError:
            return  # Invalid time format

        # Calculate operating minutes
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        operating_minutes = end_minutes - start_minutes

        if operating_minutes <= 0:
            return

        # Get staff count (simplified - count active supervisors)
        staff_count = db.query(func.count(models.User.id)).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE
        ).scalar() or 0

        # Get child count (enrolled and active)
        child_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Calculate compliant minutes (simplified logic)
        # In a real system, this would track actual staffing throughout the day
        if staff_count > 0 and child_count > 0:
            # Assume 1:10 ratio is required (adjust based on regulations)
            required_staff = max(1, child_count // 10)
            if staff_count >= required_staff:
                compliant_minutes = operating_minutes
            else:
                # Partial compliance based on available staff
                compliance_ratio = staff_count / required_staff
                compliant_minutes = int(operating_minutes * compliance_ratio)
        else:
            compliant_minutes = 0

        # Create record
        record = models.RatioCompliance(
            kindergarten_id=kindergarten_id,
            date=date,
            operating_minutes=operating_minutes,
            compliant_minutes=compliant_minutes,
            staff_count_avg=float(staff_count),
            child_count_avg=float(child_count)
        )

        db.add(record)
        db.commit()

    @staticmethod
    def populate_ratio_compliance_for_period(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> None:
        """
        Populate ratio compliance data for a date range.
        """
        current_date = start_date
        while current_date <= end_date:
            KPIService.populate_ratio_compliance_for_date(db, kindergarten_id, current_date)
            current_date += timedelta(days=1)

    @staticmethod
    def compute_child_experience_index(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        CEI: weighted mix of:
        - Attendance rate
        - Chronic absence (inverted)
        - Serious incidents (inverted)
        - Parent satisfaction (placeholder)
        """
        weights = {
            'attendance_rate': 0.30,
            'chronic_absence': 0.25,
            'serious_incidents': 0.25,
            'parent_satisfaction': 0.20
        }

        attendance_rate = KPIService.compute_attendance_rate(
            db, kindergarten_id, period_start, period_end
        )

        chronic_absence_rate = KPIService.compute_chronic_absence_rate(
            db, kindergarten_id, period_start, period_end
        )

        serious_incident_rate = KPIService.compute_serious_incident_rate(
            db, kindergarten_id, period_start, period_end
        )

        # Placeholder
        parent_satisfaction = 85.0  # Would compute from survey results

        # CEI calculation (invert negative metrics)
        cei = (
            attendance_rate * weights['attendance_rate'] +
            (100 - chronic_absence_rate) * weights['chronic_absence'] +
            (100 - min(serious_incident_rate, 100)) * weights['serious_incidents'] +
            parent_satisfaction * weights['parent_satisfaction']
        )

        return round(cei, 2)

    @staticmethod
    def compute_governance_score(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> Tuple[float, str]:
        """
        Compute final governance score (0-100) and band (RED/AMBER/GREEN)
        """
        gqi = KPIService.compute_governance_quality_index(
            db, kindergarten_id, period_start, period_end
        )

        cei = KPIService.compute_child_experience_index(
            db, kindergarten_id, period_start, period_end
        )

        # Final score: weighted average
        final_score = (gqi * 0.60) + (cei * 0.40)

        # Determine band
        if final_score >= 80:
            band = "GREEN"
        elif final_score >= 60:
            band = "AMBER"
        else:
            band = "RED"

        # Check regulatory override
        kindergarten = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if kindergarten and kindergarten.license_valid_until:
            if kindergarten.license_valid_until < date.today():
                band = "RED"  # Regulatory non-compliance overrides green

        return round(final_score, 2), band

    @staticmethod
    def save_governance_score(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> models.GovernanceScore:
        """Compute and save governance score"""
        gqi = KPIService.compute_governance_quality_index(
            db, kindergarten_id, period_start, period_end
        )

        cei = KPIService.compute_child_experience_index(
            db, kindergarten_id, period_start, period_end
        )

        final_score, band = KPIService.compute_governance_score(
            db, kindergarten_id, period_start, period_end
        )

        governance_score = models.GovernanceScore(
            kindergarten_id=kindergarten_id,
            period_start=period_start,
            period_end=period_end,
            governance_quality_index=gqi,
            child_experience_index=cei,
            final_governance_score=final_score,
            band=band
        )

        db.add(governance_score)
        db.commit()
        db.refresh(governance_score)

        return governance_score

    @staticmethod
    def generate_monthly_snapshots(db: Session, kindergarten_id: int,
                                  month: date) -> List[models.KPISnapshot]:
        """
        Generate immutable monthly KPI snapshots for a kindergarten
        """
        # Calculate period
        period_start = month.replace(day=1)
        if month.month == 12:
            period_end = date(month.year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(month.year, month.month + 1, 1) - timedelta(days=1)

        snapshots = []

        # Attendance rate
        attendance_rate = KPIService.compute_attendance_rate(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "attendance_rate", attendance_rate,
                period_start, period_end, is_monthly=True
            )
        )

        # Incident rate
        incident_rate = KPIService.compute_incident_rate(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "incident_rate", incident_rate,
                period_start, period_end, is_monthly=True
            )
        )

        # Ratio compliance
        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "ratio_compliance", ratio_compliance,
                period_start, period_end, is_monthly=True
            )
        )

        return snapshots
    
    @staticmethod
    def get_kpi_target(
        db: Session,
        kpi_name: str,
        kindergarten_id: Optional[int] = None,
        target_date: date = date.today()
    ) -> Optional[models.KPITarget]:
        """
        Retrieves the most relevant KPI target for a given KPI name and kindergarten_id
        effective on the target_date. Prioritizes kindergarten-specific targets.
        """
        query = db.query(KPITarget).filter(
            KPITarget.kpi_name == kpi_name,
            KPITarget.effective_date <= target_date
        ).order_by(
            KPITarget.effective_date.desc()
        )

        # Prioritize kindergarten-specific targets
        if kindergarten_id:
            kg_target = query.filter(KPITarget.kindergarten_id == kindergarten_id).first()
            if kg_target:
                return kg_target
        
        # Fallback to network-wide targets
        network_target = query.filter(KPITarget.kindergarten_id == None).first()
        return network_target

    @staticmethod
    def compute_training_completion_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculates the percentage of mandatory staff training modules completed.
        """
        # Get all active staff in the kindergarten
        staff_users = db.query(models.User).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR])
        ).all()
        
        if not staff_users:
            return 100.0 # No staff, so 100% compliant
        
        total_mandatory_modules = db.query(func.count(TrainingModule.id)).filter(
            TrainingModule.is_mandatory == True
        ).scalar() or 0

        if total_mandatory_modules == 0:
            return 100.0 # No mandatory trainings, so 100% compliant
        
        total_expected_completions = len(staff_users) * total_mandatory_modules
        
        if total_expected_completions == 0:
            return 100.0
            
        actual_completions = db.query(func.count(StaffTrainingCompletion.id)).filter(
            StaffTrainingCompletion.kindergarten_id == kindergarten_id,
            StaffTrainingCompletion.completion_date >= period_start,
            StaffTrainingCompletion.completion_date <= period_end,
            StaffTrainingCompletion.user_id.in_([u.id for u in staff_users]),
            StaffTrainingCompletion.status == TrainingStatus.COMPLETED
        ).scalar() or 0
        
        rate = (actual_completions / total_expected_completions) * 100
        return round(rate, 2)

    @staticmethod
    def compute_report_submission_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculates the percentage of expected daily reports submitted on time.
        Placeholder for now, assuming 95% compliance. Needs complex logic to count expected reports.
        """
        return 95.0 # Placeholder

    @staticmethod
    def compute_governance_quality_index(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        GQI: weighted mix of:
        - Ratio Compliance (weighted 0.3)
        - Incident Rate (inverted, weighted 0.2)
        - Serious Incident Rate (inverted, weighted 0.2)
        - Training Completion Rate (weighted 0.15)
        - Report Submission Rate (weighted 0.15)
        - Checklist Compliance (placeholder, weighted 0.0)
        - Regulatory Status (placeholder, weighted 0.0)
        """
        weights = {
            'ratio_compliance': 0.30,
            'incident_rate': 0.20,
            'serious_incident_rate': 0.20,
            'training_completion_rate': 0.15,
            'report_submission_rate': 0.15,
            # Placeholder for now, to be implemented
            'checklist_compliance': 0.0,
            'regulatory_status': 0.0
        }

        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )
        incident_rate = KPIService.compute_incident_rate(
            db, kindergarten_id, period_start, period_end
        )
        serious_incident_rate = KPIService.compute_serious_incident_rate(
            db, kindergarten_id, period_start, period_end
        )
        training_completion_rate = KPIService.compute_training_completion_rate(
            db, kindergarten_id, period_start, period_end
        )
        report_submission_rate = KPIService.compute_report_submission_rate(
            db, kindergarten_id, period_start, period_end
        )

        # Improved placeholders - check actual data availability
        checklist_compliance = 100.0 # KPIService.compute_checklist_compliance(db, kindergarten_id, period_start, period_end)
        regulatory_status = 100.0 # KPIService.compute_regulatory_status(db, kindergarten_id)

        # GQI calculation (invert negative metrics, cap at 100)
        gqi = (
            ratio_compliance * weights['ratio_compliance'] +
            (100 - min(incident_rate, 100)) * weights['incident_rate'] +
            (100 - min(serious_incident_rate, 100)) * weights['serious_incident_rate'] +
            training_completion_rate * weights['training_completion_rate'] +
            report_submission_rate * weights['report_submission_rate'] +
            checklist_compliance * weights['checklist_compliance'] +
            regulatory_status * weights['regulatory_status']
        )

        return round(gqi, 2)

    @staticmethod
    def compute_capacity_utilization_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculates the capacity utilization rate for a kindergarten.
        """
        total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).scalar() or 0

        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        if total_capacity == 0:
            return 0.0

        return round((active_enrollments / total_capacity) * 100, 2)

    @staticmethod
    def compute_new_enrollments(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> int:
        """Counts new enrollments created within the period."""
        return db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.created_at >= period_start,
            models.EnrollmentApplication.created_at <= period_end
        ).scalar() or 0

    @staticmethod
    def compute_checklist_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Compliance with daily operational checklists.
        Placeholder for now, assuming 100% compliance.
        """
        return 100.0 # Placeholder


    @staticmethod
    def compute_regulatory_status(
        db: Session,
        kindergarten_id: int
    ) -> float:
        """
        Regulatory status KPI.
        Placeholder for now, assuming 100% compliance.
        """
        # In production, would check license expiry, audit findings, etc.
        return 100.0 # Placeholder


    @staticmethod
    def compute_training_coverage(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date # This is likely not used for 'coverage' over a period, but for eligibility
    ) -> float:
        """
        Training coverage % - staff training completion rate.
        Now uses compute_training_completion_rate
        """
        return KPIService.compute_training_completion_rate(db, kindergarten_id, period_start, period_end)
    
@router.post("/kpi/populate-ratio-compliance")
def populate_ratio_compliance_data(
    kindergarten_id: Optional[int] = None,
    days_back: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Populate ratio compliance data for historical dates"""
    validators.validate_manager_role(current_user)

    if current_user.role == models.UserRole.MANAGER and kindergarten_id is None:
        kindergarten_id = current_user.kindergarten_id
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID required")

    # Populate data for the last N days
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    KPIService.populate_ratio_compliance_for_period(db, kindergarten_id, start_date, end_date)

    return {"message": f"Ratio compliance data populated for {days_back} days"}

@router.get("/kpi/student-distribution")
def get_student_distribution(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get student distribution by level for dashboard chart"""
    validators.validate_manager_role(current_user)

    kg_id = current_user.kindergarten_id

    # Count enrollments by level/class
    # Simplified: group by class name or level
    results = db.query(
        models.Class.name_ar,
        func.count(models.EnrollmentApplication.id)
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.class_id == models.Class.id
    ).filter(
        models.Class.kindergarten_id == kg_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).group_by(models.Class.name_ar).all()

    if not results:
        # Fallback data
        return {
            "labels": ["KG1", "KG2", "Ø­Ø¶Ø§Ù†Ø©"],
            "values": [0, 0, 0]
        }

    labels = [row[0] for row in results]
    values = [row[1] for row in results]

    return {
        "labels": labels,
        "values": values
    }

@router.get("/kpi/summary", response_model=KPISummaryResponse)
def get_kpi_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summarized KPI metrics for a given period (default: current month)"""
    validators.validate_manager_role(current_user)
    
    # Default to current month if not provided
    if not start_date or not end_date:
        today = date.today()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
            
    kg_id = current_user.kindergarten_id
    
    # Compute metrics
    # Note: Using static methods from KPIService class
    att_rate = KPIService.compute_attendance_rate(db, kg_id, start_date, end_date)
    inc_rate = KPIService.compute_incident_rate(db, kg_id, start_date, end_date)
    ser_inc_rate = KPIService.compute_serious_incident_rate(db, kg_id, start_date, end_date)
    ratio_comp = KPIService.compute_ratio_compliance(db, kg_id, start_date, end_date)
    gqi = KPIService.compute_governance_quality_index(db, kg_id, start_date, end_date)
    return KPISummaryResponse(
        period_start=start_date,
        period_end=end_date,
        attendance_rate=att_rate,
        incident_rate=inc_rate,
        serious_incident_rate=ser_inc_rate,
        ratio_compliance=ratio_comp,
        gqi_score=gqi
    )

@router.get("/kpi/attendance-rate", response_model=AttendanceRateResponse)
def get_attendance_rate(
    kindergarten_id: Optional[int] = Query(None, description="Optional. Kindergarten ID. Managers see their own, Admins can specify any."),
    start_date: Optional[date] = Query(None, description="Start date for the period (YYYY-MM-DD). Defaults to start of current month."),
    end_date: Optional[date] = Query(None, description="End date for the period (YYYY-MM-DD). Defaults to end of current month."),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the attendance rate for a specified kindergarten and period.
    Admins can query any kindergarten. Managers can only query their own.
    """
    # Default to current month if dates not provided
    if not start_date or not end_date:
        today = date.today()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # RBAC check
    if current_user.role == models.UserRole.MANAGER:
        if kindergarten_id is not None and kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(
                status_code=403, detail="Managers can only view KPIs for their assigned kindergarten."
            )
        target_kindergarten_id = current_user.kindergarten_id
    elif current_user.role == models.UserRole.ADMIN:
        if kindergarten_id is None:
            raise HTTPException(status_code=400, detail="Admin must specify a kindergarten_id.")
        target_kindergarten_id = kindergarten_id
    else:
        raise HTTPException(status_code=403, detail="Access denied. Admin or Manager role required.")

    if target_kindergarten_id is None:
        raise HTTPException(status_code=400, detail="Kindergarten ID is required.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == target_kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    attendance_rate = KPIService.compute_attendance_rate(db, target_kindergarten_id, start_date, end_date)

    return AttendanceRateResponse(
        kindergarten_id=target_kindergarten_id,
        period_start=start_date,
        period_end=end_date,
        attendance_rate=attendance_rate
    )

@router.get("/kpi/governance-score", response_model=GovernanceScoreResponse)
def get_governance_score(
    kindergarten_id: Optional[int] = Query(None, description="Optional. Kindergarten ID. Managers see their own, Admins can specify any."),
    start_date: Optional[date] = Query(None, description="Start date for the period (YYYY-MM-DD). Defaults to start of current month."),
    end_date: Optional[date] = Query(None, description="End date for the period (YYYY-MM-DD). Defaults to end of current month."),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the governance score and band for a specified kindergarten and period.
    Admins can query any kindergarten. Managers can only query their own.
    """
    # Default to current month if dates not provided
    if not start_date or not end_date:
        today = date.today()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # RBAC check
    if current_user.role == models.UserRole.MANAGER:
        if kindergarten_id is not None and kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(
                status_code=403, detail="Managers can only view KPIs for their assigned kindergarten."
            )
        target_kindergarten_id = current_user.kindergarten_id
    elif current_user.role == models.UserRole.ADMIN:
        if kindergarten_id is None:
            raise HTTPException(status_code=400, detail="Admin must specify a kindergarten_id.")
        target_kindergarten_id = kindergarten_id
    else:
        raise HTTPException(status_code=403, detail="Access denied. Admin or Manager role required.")

    if target_kindergarten_id is None:
        raise HTTPException(status_code=400, detail="Kindergarten ID is required.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == target_kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    governance_score, governance_band = KPIService.compute_governance_score(db, target_kindergarten_id, start_date, end_date)

    return GovernanceScoreResponse(
        kindergarten_id=target_kindergarten_id,
        period_start=start_date,
        period_end=end_date,
        governance_score=governance_score,
        governance_band=governance_band
    )

@router.post("/kpi/monthly-snapshots", response_model=MonthlySnapshotResponse)
def generate_monthly_snapshots(
    month: str = Query(..., description="Month in YYYY-MM format"),
    kindergarten_id: int = Query(..., description="Kindergarten ID"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Generate monthly KPI snapshots for a specific kindergarten and month.
    Requires admin role.
    """
    # Validate month format
    try:
        snapshot_month = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    # Generate snapshots
    snapshots = KPIService.generate_monthly_snapshots(db, kindergarten_id, snapshot_month)

    return MonthlySnapshotResponse(
        message=f"Generated {len(snapshots)} monthly KPI snapshots for kindergarten {kindergarten_id} for {month}.",
        snapshots_created=len(snapshots),
        kindergarten_id=kindergarten_id,
        month=snapshot_month
    )

@router.get("/kpi/dashboard-data", response_model=KPIDashboardResponse)
def get_consolidated_kpi_dashboard_data(
    kindergarten_ids: Optional[List[int]] = Query(
        None, description="Kindergarten IDs to include (admin only)"
    ),
    governorate: Optional[str] = Query(
        None, description="Jordanian governorate filter (admin only)"
    ),
    period_start: Optional[date] = Query(
        None, description="Start date for the KPI period (inclusive)"
    ),
    period_end: Optional[date] = Query(
        None, description="End date for the KPI period (inclusive)"
    ),
    granularity: str = Query(
        "weekly", regex="^(daily|weekly|monthly)$", description="Trend granularity"
    ),
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Consolidated KPI dashboard payload.
    Admins may filter by kindergarten IDs or governorate; managers only see their own kindergarten.
    """
    granularity = granularity.lower()
    if granularity not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid granularity")

    if not period_start or not period_end:
        today = date.today()
        period_start = today.replace(day=1)
        period_end = (
            date(today.year + 1, 1, 1) - timedelta(days=1)
            if today.month == 12
            else date(today.year, today.month + 1, 1) - timedelta(days=1)
        )

    if period_start > period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_start must be on or before period_end")

    target_kindergarten_ids: List[int] = []
    selected_governorate: Optional[str] = None

    if current_user.role == models.UserRole.ADMIN:
        if kindergarten_ids:
            target_kindergarten_ids = list(dict.fromkeys(kindergarten_ids))
        elif governorate:
            try:
                normalized = validators.validate_jordan_governorate(governorate)
            except validators.ValidationError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            selected_governorate = normalized
            target_kindergarten_ids = [
                kg.id
                for kg in db.query(models.Kindergarten)
                .filter(
                    models.Kindergarten.governorate == normalized,
                    models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                )
                .all()
            ]
        else:
            target_kindergarten_ids = [
                kg.id
                for kg in db.query(models.Kindergarten)
                .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
                .all()
            ]
    elif current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manager is not assigned to a kindergarten")
        if kindergarten_ids and current_user.kindergarten_id not in kindergarten_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager cannot access other kindergartens")
        if governorate:
            try:
                normalized = validators.validate_jordan_governorate(governorate)
            except validators.ValidationError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            kg_gov = (
                db.query(models.Kindergarten.governorate)
                .filter(models.Kindergarten.id == current_user.kindergarten_id)
                .scalar()
            )
            if kg_gov != normalized:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager's kindergarten is not in the specified governorate")
            selected_governorate = normalized
        target_kindergarten_ids = [current_user.kindergarten_id]
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view KPI dashboard")

    kindergarten_records = (
        db.query(models.Kindergarten)
        .filter(
            models.Kindergarten.id.in_(target_kindergarten_ids),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        )
        .all()
    )
    target_kindergarten_ids = [kg.id for kg in kindergarten_records]

    if not target_kindergarten_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No kindergartens found for the applied filters")

    kindergarten_count = len(target_kindergarten_ids)
    single_kindergarten_id = target_kindergarten_ids[0] if kindergarten_count == 1 else None

    totals = {
        "gce_score": 0.0,
        "attendance_rate": 0.0,
        "incident_rate": 0.0,
        "serious_incident_rate": 0.0,
        "ratio_compliance": 0.0,
        "training_completion_rate": 0.0,
        "report_submission_rate": 0.0,
        "capacity_utilization_rate": 0.0,
        "chronic_absence_rate": 0.0,
        "incident_followup_sla": 0.0,
        "new_enrollments": 0,
    }

    for kg_id in target_kindergarten_ids:
        gce_score, _ = KPIService.compute_governance_score(db, kg_id, period_start, period_end)
        totals["gce_score"] += gce_score
        totals["attendance_rate"] += KPIService.compute_attendance_rate(db, kg_id, period_start, period_end)
        totals["incident_rate"] += KPIService.compute_incident_rate(db, kg_id, period_start, period_end)
        totals["serious_incident_rate"] += KPIService.compute_serious_incident_rate(db, kg_id, period_start, period_end)
        totals["ratio_compliance"] += KPIService.compute_ratio_compliance(db, kg_id, period_start, period_end)
        totals["training_completion_rate"] += KPIService.compute_training_completion_rate(db, kg_id, period_start, period_end)
        totals["report_submission_rate"] += KPIService.compute_report_submission_rate(db, kg_id, period_start, period_end)
        totals["capacity_utilization_rate"] += KPIService.compute_capacity_utilization_rate(db, kg_id, period_start, period_end)
        totals["chronic_absence_rate"] += KPIService.compute_chronic_absence_rate(db, kg_id, period_start, period_end)
        totals["incident_followup_sla"] += KPIService.compute_incident_followup_sla_compliance(db, kg_id, period_start, period_end)
        totals["new_enrollments"] += KPIService.compute_new_enrollments(db, kg_id, period_start, period_end)

    total_active_enrollments = (
        db.query(func.count(models.EnrollmentApplication.id))
        .filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .scalar()
        or 0
    )

    def _determine_band(value: float, target: Optional[models.KPITarget], lower_is_better: bool) -> str:
        resolved = float(value)
        if target:
            limit = target.target_value
            if lower_is_better:
                if resolved <= limit:
                    return "GREEN"
                if resolved <= limit * 1.1:
                    return "AMBER"
                return "RED"
            if resolved >= limit:
                return "GREEN"
            if resolved >= limit * 0.8:
                return "AMBER"
            return "RED"
        if lower_is_better:
            if resolved <= 1.0:
                return "GREEN"
            if resolved <= 2.0:
                return "AMBER"
            return "RED"
        if resolved >= 80.0:
            return "GREEN"
        if resolved >= 60.0:
            return "AMBER"
        return "RED"

    LOWER_IS_BETTER = {
        "incident_rate",
        "serious_incident_rate",
        "chronic_absence_rate",
    }

    def _create_card(value: float, kpi_name: str, unit: Optional[str], is_percentage: bool) -> KPICardData:
        target = KPIService.get_kpi_target(db, kpi_name, single_kindergarten_id, period_end)
        lower_is_better = kpi_name in LOWER_IS_BETTER
        band = _determine_band(value, target, lower_is_better)
        alert = "threshold_breached" if band == "RED" else None
        return KPICardData(
            value=round(value, 2),
            unit="%" if is_percentage else unit,
            band=band,
            alert=alert,
        )

    def _next_period_start(dt: date) -> date:
        if granularity == "daily":
            return dt + timedelta(days=1)
        if granularity == "weekly":
            return dt + timedelta(weeks=1)
        if dt.month == 12:
            return date(dt.year + 1, 1, 1)
        return date(dt.year, dt.month + 1, 1)

    def _build_trend(
        compute_fn: Callable[[Session, int, date, date], float],
        aggregate: str = "average",
    ) -> List[TrendDataPoint]:
        points: List[TrendDataPoint] = []
        current = period_start
        while current <= period_end:
            next_start = _next_period_start(current)
            window_end = min(period_end, next_start - timedelta(days=1))
            if window_end < current:
                window_end = current
            total_value = 0.0
            for kg_id in target_kindergarten_ids:
                total_value += compute_fn(db, kg_id, current, window_end)
            if aggregate == "average" and kindergarten_count:
                value = round(total_value / kindergarten_count, 2)
            else:
                value = round(total_value, 2)
            points.append(TrendDataPoint(date=current, value=value))
            current = next_start
        return points

    student_distribution_queries = db.query(
        models.Class.name_ar,
        func.count(models.EnrollmentApplication.id),
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.class_id == models.Class.id,
    ).filter(
        models.Class.kindergarten_id.in_(target_kindergarten_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    ).group_by(models.Class.name_ar)
    student_distribution_results = student_distribution_queries.all()
    if not student_distribution_results:
        student_distribution_items = [
            StudentDistributionItem(label="KG1", value=0),
            StudentDistributionItem(label="KG2", value=0),
            StudentDistributionItem(label="Ø­Ø¶Ø§Ù†Ø©", value=0),
        ]
    else:
        student_distribution_items = [
            StudentDistributionItem(label=label, value=count)
            for label, count in student_distribution_results
        ]

    def _build_governance_rankings(limit: int = 5) -> Tuple[List[TopBottomPerformer], List[TopBottomPerformer]]:
        enriched = []
        for kg in kindergarten_records:
            score, _ = KPIService.compute_governance_score(db, kg.id, period_start, period_end)
            enriched.append(
                {
                    "kg": kg,
                    "score": round(score, 2),
                }
            )
        sorted_desc = sorted(
            enriched,
            key=lambda item: (-item["score"], item["kg"].id),
        )
        sorted_asc = sorted(
            enriched,
            key=lambda item: (item["score"], item["kg"].id),
        )

        def _unique(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            seen_ids = set()
            deduped: List[Dict[str, Any]] = []
            for entry in items:
                kg_id = entry["kg"].id
                if kg_id in seen_ids:
                    continue
                seen_ids.add(kg_id)
                deduped.append(entry)
            return deduped

        def build_list(items: List[Dict[str, Any]]) -> List[TopBottomPerformer]:
            performers = []
            for rank_idx, entry in enumerate(_unique(items)[:limit], start=1):
                kg = entry["kg"]
                name = kg.name_ar if locale == "ar" else (kg.name_en or kg.name_ar)
                performers.append(
                    TopBottomPerformer(
                        id=kg.id,
                        name=name,
                        value=entry["score"],
                        rank=rank_idx,
                        governorate=kg.governorate,
                    )
                )
            return performers

        return build_list(sorted_desc), build_list(sorted_asc)

    top_performers, low_performers = _build_governance_rankings()

    selected_governorate_value = selected_governorate
    if not selected_governorate_value and single_kindergarten_id:
        fallback_kg = next(
            (kg for kg in kindergarten_records if kg.id == single_kindergarten_id),
            None,
        )
        if fallback_kg and fallback_kg.governorate:
            selected_governorate_value = fallback_kg.governorate
    alerts: List[AlertsSummary] = []
    today = date.today()
    for kg in kindergarten_records:
        if kg.license_valid_until:
            if kg.license_valid_until < today:
                alerts.append(
                    AlertsSummary(
                        type="REGULATORY",
                        message=f"{kg.name_ar or 'Kindergarten'} license expired on {kg.license_valid_until}",
                        priority="high",
                        entity_id=kg.id,
                    )
                )
            elif kg.license_valid_until <= today + timedelta(days=30):
                alerts.append(
                    AlertsSummary(
                        type="REGULATORY",
                        message=f"{kg.name_ar or 'Kindergarten'} license expires on {kg.license_valid_until}",
                        priority="medium",
                        entity_id=kg.id,
                    )
                )

    avg_incident_rate = round(totals["incident_rate"] / kindergarten_count, 2)
    if avg_incident_rate > 5.0:
        alerts.append(
            AlertsSummary(
                type="KPI",
                message=f"Average incident rate {avg_incident_rate}% exceeds threshold",
                priority="medium",
            )
        )

    attendance_trend = _build_trend(KPIService.compute_attendance_rate)
    incidents_trend = _build_trend(KPIService.compute_incident_rate)
    enrollment_trend = _build_trend(KPIService.compute_new_enrollments, aggregate="sum")
    gcei_trend = _build_trend(
        lambda session, kg_id, start, end: KPIService.compute_governance_score(session, kg_id, start, end)[0]
    )

    return KPIDashboardResponse(
        period_start=period_start,
        period_end=period_end,
        kindergarten_id=single_kindergarten_id,
        governorate=selected_governorate_value,
        overall_gcei=_create_card(
            round(totals["gce_score"] / kindergarten_count, 2),
            "governance_score",
            "%",
            True,
        ),
        attendance_rate=_create_card(
            round(totals["attendance_rate"] / kindergarten_count, 2),
            "attendance_rate",
            "%",
            True,
        ),
        ratio_compliance=_create_card(
            round(totals["ratio_compliance"] / kindergarten_count, 2),
            "ratio_compliance",
            "%",
            True,
        ),
        training_completion_rate=_create_card(
            round(totals["training_completion_rate"] / kindergarten_count, 2),
            "training_completion_rate",
            "%",
            True,
        ),
        report_submission_rate=_create_card(
            round(totals["report_submission_rate"] / kindergarten_count, 2),
            "report_submission_rate",
            "%",
            True,
        ),
        incident_rate=_create_card(
            avg_incident_rate,
            "incident_rate",
            "per 100 child-days",
            False,
        ),
        serious_incident_rate=_create_card(
            round(totals["serious_incident_rate"] / kindergarten_count, 2),
            "serious_incident_rate",
            "per 100 child-days",
            False,
        ),
        incident_followup_sla=_create_card(
            round(totals["incident_followup_sla"] / kindergarten_count, 2),
            "incident_followup_sla",
            "%",
            True,
        ),
        chronic_absence_rate=_create_card(
            round(totals["chronic_absence_rate"] / kindergarten_count, 2),
            "chronic_absence_rate",
            "%",
            True,
        ),
        capacity_utilization_rate=_create_card(
            round(totals["capacity_utilization_rate"] / kindergarten_count, 2),
            "capacity_utilization_rate",
            "%",
            True,
        ),
        active_enrollments=KPICardData(value=total_active_enrollments, unit="children"),
        new_enrollments=KPICardData(value=totals["new_enrollments"], unit="children"),
        student_distribution=student_distribution_items,
        top_performers_by_gcei=top_performers,
        low_performers_by_gcei=low_performers,
        attendance_trend=attendance_trend,
        incidents_trend=incidents_trend,
        enrollment_trend=enrollment_trend,
        gcei_trend=gcei_trend,
        alerts=alerts,
    )


@router.get("/kpi/filters", response_model=KpiFiltersResponse)
def get_kpi_filters(
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """
    Get filter options for KPI dashboard.
    Returns unique kindergartens and governorates with localization support.
    """
    # Get unique kindergartens
    kindergartens_query = db.query(
        models.Kindergarten.id,
        models.Kindergarten.name_ar,
        models.Kindergarten.name_en
    ).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).distinct()

    kindergartens = []
    for kg in kindergartens_query:
        name = kg.name_ar if locale == "ar" else (kg.name_en or kg.name_ar)
        kindergartens.append(FilterOption(id=kg.id, name=name))

    # Get governorates from config with localization
    from config import settings
    governorates = []
    for i, gov_ar in enumerate(settings.JORDAN_GOVERNORATES):
        name = gov_ar if locale == "ar" else settings.JORDAN_GOVERNORATES_ENGLISH[i]
        governorates.append(FilterOption(id=i+1, name=name))

    return KpiFiltersResponse(
        kindergartens=kindergartens,
        governorates=governorates
    )
