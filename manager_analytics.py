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
import validators

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

        Each value equals ``KPIService.compute_attendance_rate(db, kg, d, d)`` — it
        reuses the canonical working-day / expected-child-day / attended-child-day
        definitions so the forecast & anomaly series stay consistent with the
        headline attendance KPI — but computes the whole range with a bounded
        number of queries (3) instead of one set per day (B3). Closed days and
        days with no expected child-days are 0.0, and every day in the range is
        present (missing attendance => 0.0).
        """
        from collections import defaultdict
        from kpi_service import KPIService

        result: Dict[date, float] = {}
        if end_date < start_date:
            return result

        # Query 1: working days (Jordan Sun–Thu + explicit OperatingCalendar).
        working_set = set(
            KPIService._list_working_days(db, kindergarten_id, start_date, end_date)
        )
        # Query 2: active enrollments overlapping the window, with effective
        # per-child date ranges (a child may hold several overlapping rows).
        enrollments = KPIService._get_overlapping_active_enrollments(
            db, kindergarten_id, start_date, end_date
        )
        child_windows: Dict[int, list] = defaultdict(list)
        for child_id, eff_start, eff_end in enrollments:
            child_windows[child_id].append((eff_start, eff_end))

        # Query 3: attended (PRESENT/LATE) child-days grouped by (date, child).
        attended_by_day_child: Dict[Tuple[date, int], int] = {}
        child_ids = list(child_windows.keys())
        if child_ids:
            rows = db.query(
                models.AttendanceLog.date,
                models.AttendanceLog.child_id,
                func.count(models.AttendanceLog.id),
            ).filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date,
                models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
            ).group_by(models.AttendanceLog.date, models.AttendanceLog.child_id).all()
            attended_by_day_child = {(row[0], row[1]): row[2] for row in rows}

        cursor = start_date
        while cursor <= end_date:
            if cursor not in working_set:
                result[cursor] = 0.0
                cursor += timedelta(days=1)
                continue
            # expected = enrollment rows whose effective window covers this day;
            # attended = PRESENT/LATE logs on this day for those same children.
            expected = 0
            attended = 0
            for child_id, windows in child_windows.items():
                covers = sum(1 for (s, e) in windows if s <= cursor <= e)
                if covers:
                    expected += covers
                    attended += attended_by_day_child.get((cursor, child_id), 0)
            result[cursor] = round(attended / expected * 100, 2) if expected else 0.0
            cursor += timedelta(days=1)
        return result

    @staticmethod
    def _supervisor_class_counts(db: Session, sup_ids):
        """(children_by_sup, classes_by_sup) for the given supervisors.

        Counts via active primary SupervisorAssignment rows (D1/B5). Shared by
        both supervisor-workload computations to avoid duplicated JOIN blocks.
        """
        SA = models.SupervisorAssignment
        primary = (SA.is_primary.is_(True), SA.deleted_at.is_(None))
        children_by_sup = dict(
            db.query(SA.supervisor_id, func.count(models.Child.id))
            .join(models.Class, models.Class.id == SA.class_id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.class_id == models.Class.id)
            .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
            .filter(
                SA.supervisor_id.in_(sup_ids), *primary,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .group_by(SA.supervisor_id)
            .all()
        )
        classes_by_sup = dict(
            db.query(SA.supervisor_id, func.count(models.Class.id))
            .join(models.Class, models.Class.id == SA.class_id)
            .filter(SA.supervisor_id.in_(sup_ids), *primary, models.Class.is_active == True)
            .group_by(SA.supervisor_id)
            .all()
        )
        return children_by_sup, classes_by_sup

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
        Compute attendance rate using the centralized KPIService logic.
        """
        from kpi_service import KPIService
        return KPIService.compute_attendance_rate(db, kindergarten_id, start_date, end_date)

    @staticmethod
    def compute_incident_rate(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date,
        per_children: int = 100  # retained for backward compatibility; unused
    ) -> float:
        """Compute incident rate using the centralized KPIService logic.

        NOTE: KPIService expresses this **per 1,000 attended child-days** (not the
        legacy per-100-children), to match kpi_standards.py thresholds. The
        ``per_children`` argument is ignored and kept only for call-site
        compatibility.
        """
        from kpi_service import KPIService
        return KPIService.compute_incident_rate(db, kindergarten_id, start_date, end_date)

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

        operating_days = ManagerAnalyticsService._count_operating_days(
            db, kindergarten_id, start_date, end_date
        )
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

        # Supervisor -> class counts come from active primary SupervisorAssignment
        # rows, not the retired Class.supervisor_id (D1/B5).
        children_by_sup, classes_by_sup = ManagerAnalyticsService._supervisor_class_counts(db, sup_ids)

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

        # class_id -> primary supervisor_id from SupervisorAssignment (D1/B5).
        primary_by_class = validators.active_primary_supervisor_map(db, class_ids)
        sup_id_set = set(primary_by_class.values())
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

        # Only PRESENT/LATE count as attended (B1); ACTIVE enrollments only and
        # DISTINCT log ids so a child with several enrollment rows isn't
        # double-counted (fan-out).
        attendance_by_class = dict(
            db.query(
                models.EnrollmentApplication.class_id,
                func.count(func.distinct(models.AttendanceLog.id)),
            )
            .select_from(models.AttendanceLog)
            .join(models.Child, models.Child.id == models.AttendanceLog.child_id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
            .filter(
                models.EnrollmentApplication.class_id.in_(class_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date,
                models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
            )
            .group_by(models.EnrollmentApplication.class_id)
            .all()
        )

        # occurred_at is a timezone-aware DateTime; compare on its DATE so
        # incidents on end_date (after 00:00) are not silently dropped.
        incidents_by_class = dict(
            db.query(models.Incident.class_id, func.count(models.Incident.id))
            .filter(
                models.Incident.class_id.in_(class_ids),
                func.date(models.Incident.occurred_at) >= start_date,
                func.date(models.Incident.occurred_at) <= end_date,
            )
            .group_by(models.Incident.class_id)
            .all()
        )

        # Calendar-aware operating days (Jordan Sun–Thu + OperatingCalendar), so
        # the per-class attendance rate agrees with the KG-level KPI (B2).
        operating_days = ManagerAnalyticsService._count_operating_days(
            db, kindergarten_id, start_date, end_date
        )

        result = []
        for class_obj in classes:
            supervisor = supervisors_by_id.get(primary_by_class.get(class_obj.id))
            enrolled_count = enrolled_by_class.get(class_obj.id, 0)
            attendance_logs = attendance_by_class.get(class_obj.id, 0)
            incidents = incidents_by_class.get(class_obj.id, 0)

            expected = enrolled_count * operating_days
            attendance_rate = (attendance_logs / expected * 100) if expected > 0 else 0
            utilization = (enrolled_count / class_obj.capacity_total * 100) if class_obj.capacity_total else 0

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

        # Supervisor -> class counts from active primary SupervisorAssignment (D1/B5).
        SA = models.SupervisorAssignment
        _primary = (SA.is_primary.is_(True), SA.deleted_at.is_(None))
        children_by_sup, classes_by_sup = ManagerAnalyticsService._supervisor_class_counts(db, sup_ids)

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
            db.query(SA.supervisor_id, func.count(models.Incident.id))
            .join(models.Class, models.Class.id == SA.class_id)
            .join(models.Incident, models.Incident.class_id == models.Class.id)
            .filter(
                SA.supervisor_id.in_(sup_ids), *_primary,
                # occurred_at is a DateTime; compare on DATE so end_date incidents count.
                func.date(models.Incident.occurred_at) >= start_date,
                func.date(models.Incident.occurred_at) <= end_date,
            )
            .group_by(SA.supervisor_id)
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
