"""
Staff equity analytics service.
Computes Gini coefficient, overtime hours, and workload equity metrics
for supervisors and staff within kindergartens.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from models import (
    Class,
    EnrollmentApplication,
    EnrollmentStatus,
    SupervisorAssignment,
    SupervisorProfile,
    User,
    UserRole,
    Kindergarten,
    KindergartenStatus,
    AttendanceLog,
    AttendanceStatus,
    StaffPresenceLog,
)

logger = logging.getLogger(__name__)


def compute_gini(values: List[float]) -> float:
    if not values or len(values) < 2:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumulative = 0.0
    weighted_sum = 0.0
    for i, val in enumerate(sorted_vals):
        cumulative += val
        weighted_sum += (i + 1) * val
    gini = (2.0 * weighted_sum) / (n * total) - (n + 1) / n
    return max(0.0, min(1.0, gini))


class StaffEquityService:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(_JORDAN_TZ).replace(tzinfo=None)

    def teacher_workload_gini(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = db.query(
            Class.kindergarten_id,
            Class.id,
            Class.enrolled_children_count,
        ).filter(Class.enrolled_children_count.isnot(None))

        if kindergarten_id is not None:
            query = query.filter(Class.kindergarten_id == kindergarten_id)

        rows = query.all()
        if not rows:
            return {
                "gini": 0.0,
                "class_count": 0,
                "avg_children_per_class": 0.0,
                "min_children": 0,
                "max_children": 0,
                "classification": "no_data",
            }

        children_counts = [c[2] for c in rows]
        gini = compute_gini([float(c) for c in children_counts])

        if gini <= 0.15:
            classification = "excellent"
        elif gini <= 0.25:
            classification = "acceptable"
        elif gini <= 0.40:
            classification = "concerning"
        else:
            classification = "critical"

        return {
            "gini": round(gini, 3),
            "class_count": len(children_counts),
            "avg_children_per_class": round(sum(children_counts) / len(children_counts), 1),
            "min_children": min(children_counts),
            "max_children": max(children_counts),
            "classification": classification,
        }

    def teacher_workload_equity_index(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = db.query(
            Class.kindergarten_id,
            Class.enrolled_children_count,
            Class.capacity_total,
        ).filter(
            Class.enrolled_children_count.isnot(None),
            Class.capacity_total.isnot(None),
            Class.capacity_total > 0,
        )

        if kindergarten_id is not None:
            query = query.filter(Class.kindergarten_id == kindergarten_id)

        rows = query.all()
        if not rows:
            return {
                "equity_index": 1.0,
                "classification": "no_data",
                "classes_analyzed": 0,
            }

        ratios = [c[1] / c[2] for c in rows if c[2] > 0]
        if not ratios:
            return {"equity_index": 1.0, "classification": "no_data", "classes_analyzed": 0}

        avg_ratio = sum(ratios) / len(ratios)
        max_ratio = max(ratios)
        min_ratio = min(ratios)

        imbalance = abs(max_ratio - min_ratio) / avg_ratio if avg_ratio > 0 else 0
        equity_index = max(0.0, 1.0 - imbalance)

        return {
            "equity_index": round(equity_index, 3),
            "avg_ratio": round(avg_ratio, 3),
            "min_ratio": round(min_ratio, 3),
            "max_ratio": round(max_ratio, 3),
            "imbalance": round(imbalance, 3),
            "classification": (
                "equitable" if equity_index >= 0.8
                else "imbalanced" if equity_index >= 0.6
                else "critical"
            ),
            "classes_analyzed": len(ratios),
        }

    def overtime_tracking(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))

        query = db.query(
            StaffPresenceLog.staff_id,
            func.min(StaffPresenceLog.start_at).label("first_in"),
            func.max(StaffPresenceLog.end_at).label("last_out"),
            func.count(StaffPresenceLog.id).label("days"),
        ).filter(
            StaffPresenceLog.start_at >= cutoff,
            StaffPresenceLog.end_at.isnot(None),
        )

        if kindergarten_id is not None:
            query = query.filter(
                StaffPresenceLog.kindergarten_id == kindergarten_id,
            )

        rows = query.group_by(StaffPresenceLog.staff_id).all()

        if not rows:
            return {
                "avg_daily_hours": 0.0,
                "max_daily_hours": 0.0,
                "staff_with_overtime": 0,
                "total_staff": 0,
                "avg_hours_per_week": 0.0,
            }

        STANDARD_DAILY_HOURS = 8.0
        daily_hours = []
        staff_with_overtime = 0

        for row in rows:
            first_in = row[1]
            last_out = row[2]
            day_count = row[3]
            if first_in and last_out and first_in.tzinfo is None:
                first_in = first_in
            if last_out and last_out.tzinfo is None:
                last_out = last_out
            if first_in and last_out:
                duration_hours = (last_out - first_in).total_seconds() / 3600.0
                avg_daily = duration_hours / day_count if day_count > 0 else 0
                daily_hours.append(avg_daily)
                if avg_daily > STANDARD_DAILY_HOURS + 1:
                    staff_with_overtime += 1

        avg_daily = sum(daily_hours) / len(daily_hours) if daily_hours else 0
        max_daily = max(daily_hours) if daily_hours else 0
        avg_weekly = avg_daily * 5

        return {
            "avg_daily_hours": round(avg_daily, 1),
            "max_daily_hours": round(max_daily, 1),
            "avg_hours_per_week": round(avg_weekly, 1),
            "staff_with_overtime": staff_with_overtime,
            "total_staff": len(daily_hours),
            "period_days": days,
        }

    def staffing_ratio_compliance(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        today = datetime.now(timezone(timedelta(hours=3))).date()

        query = db.query(
            Class.id,
            Class.enrolled_children_count,
            Class.capacity_total,
            Class.kindergarten_id,
        ).filter(Class.enrolled_children_count.isnot(None))

        if kindergarten_id is not None:
            query = query.filter(Class.kindergarten_id == kindergarten_id)

        rows = query.all()
        if not rows:
            return {
                "compliant_classes": 0,
                "total_classes": 0,
                "compliance_rate": 100.0,
                "over_capacity_classes": 0,
            }

        compliant = 0
        over_capacity = 0
        for row in rows:
            enrolled = row[1] or 0
            capacity = row[2] or 1
            if enrolled <= capacity * 1.05:
                compliant += 1
            if enrolled > capacity:
                over_capacity += 1

        compliance_rate = (compliant / len(rows)) * 100.0 if rows else 100.0

        return {
            "compliant_classes": compliant,
            "total_classes": len(rows),
            "compliance_rate": round(compliance_rate, 1),
            "over_capacity_classes": over_capacity,
        }

    def overall_staff_equity(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        gini = self.teacher_workload_gini(db, kindergarten_id=kindergarten_id)
        equity = self.teacher_workload_equity_index(db, kindergarten_id=kindergarten_id)
        overtime = self.overtime_tracking(db, kindergarten_id=kindergarten_id)
        compliance = self.staffing_ratio_compliance(db, kindergarten_id=kindergarten_id)

        gini_score = max(0, 100.0 - (gini["gini"] * 200))
        equity_score = equity["equity_index"] * 100.0
        overtime_score = 100.0 if overtime["staff_with_overtime"] <= 1 else max(0, 100 - (overtime["staff_with_overtime"] * 20))
        compliance_score = compliance["compliance_rate"]

        overall = (
            gini_score * 0.25
            + equity_score * 0.25
            + overtime_score * 0.20
            + compliance_score * 0.30
        )

        return {
            "overall_score": round(overall, 1),
            "gini": gini,
            "equity_index": equity,
            "overtime": overtime,
            "compliance": compliance,
            "status": (
                "excellent" if overall >= 85
                else "good" if overall >= 70
                else "fair" if overall >= 55
                else "needs_attention"
            ),
        }


staff_equity_service = StaffEquityService()
