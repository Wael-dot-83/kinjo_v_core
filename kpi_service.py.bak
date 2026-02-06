"""
KPI and Governance Reporting Services
Implements all KPIs from Section 5 of the SRS
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, literal_column
from pydantic import BaseModel

import models
from database import get_db
from dependencies import get_current_user
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

    alerts: List[Dict] # Simplified for now


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
            "labels": ["KG1", "KG2", "حضانة"],
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
    
    
    
        
    
    
    
            def generate_monthly_snapshots_endpoint(
    
    
    
        
    
    
    
                kindergarten_id: int = Query(..., description="Kindergarten ID for which to generate snapshots."),
    
    
    
        
    
    
    
                month: str = Query(..., regex=r"^\d{4}-\d{2}$", description="Month for which to generate snapshots (YYYY-MM)."),
    
    
    
        
    
    
    
                current_user: models.User = Depends(get_current_user),
    
    
    
        
    
    
    
                db: Session = Depends(get_db)
    
    
    
        
    
    
    
            ):
    
    
    
        
    
    
    
                """
    
    
    
        
    
    
    
                Generates immutable monthly KPI snapshots for a specified kindergarten and month.
    
    
    
        
    
    
    
                Requires Admin role.
    
    
    
        
    
    
    
                """
    
    
    
        
    
    
    
                # RBAC check
    
    
    
        
    
    
    
                if current_user.role != models.UserRole.ADMIN:
    
    
    
        
    
    
    
                    raise HTTPException(status_code=403, detail="Access denied. Admin role required.")
    
    
    
        
    
    
    
            
    
    
    
        
    
    
    
                # Parse month string to date object (first day of the month)
    
    
    
        
    
    
    
                try:
    
    
    
        
    
    
    
                    snapshot_month = datetime.strptime(month, "%Y-%m").date()
    
    
    
        
    
    
    
                except ValueError:
    
    
    
        
    
    
    
                    raise HTTPException(status_code=400, detail="Invalid month format. Expected YYYY-MM.")
    
    
    
        
    
    
    
            
    
    
    
        
    
    
    
                # Ensure kindergarten exists
    
    
    
        
    
    
    
                kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    
    
    
        
    
    
    
                if not kg:
    
    
    
        
    
    
    
                    raise HTTPException(status_code=404, detail="Kindergarten not found.")
    
    
    
        
    
    
    
            
    
    
    
        
    
    
    
                snapshots = KPIService.generate_monthly_snapshots(db, kindergarten_id, snapshot_month)
    
    
    
        
    
    
    
            
    
    
    
        
    
    
    
                return MonthlySnapshotResponse(
    
    
    
        
    
    
    
                    message=f"Generated {len(snapshots)} monthly KPI snapshots for kindergarten {kindergarten_id} for {month}.",
    
    
    
        
    
    
    
                    snapshots_created=len(snapshots),
    
    
    
        
    
    
    
                    kindergarten_id=kindergarten_id,
    
    
    
        
    
    
    
                    month=snapshot_month
    
    
    
        
    
    
    
                )
    
    
    
        
    
    
    
            
    
    
    
        
    
    