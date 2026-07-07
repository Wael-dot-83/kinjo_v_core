"""
Manager Analytics Service - Operational KPIs & Predictive Indicators

Provides manager-scoped analytics including:
- Operational KPIs (enrollment, attendance, incidents, capacity)
- Predictive indicators (forecasting, anomaly detection)
- Drill-down navigation (KG -> Classes -> Children)
"""

from typing import Optional, List, Dict, Tuple
from datetime import date, datetime, timedelta
from utils.time_utils import today_amman as _today
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import logging
import math

import models

logger = logging.getLogger(__name__)

# Attendance statuses that count as the child having attended (B1).
_ATTENDED_STATUSES = (models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE)


class ManagerAnalyticsService:
    """
    Provides analytics calculations scoped to a manager's kindergarten.
    All metrics are computed for a single kindergarten only.
    """

    @staticmethod
    def _count_operating_days(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date,
    ) -> int:
        """Number of *operating* days in [start_date, end_date] for a kindergarten (B2).

        A day is operating when OperatingCalendar says so explicitly; otherwise
        it defaults to open on the Jordan school week (Sun–Thu) and closed on
        Friday (weekday 4) and Saturday (weekday 5). This mirrors the KPI engine
        so manager and admin analytics agree.
        """
        if end_date < start_date:
            return 0
        rows = db.query(
            models.OperatingCalendar.date,
            models.OperatingCalendar.is_open,
        ).filter(
            models.OperatingCalendar.kindergarten_id == kindergarten_id,
            models.OperatingCalendar.date >= start_date,
            models.OperatingCalendar.date <= end_date,
        ).all()
        explicit = {row[0]: bool(row[1]) for row in rows}

        count = 0
        cursor = start_date
        while cursor <= end_date:
            if cursor in explicit:
                is_open = explicit[cursor]
            else:
                is_open = cursor.weekday() not in (4, 5)
            if is_open:
                count += 1
            cursor += timedelta(days=1)
        return count

    @staticmethod
    def _compute_daily_attendance_rates(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date,
    ) -> Dict[date, float]:
        """Per-day attendance rate (%) for every day in [start_date, end_date].

        Equivalent to calling compute_attendance_rate(db, kg, d, d) for each day
        but with a fixed small number of queries instead of one set per day (B3):
        one for active enrollments, one grouped attended-count query, one for the
        calendar. Closed days and days with no active enrollments are 0.0, and
        every day in the range is present (missing attendance => 0.0).
        """
        result: Dict[date, float] = {}
        if end_date < start_date:
            return result

        active = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).scalar() or 0

        attended_by_day = {}
        if active:
            rows = db.query(
                models.AttendanceLog.date,
                func.count(models.AttendanceLog.id),
            ).join(
                models.Child
            ).join(
                models.EnrollmentApplication
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kindergarten_id,
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date,
                models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
            ).group_by(models.AttendanceLog.date).all()
            attended_by_day = {row[0]: row[1] for row in rows}

        cal = db.query(
            models.OperatingCalendar.date,
            models.OperatingCalendar.is_open,
        ).filter(
            models.OperatingCalendar.kindergarten_id == kindergarten_id,
            models.OperatingCalendar.date >= start_date,
            models.OperatingCalendar.date <= end_date,
        ).all()
        explicit = {row[0]: bool(row[1]) for row in cal}

        cursor = start_date
        while cursor <= end_date:
            is_open = explicit[cursor] if cursor in explicit else cursor.weekday() not in (4, 5)
            if active == 0 or not is_open:
                result[cursor] = 0.0
            else:
                fraction = attended_by_day.get(cursor, 0) / active
                fraction = max(0.0, min(1.0, fraction))
                result[cursor] = round(fraction * 100, 2)
            cursor += timedelta(days=1)
        return result

    @staticmethod
    def compute_enrollment_trend(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date,
        grouping: str = "daily"  # daily, weekly, monthly
    ) -> List[Dict]:
        """
        Compute enrollment trend over period.
        Returns list of {date, new_enrollments, total_active, cumulative}
        """
        # Get all enrollments in date range
        enrollments = db.query(
            models.EnrollmentApplication.created_at,
            models.EnrollmentApplication.status
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.created_at >= start_date,
            models.EnrollmentApplication.created_at <= end_date
        ).all()

        # Group by period
        if grouping == "daily":
            periods = {}
            for enrollment in enrollments:
                key = enrollment.created_at.date()
                if key not in periods:
                    periods[key] = {"new": 0, "active": 0}
                periods[key]["new"] += 1
                if enrollment.status == models.EnrollmentStatus.ACTIVE:
                    periods[key]["active"] += 1

            # Fill in missing days
            result = []
            current = start_date
            cumulative_active = 0
            while current <= end_date:
                if current in periods:
                    cumulative_active += periods[current]["active"]
                result.append({
                    "date": current.isoformat(),
                    "new_enrollments": periods.get(current, {}).get("new", 0),
                    "active_enrollments": periods.get(current, {}).get("active", 0),
                    "cumulative_active": cumulative_active
                })
                current += timedelta(days=1)
            return result
        else:
            # For weekly/monthly, aggregate
            return []

    @staticmethod
    def compute_attendance_rate(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> float:
        """
        Compute attendance rate: (check-ins / expected attendances) * 100
        Expected = active enrollments * operating days
        """
        # Count active enrollments in this kindergarten
        active_enrollments = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        if active_enrollments == 0:
            return 0.0

        # Numerator: only PRESENT/LATE count as attended. ABSENT and EXCUSED must
        # not inflate the rate (B1).
        attended = db.query(
            func.count(models.AttendanceLog.id)
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date,
            models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
        ).scalar() or 0

        # Denominator: active enrollments * *operating* days (open days from
        # OperatingCalendar, not raw calendar days). Closed days are excluded (B2).
        operating_days = ManagerAnalyticsService._count_operating_days(
            db, kindergarten_id, start_date, end_date
        )
        expected_attendance = active_enrollments * operating_days
        if expected_attendance == 0:
            return 0.0

        # Validate/clamp the underlying fraction to [0, 1]; log anomalies (e.g.
        # duplicate logs) rather than returning an impossible >100% rate.
        fraction = attended / expected_attendance
        if fraction < 0.0 or fraction > 1.0:
            logger.warning(
                "Attendance rate out of range for kg=%s [%s..%s]: "
                "attended=%s expected=%s fraction=%.3f",
                kindergarten_id, start_date, end_date,
                attended, expected_attendance, fraction,
            )
            fraction = max(0.0, min(1.0, fraction))
        return round(fraction * 100, 2)

    @staticmethod
    def compute_incident_rate(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date,
        per_children: int = 100
    ) -> float:
        """
        Compute incident rate per 100 children.
        Rate = (incidents / active_enrollments) * per_children
        """
        # Count active enrollments
        active_enrollments = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        if active_enrollments == 0:
            return 0.0

        # Count incidents in date range
        incidents = db.query(
            func.count(models.Incident.id)
        ).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            models.Incident.occurred_at >= start_date,
            models.Incident.occurred_at <= end_date
        ).scalar() or 0

        incident_rate = (incidents / active_enrollments) * per_children
        return round(incident_rate, 2)

    @staticmethod
    def compute_absenteeism_rate(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> float:
        """
        Compute absenteeism rate: (absences / expected) * 100
        """
        active_enrollments = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        if active_enrollments == 0:
            return 0.0

        # Count absences (AttendanceStatus.ABSENT)
        absences = db.query(
            func.count(models.AttendanceLog.id)
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.AttendanceLog.status == models.AttendanceStatus.ABSENT,
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date
        ).scalar() or 0

        operating_days = (end_date - start_date).days + 1
        expected = active_enrollments * operating_days

        if expected == 0:
            return 0.0

        absenteeism_rate = (absences / expected) * 100
        return round(absenteeism_rate, 2)

    @staticmethod
    def compute_class_capacity_utilization(
        db: Session,
        kindergarten_id: int
    ) -> float:
        """
        Compute average class capacity utilization: sum(enrolled) / sum(capacity) * 100
        """
        # Sum total capacity
        total_capacity = db.query(
            func.sum(models.Class.capacity_total)
        ).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).scalar() or 0

        if total_capacity == 0:
            return 0.0

        # Sum enrolled children
        total_enrolled = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        utilization = (total_enrolled / total_capacity) * 100
        return round(utilization, 2)

    @staticmethod
    def compute_supervisor_workload(
        db: Session,
        kindergarten_id: int
    ) -> List[Dict]:
        """
        Compute supervisor workload: children per supervisor, reports per day
        Returns list of {supervisor_id, name, children_count, classes_count, reports_per_day}
        """
        supervisors = db.query(models.User).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE
        ).all()

        today = _today()
        sup_ids = [s.id for s in supervisors]
        if not sup_ids:
            return []

        children_by_sup = dict(
            db.query(models.Class.supervisor_id, func.count(models.Child.id))
            .join(models.EnrollmentApplication, models.EnrollmentApplication.class_id == models.Class.id)
            .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
            .filter(
                models.Class.supervisor_id.in_(sup_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .group_by(models.Class.supervisor_id)
            .all()
        )

        classes_by_sup = dict(
            db.query(models.Class.supervisor_id, func.count(models.Class.id))
            .filter(
                models.Class.supervisor_id.in_(sup_ids),
                models.Class.is_active == True,
            )
            .group_by(models.Class.supervisor_id)
            .all()
        )

        reports_today_by_sup = dict(
            db.query(models.DailyReport.submitted_by, func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.submitted_by.in_(sup_ids),
                models.DailyReport.date == today,
            )
            .group_by(models.DailyReport.submitted_by)
            .all()
        )

        result = []
        for supervisor in supervisors:
            children_count = children_by_sup.get(supervisor.id, 0)
            classes_count = classes_by_sup.get(supervisor.id, 0)
            reports_today = reports_today_by_sup.get(supervisor.id, 0)
            result.append({
                "supervisor_id": supervisor.id,
                "name": supervisor.username,
                "children_count": children_count,
                "classes_count": classes_count,
                "children_per_supervisor": children_count,
                "reports_submitted_today": reports_today
            })

        return result

    @staticmethod
    def compute_attendance_forecast(
        db: Session,
        kindergarten_id: int,
        lookback_days: int = 30,
        forecast_days: int = 7
    ) -> Dict:
        """
        Simple linear regression forecast for attendance.
        
        Returns {
            historical: [{date, rate}],
            forecast: [{date, predicted_rate, confidence_interval}],
            trend: "increasing|decreasing|stable"
        }
        """
        today = _today()
        start_date = today - timedelta(days=lookback_days)

        # Get historical attendance rates — one batched query set, not one per
        # day (B3).
        daily = ManagerAnalyticsService._compute_daily_attendance_rates(
            db, kindergarten_id, start_date, today
        )
        historical = []
        current = start_date
        rates = []
        while current <= today:
            rate = daily.get(current, 0.0)
            historical.append({"date": current.isoformat(), "rate": rate})
            rates.append(rate)
            current += timedelta(days=1)

        # Simple linear regression
        if len(rates) < 2:
            return {
                "historical": historical,
                "forecast": [],
                "trend": "insufficient_data"
            }

        n = len(rates)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(rates) / n

        slope = sum((x[i] - x_mean) * (rates[i] - y_mean) for i in range(n)) / sum(
            (x[i] - x_mean) ** 2 for i in range(n)
        )
        intercept = y_mean - slope * x_mean

        # Generate forecast
        forecast = []
        for i in range(1, forecast_days + 1):
            future_x = n + i - 1
            predicted = slope * future_x + intercept
            # Clamp to 0-100
            predicted = max(0, min(100, predicted))
            forecast_date = today + timedelta(days=i)

            # Simple confidence interval (±5%)
            forecast.append({
                "date": forecast_date.isoformat(),
                "predicted_rate": round(predicted, 1),
                "confidence_interval": {
                    "lower": round(max(0, predicted - 5), 1),
                    "upper": round(min(100, predicted + 5), 1)
                }
            })

        # Determine trend
        if slope > 0.5:
            trend = "increasing"
        elif slope < -0.5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "historical": historical,
            "forecast": forecast,
            "trend": trend,
            "slope": round(slope, 3)
        }

    @staticmethod
    def detect_anomalies(
        db: Session,
        kindergarten_id: int,
        lookback_days: int = 30,
        threshold: float = 2.0  # Standard deviations
    ) -> Dict:
        """
        Detect anomalies in attendance using z-score method.
        
        Returns {
            anomalies: [{date, metric, value, z_score, severity}],
            baseline_mean: float,
            baseline_std: float
        }
        """
        today = _today()
        start_date = today - timedelta(days=lookback_days)

        # Collect attendance rates — one batched query set, not one per day (B3).
        daily = ManagerAnalyticsService._compute_daily_attendance_rates(
            db, kindergarten_id, start_date, today
        )
        current = start_date
        rates = []
        while current <= today:
            rates.append({"date": current, "rate": daily.get(current, 0.0)})
            current += timedelta(days=1)

        if len(rates) < 3:
            return {
                "anomalies": [],
                "baseline_mean": 0,
                "baseline_std": 0,
                "status": "insufficient_data"
            }

        # Calculate mean and std deviation
        values = [r["rate"] for r in rates]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return {
                "anomalies": [],
                "baseline_mean": round(mean, 2),
                "baseline_std": 0,
                "status": "no_variation"
            }

        # Detect anomalies
        anomalies = []
        for record in rates:
            z_score = (record["rate"] - mean) / std_dev
            if abs(z_score) > threshold:
                severity = "critical" if abs(z_score) > 3 else "warning"
                anomalies.append({
                    "date": record["date"].isoformat(),
                    "metric": "attendance_rate",
                    "value": record["rate"],
                    "z_score": round(z_score, 2),
                    "severity": severity
                })

        return {
            "anomalies": anomalies,
            "baseline_mean": round(mean, 2),
            "baseline_std": round(std_dev, 2),
            "threshold": threshold,
            "status": "ok"
        }

    @staticmethod
    def get_drilldown_by_class(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """
        Drill-down view: KG -> Classes -> Statistics
        Returns list of classes with their KPIs
        """
        classes = db.query(models.Class).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).all()

        class_ids = [c.id for c in classes]
        if not class_ids:
            return []

        sup_id_set = {c.supervisor_id for c in classes if c.supervisor_id}
        supervisors_by_id = {
            u.id: u for u in db.query(models.User).filter(models.User.id.in_(sup_id_set)).all()
        } if sup_id_set else {}

        enrolled_by_class = dict(
            db.query(models.EnrollmentApplication.class_id, func.count(models.EnrollmentApplication.id))
            .filter(
                models.EnrollmentApplication.class_id.in_(class_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .group_by(models.EnrollmentApplication.class_id)
            .all()
        )

        attendance_by_class = dict(
            db.query(models.EnrollmentApplication.class_id, func.count(models.AttendanceLog.id))
            .select_from(models.AttendanceLog)
            .join(models.Child, models.Child.id == models.AttendanceLog.child_id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
            .filter(
                models.EnrollmentApplication.class_id.in_(class_ids),
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date,
            )
            .group_by(models.EnrollmentApplication.class_id)
            .all()
        )

        incidents_by_class = dict(
            db.query(models.Incident.class_id, func.count(models.Incident.id))
            .filter(
                models.Incident.class_id.in_(class_ids),
                models.Incident.occurred_at >= start_date,
                models.Incident.occurred_at <= end_date,
            )
            .group_by(models.Incident.class_id)
            .all()
        )

        operating_days = (end_date - start_date).days + 1

        result = []
        for class_obj in classes:
            supervisor = supervisors_by_id.get(class_obj.supervisor_id)
            enrolled_count = enrolled_by_class.get(class_obj.id, 0)
            attendance_logs = attendance_by_class.get(class_obj.id, 0)
            incidents = incidents_by_class.get(class_obj.id, 0)

            expected = enrolled_count * operating_days
            attendance_rate = (attendance_logs / expected * 100) if expected > 0 else 0
            utilization = (enrolled_count / class_obj.capacity_total * 100) if class_obj.capacity_total > 0 else 0

            result.append({
                "class_id": class_obj.id,
                "class_name": class_obj.name_ar or class_obj.name_en,
                "supervisor_id": supervisor.id if supervisor else None,
                "supervisor_name": supervisor.username if supervisor else "Unassigned",
                "age_range": f"{class_obj.min_age_months}-{class_obj.max_age_months} months",
                "capacity": class_obj.capacity_total,
                "enrolled": enrolled_count,
                "utilization_percent": round(utilization, 1),
                "attendance_rate": round(attendance_rate, 1),
                "incidents": incidents,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat()
            })

        return result

    @staticmethod
    def get_drilldown_by_supervisor(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """
        Drill-down view: KG -> Supervisors -> Statistics
        Returns list of supervisors with their KPIs
        """
        supervisors = db.query(models.User).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE
        ).all()

        sup_ids = [s.id for s in supervisors]
        if not sup_ids:
            return []

        children_by_sup = dict(
            db.query(models.Class.supervisor_id, func.count(models.Child.id))
            .join(models.EnrollmentApplication, models.EnrollmentApplication.class_id == models.Class.id)
            .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
            .filter(
                models.Class.supervisor_id.in_(sup_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .group_by(models.Class.supervisor_id)
            .all()
        )

        classes_by_sup = dict(
            db.query(models.Class.supervisor_id, func.count(models.Class.id))
            .filter(
                models.Class.supervisor_id.in_(sup_ids),
                models.Class.is_active == True,
            )
            .group_by(models.Class.supervisor_id)
            .all()
        )

        reports_by_sup = dict(
            db.query(models.DailyReport.submitted_by, func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.submitted_by.in_(sup_ids),
                models.DailyReport.date >= start_date,
                models.DailyReport.date <= end_date,
            )
            .group_by(models.DailyReport.submitted_by)
            .all()
        )

        incidents_by_sup = dict(
            db.query(models.Class.supervisor_id, func.count(models.Incident.id))
            .join(models.Incident, models.Incident.class_id == models.Class.id)
            .filter(
                models.Class.supervisor_id.in_(sup_ids),
                models.Incident.occurred_at >= start_date,
                models.Incident.occurred_at <= end_date,
            )
            .group_by(models.Class.supervisor_id)
            .all()
        )

        result = []
        for supervisor in supervisors:
            result.append({
                "supervisor_id": supervisor.id,
                "supervisor_name": supervisor.username,
                "classes_managed": classes_by_sup.get(supervisor.id, 0),
                "children_supervised": children_by_sup.get(supervisor.id, 0),
                "reports_submitted": reports_by_sup.get(supervisor.id, 0),
                "incidents_reported": incidents_by_sup.get(supervisor.id, 0),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat()
            })

        return result


# Export for use in routers
__all__ = ['ManagerAnalyticsService']
