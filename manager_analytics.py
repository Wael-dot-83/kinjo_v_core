"""
Manager Analytics Service - Operational KPIs & Predictive Indicators

Provides manager-scoped analytics including:
- Operational KPIs (enrollment, attendance, incidents, capacity)
- Predictive indicators (forecasting, anomaly detection)
- Drill-down navigation (KG -> Classes -> Children)
"""

from typing import Optional, List, Dict, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import math

import models


class ManagerAnalyticsService:
    """
    Provides analytics calculations scoped to a manager's kindergarten.
    All metrics are computed for a single kindergarten only.
    """

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

        # Count attendance logs in date range
        attendance_logs = db.query(
            func.count(models.AttendanceLog.id)
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date
        ).scalar() or 0

        # Count operating days (calendar days in range)
        operating_days = (end_date - start_date).days + 1

        # Expected attendance = active_enrollments * operating_days
        expected_attendance = active_enrollments * operating_days

        if expected_attendance == 0:
            return 0.0

        attendance_rate = (attendance_logs / expected_attendance) * 100
        return round(attendance_rate, 2)

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

        result = []
        today = date.today()

        for supervisor in supervisors:
            # Count children assigned to supervisor's classes
            children_count = db.query(
                func.count(models.Child.id)
            ).join(
                models.EnrollmentApplication
            ).join(
                models.Class
            ).filter(
                models.Class.supervisor_id == supervisor.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Count assigned classes
            classes_count = db.query(
                func.count(models.Class.id)
            ).filter(
                models.Class.supervisor_id == supervisor.id,
                models.Class.is_active == True
            ).scalar() or 0

            # Count reports submitted today
            reports_today = db.query(
                func.count(models.DailyReport.id)
            ).filter(
                models.DailyReport.submitted_by == supervisor.id,
                models.DailyReport.date == today
            ).scalar() or 0

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
        today = date.today()
        start_date = today - timedelta(days=lookback_days)

        # Get historical attendance rates
        historical = []
        current = start_date
        rates = []

        while current <= today:
            rate = ManagerAnalyticsService.compute_attendance_rate(
                db, kindergarten_id, current, current
            )
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
        today = date.today()
        start_date = today - timedelta(days=lookback_days)

        # Collect attendance rates
        current = start_date
        rates = []

        while current <= today:
            rate = ManagerAnalyticsService.compute_attendance_rate(
                db, kindergarten_id, current, current
            )
            rates.append({"date": current, "rate": rate})
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

        result = []
        for class_obj in classes:
            # Get supervisor for this class
            supervisor = db.query(models.User).filter(
                models.User.id == class_obj.supervisor_id
            ).first()

            # Count enrolled children
            enrolled_count = db.query(
                func.count(models.EnrollmentApplication.id)
            ).filter(
                models.EnrollmentApplication.class_id == class_obj.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Attendance rate for this class
            attendance_logs = db.query(
                func.count(models.AttendanceLog.id)
            ).join(
                models.Child
            ).join(
                models.EnrollmentApplication
            ).filter(
                models.EnrollmentApplication.class_id == class_obj.id,
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date
            ).scalar() or 0

            operating_days = (end_date - start_date).days + 1
            expected = enrolled_count * operating_days
            attendance_rate = (attendance_logs / expected * 100) if expected > 0 else 0

            # Incident count
            incidents = db.query(
                func.count(models.Incident.id)
            ).join(
                models.Child
            ).join(
                models.EnrollmentApplication
            ).filter(
                models.EnrollmentApplication.class_id == class_obj.id,
                models.Incident.occurred_at >= start_date,
                models.Incident.occurred_at <= end_date
            ).scalar() or 0

            # Capacity utilization
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

        result = []
        for supervisor in supervisors:
            # Count children under supervision
            children_count = db.query(
                func.count(models.Child.id)
            ).join(
                models.EnrollmentApplication
            ).join(
                models.Class
            ).filter(
                models.Class.supervisor_id == supervisor.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Count classes
            classes_count = db.query(
                func.count(models.Class.id)
            ).filter(
                models.Class.supervisor_id == supervisor.id,
                models.Class.is_active == True
            ).scalar() or 0

            # Reports submitted in period
            reports_submitted = db.query(
                func.count(models.DailyReport.id)
            ).filter(
                models.DailyReport.submitted_by == supervisor.id,
                models.DailyReport.date >= start_date,
                models.DailyReport.date <= end_date
            ).scalar() or 0

            # Incidents reported
            incidents = db.query(
                func.count(models.Incident.id)
            ).join(
                models.Child
            ).join(
                models.EnrollmentApplication
            ).join(
                models.Class
            ).filter(
                models.Class.supervisor_id == supervisor.id,
                models.Incident.occurred_at >= start_date,
                models.Incident.occurred_at <= end_date
            ).scalar() or 0

            result.append({
                "supervisor_id": supervisor.id,
                "supervisor_name": supervisor.username,
                "classes_managed": classes_count,
                "children_supervised": children_count,
                "reports_submitted": reports_submitted,
                "incidents_reported": incidents,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat()
            })

        return result


# Export for use in routers
__all__ = ['ManagerAnalyticsService']
