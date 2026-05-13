"""
KPI and Governance Reporting Services
Implements all KPIs from Section 5 of the SRS
"""
from fastapi import APIRouter, Depends, Query
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel

import models
from database import get_db
from dependencies import get_current_user
import validators

router = APIRouter()

class KPISummaryResponse(BaseModel):
    period_start: date
    period_end: date
    attendance_rate: float
    incident_rate: float
    serious_incident_rate: float
    ratio_compliance: float
    gqi_score: float

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
    def compute_parent_satisfaction(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Parent satisfaction score (0-100) derived from NPS survey responses.
        Calculates average NPS score (0-10 scale) converted to 0-100 percentage.
        Falls back to 75.0 when no survey data is available for the period.
        """
        avg_score = db.query(func.avg(models.SurveyResponse.nps_score)).join(
            models.Survey,
            models.SurveyResponse.survey_id == models.Survey.id
        ).filter(
            models.Survey.kindergarten_id == kindergarten_id,
            models.Survey.deleted_at.is_(None),
            models.SurveyResponse.nps_score.isnot(None),
            models.Survey.start_date <= period_end,
            models.Survey.end_date >= period_start
        ).scalar()

        if avg_score is None:
            return 75.0  # Neutral default when no survey data

        return round(float(avg_score) * 10.0, 2)

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
        - Parent satisfaction (from NPS surveys)
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

        parent_satisfaction = KPIService.compute_parent_satisfaction(
            db, kindergarten_id, period_start, period_end
        )

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
    def compute_governance_quality_index(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        GQI: weighted mix of:
        - Ratio compliance
        - Checklist compliance (placeholder)
        - Regulatory status (placeholder)
        - Training coverage (placeholder)
        - Incident follow-up SLA
        """
        # Weights (configurable in production)
        weights = {
            'ratio_compliance': 0.30,
            'checklist_compliance': 0.20,
            'regulatory_status': 0.20,
            'training_coverage': 0.15,
            'incident_followup_sla': 0.15
        }

        # Compute individual metrics
        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )

        incident_followup_sla = KPIService.compute_incident_followup_sla_compliance(
            db, kindergarten_id, period_start, period_end
        )

        # Improved placeholders - check actual data availability
        checklist_compliance = KPIService.compute_checklist_compliance(db, kindergarten_id, period_start, period_end)
        regulatory_status = KPIService.compute_regulatory_status(db, kindergarten_id)
        training_coverage = KPIService.compute_training_coverage(db, kindergarten_id, period_start, period_end)

        # Weighted average
        gqi = (
            ratio_compliance * weights['ratio_compliance'] +
            checklist_compliance * weights['checklist_compliance'] +
            regulatory_status * weights['regulatory_status'] +
            training_coverage * weights['training_coverage'] +
            incident_followup_sla * weights['incident_followup_sla']
        )

        return round(gqi, 2)

    @staticmethod
    def compute_checklist_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Checklist compliance % - placeholder for daily safety/operational checklists
        """
        # For now, return 85% as baseline
        # In production, would check completed checklists vs required
        return 85.0

    @staticmethod
    def compute_regulatory_status(
        db: Session,
        kindergarten_id: int
    ) -> float:
        """
        Regulatory compliance % based on license validity and inspections
        """
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if not kg:
            return 0.0

        score = 100.0

        # Check license validity
        if kg.license_valid_until and kg.license_valid_until < date.today():
            score -= 50.0  # Expired license
        elif kg.license_valid_until and (kg.license_valid_until - date.today()).days < 30:
            score -= 20.0  # Expires soon

        # Check license status
        if hasattr(kg, 'license_status') and kg.license_status != 'active':
            score -= 30.0

        return max(0.0, score)

    @staticmethod
    def compute_training_coverage(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Training coverage % - staff training completion rate
        """
        # For now, return 90% as baseline
        # In production, would check training records vs requirements
        return 90.0

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


@router.get("/kpi/network-summary")
def get_kpi_network_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Network-wide KPI aggregate across all active kindergartens (Admin only)"""
    validators.validate_admin_role(current_user)

    if not start_date or not end_date:
        today = date.today()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    active_kg_ids = [
        row[0] for row in db.query(models.Kindergarten.id).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
    ]

    if not active_kg_ids:
        return {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "kindergarten_count": 0,
            "avg_attendance_rate": 0.0,
            "avg_incident_rate": 0.0,
            "avg_serious_incident_rate": 0.0,
            "avg_ratio_compliance": 0.0,
            "avg_gqi_score": 0.0,
            "per_kindergarten": []
        }

    per_kg = []
    for kg_id in active_kg_ids:
        kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
        att = KPIService.compute_attendance_rate(db, kg_id, start_date, end_date)
        inc = KPIService.compute_incident_rate(db, kg_id, start_date, end_date)
        ser = KPIService.compute_serious_incident_rate(db, kg_id, start_date, end_date)
        ratio = KPIService.compute_ratio_compliance(db, kg_id, start_date, end_date)
        gqi = KPIService.compute_governance_quality_index(db, kg_id, start_date, end_date)
        _, band = KPIService.compute_governance_score(db, kg_id, start_date, end_date)
        per_kg.append({
            "kindergarten_id": kg_id,
            "kindergarten_name": kg.name_ar if kg else "",
            "governorate": kg.governorate if kg else "",
            "attendance_rate": att,
            "incident_rate": inc,
            "serious_incident_rate": ser,
            "ratio_compliance": ratio,
            "gqi_score": gqi,
            "governance_band": band
        })

    n = len(per_kg)
    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "kindergarten_count": n,
        "avg_attendance_rate": round(sum(k["attendance_rate"] for k in per_kg) / n, 2),
        "avg_incident_rate": round(sum(k["incident_rate"] for k in per_kg) / n, 4),
        "avg_serious_incident_rate": round(sum(k["serious_incident_rate"] for k in per_kg) / n, 4),
        "avg_ratio_compliance": round(sum(k["ratio_compliance"] for k in per_kg) / n, 2),
        "avg_gqi_score": round(sum(k["gqi_score"] for k in per_kg) / n, 2),
        "per_kindergarten": per_kg
    }
