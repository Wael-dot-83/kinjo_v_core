"""
Governance KPI Service — Daily Report Compliance Monitoring
============================================================
Computes funnel KPIs (required → submitted → delivered → viewed),
timeliness/quality/consistency metrics, Bayesian fair ranking,
low-performance detection, and reminder management with cooldown.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case

import models
from config import settings
from cache_service import cache_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funnel computation
# ---------------------------------------------------------------------------

def compute_governance_funnel(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute the daily-report governance funnel per kindergarten.

    Stages:
      required  — children who had attendance on each day in the range
      submitted — daily reports that reached SUBMITTED or beyond
      delivered — reports with status SENT_TO_PARENT
      viewed    — reports with a DailyReportView record
    """
    cache_key = f"governance:funnel:{start_date}:{end_date}:{kindergarten_id or 'all'}"
    use_cache = not settings.TESTING

    def _compute():
        # --- required: children with attendance in the period ---
        # AttendanceLog has class_id; join through Class to get kindergarten_id
        # Use count(*) since unique constraint (child_id, date) ensures no duplicates
        attendance_q = (
            db.query(
                models.Class.kindergarten_id,
                func.count(models.AttendanceLog.id).label("required_count"),
            )
            .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
            .filter(
                models.AttendanceLog.date >= start_date,
                models.AttendanceLog.date <= end_date,
            )
        )
        if kindergarten_id:
            attendance_q = attendance_q.filter(
                models.Class.kindergarten_id == kindergarten_id
            )
        attendance_q = attendance_q.group_by(models.Class.kindergarten_id)
        attendance_rows = {row.kindergarten_id: row.required_count for row in attendance_q.all()}

        # --- submitted / delivered counts ---
        submitted_statuses = [
            models.DailyReportStatus.SUBMITTED,
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
        ]
        delivered_statuses = [models.DailyReportStatus.SENT_TO_PARENT]

        report_q = (
            db.query(
                models.DailyReport.kindergarten_id,
                func.count(models.DailyReport.id).label("total_reports"),
                func.sum(
                    case(
                        (models.DailyReport.status.in_(submitted_statuses), 1),
                        else_=0,
                    )
                ).label("submitted_count"),
                func.sum(
                    case(
                        (models.DailyReport.status.in_(delivered_statuses), 1),
                        else_=0,
                    )
                ).label("delivered_count"),
            )
            .filter(
                models.DailyReport.date >= start_date,
                models.DailyReport.date <= end_date,
            )
        )
        if kindergarten_id:
            report_q = report_q.filter(
                models.DailyReport.kindergarten_id == kindergarten_id
            )
        report_q = report_q.group_by(models.DailyReport.kindergarten_id)
        report_rows = {
            row.kindergarten_id: {
                "total_reports": row.total_reports,
                "submitted": int(row.submitted_count or 0),
                "delivered": int(row.delivered_count or 0),
            }
            for row in report_q.all()
        }

        # --- viewed counts ---
        viewed_q = (
            db.query(
                models.DailyReport.kindergarten_id,
                func.count(func.distinct(models.DailyReportView.daily_report_id)).label("viewed_count"),
            )
            .join(models.DailyReportView, models.DailyReportView.daily_report_id == models.DailyReport.id)
            .filter(
                models.DailyReport.date >= start_date,
                models.DailyReport.date <= end_date,
            )
        )
        if kindergarten_id:
            viewed_q = viewed_q.filter(
                models.DailyReport.kindergarten_id == kindergarten_id
            )
        viewed_q = viewed_q.group_by(models.DailyReport.kindergarten_id)
        viewed_rows = {row.kindergarten_id: int(row.viewed_count or 0) for row in viewed_q.all()}

        # --- Assemble per-KG results ---
        all_kg_ids = set(attendance_rows.keys()) | set(report_rows.keys())
        per_kg = {}
        agg = {"required": 0, "submitted": 0, "delivered": 0, "viewed": 0}

        for kg_id in all_kg_ids:
            required = attendance_rows.get(kg_id, 0)
            rr = report_rows.get(kg_id, {"total_reports": 0, "submitted": 0, "delivered": 0})
            viewed = viewed_rows.get(kg_id, 0)

            entry = {
                "kindergarten_id": kg_id,
                "required": required,
                "submitted": rr["submitted"],
                "delivered": rr["delivered"],
                "viewed": viewed,
                "submission_rate": round(rr["submitted"] / required, 4) if required else 0,
                "delivery_rate": round(rr["delivered"] / rr["submitted"], 4) if rr["submitted"] else 0,
                "view_rate": round(viewed / rr["delivered"], 4) if rr["delivered"] else 0,
            }
            per_kg[kg_id] = entry
            agg["required"] += required
            agg["submitted"] += rr["submitted"]
            agg["delivered"] += rr["delivered"]
            agg["viewed"] += viewed

        agg["submission_rate"] = round(agg["submitted"] / agg["required"], 4) if agg["required"] else 0
        agg["delivery_rate"] = round(agg["delivered"] / agg["submitted"], 4) if agg["submitted"] else 0
        agg["view_rate"] = round(agg["viewed"] / agg["delivered"], 4) if agg["delivered"] else 0

        return {"per_kindergarten": per_kg, "aggregate": agg}

    if use_cache:
        return cache_service.get_or_set(cache_key, _compute, ttl_seconds=300)
    return _compute()


# ---------------------------------------------------------------------------
# Timeliness metrics
# ---------------------------------------------------------------------------

def compute_timeliness_metrics(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute submission timeliness: median and p90 hours from report creation to submission.
    """
    q = (
        db.query(
            models.DailyReport.kindergarten_id,
            models.DailyReport.created_at,
            models.DailyReport.submitted_at,
            models.DailyReport.sent_to_parent_at,
        )
        .filter(
            models.DailyReport.date >= start_date,
            models.DailyReport.date <= end_date,
            models.DailyReport.submitted_at.isnot(None),
        )
    )
    if kindergarten_id:
        q = q.filter(models.DailyReport.kindergarten_id == kindergarten_id)

    rows = q.all()

    # Group by KG
    kg_deltas: Dict[int, List[float]] = {}
    for row in rows:
        if not row.created_at or not row.submitted_at:
            continue
        delta_hours = (row.submitted_at - row.created_at).total_seconds() / 3600
        kg_deltas.setdefault(row.kindergarten_id, []).append(delta_hours)

    per_kg = {}
    for kg_id, deltas in kg_deltas.items():
        deltas.sort()
        n = len(deltas)
        median = deltas[n // 2] if n else 0
        p90_idx = int(n * 0.9)
        p90 = deltas[min(p90_idx, n - 1)] if n else 0
        per_kg[kg_id] = {
            "kindergarten_id": kg_id,
            "sample_size": n,
            "median_hours": round(median, 2),
            "p90_hours": round(p90, 2),
        }

    return {"per_kindergarten": per_kg}


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

def compute_quality_metrics(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute rejection rate and first-pass approval rate per KG.
    """
    q = (
        db.query(
            models.DailyReport.kindergarten_id,
            func.count(models.DailyReport.id).label("total"),
            func.sum(
                case(
                    (models.DailyReport.status == models.DailyReportStatus.REJECTED, 1),
                    else_=0,
                )
            ).label("rejected"),
            func.sum(
                case(
                    (models.DailyReport.status.in_([
                        models.DailyReportStatus.APPROVED,
                        models.DailyReportStatus.SENT_TO_PARENT,
                    ]), 1),
                    else_=0,
                )
            ).label("approved"),
        )
        .filter(
            models.DailyReport.date >= start_date,
            models.DailyReport.date <= end_date,
        )
    )
    if kindergarten_id:
        q = q.filter(models.DailyReport.kindergarten_id == kindergarten_id)

    q = q.group_by(models.DailyReport.kindergarten_id)

    per_kg = {}
    for row in q.all():
        total = row.total or 0
        rejected = int(row.rejected or 0)
        approved = int(row.approved or 0)
        per_kg[row.kindergarten_id] = {
            "kindergarten_id": row.kindergarten_id,
            "total": total,
            "rejected": rejected,
            "approved": approved,
            "rejection_rate": round(rejected / total, 4) if total else 0,
            "first_pass_rate": round(approved / total, 4) if total else 0,
        }

    return {"per_kindergarten": per_kg}


# ---------------------------------------------------------------------------
# Consistency index
# ---------------------------------------------------------------------------

def compute_consistency_index(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Consistency = 1 - std_dev(daily_submission_rate) over the date range.
    Higher is better (more consistent daily output).
    """
    # Get per-KG per-day report counts
    report_q = (
        db.query(
            models.DailyReport.kindergarten_id,
            models.DailyReport.date,
            func.count(models.DailyReport.id).label("report_count"),
        )
        .filter(
            models.DailyReport.date >= start_date,
            models.DailyReport.date <= end_date,
        )
    )
    if kindergarten_id:
        report_q = report_q.filter(models.DailyReport.kindergarten_id == kindergarten_id)

    report_q = report_q.group_by(
        models.DailyReport.kindergarten_id,
        models.DailyReport.date,
    )

    # Get per-KG per-day attendance counts (denominator)
    # Join through Class to get kindergarten_id
    attend_q = (
        db.query(
            models.Class.kindergarten_id,
            models.AttendanceLog.date,
            func.count(models.AttendanceLog.id).label("attend_count"),
        )
        .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
        .filter(
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date,
        )
    )
    if kindergarten_id:
        attend_q = attend_q.filter(models.Class.kindergarten_id == kindergarten_id)

    attend_q = attend_q.group_by(
        models.Class.kindergarten_id,
        models.AttendanceLog.date,
    )

    attend_map: Dict[Tuple[int, date], int] = {}
    for row in attend_q.all():
        attend_map[(row.kindergarten_id, row.date)] = row.attend_count

    # Compute daily rates
    kg_daily_rates: Dict[int, List[float]] = {}
    for row in report_q.all():
        denom = attend_map.get((row.kindergarten_id, row.date), 0)
        rate = row.report_count / denom if denom else 0
        kg_daily_rates.setdefault(row.kindergarten_id, []).append(rate)

    per_kg = {}
    for kg_id, rates in kg_daily_rates.items():
        n = len(rates)
        if n < 2:
            std_dev = 0.0
        else:
            mean = sum(rates) / n
            variance = sum((r - mean) ** 2 for r in rates) / (n - 1)
            std_dev = variance ** 0.5
        consistency = round(max(0.0, 1.0 - std_dev), 4)
        per_kg[kg_id] = {
            "kindergarten_id": kg_id,
            "days_sampled": n,
            "consistency_index": consistency,
        }

    return {"per_kindergarten": per_kg}


# ---------------------------------------------------------------------------
# Bayesian fair ranking
# ---------------------------------------------------------------------------

def compute_fair_ranking(
    funnel_data: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Bayesian-smoothed ranking of kindergartens by submission rate.
    Formula: score = (successes + k * prior) / (total + k)
    """
    k = settings.GOVERNANCE_SMOOTHING_K
    min_required = settings.GOVERNANCE_MIN_REPORTS_FOR_RANKING

    per_kg = funnel_data.get("per_kindergarten", {})

    # Compute global prior (overall submission rate)
    agg = funnel_data.get("aggregate", {})
    prior = agg.get("submission_rate", 0.5) or 0.5

    # Look up KG names
    kg_ids = list(per_kg.keys())
    kg_names = {}
    if kg_ids:
        for kg in db.query(models.Kindergarten.id, models.Kindergarten.name_ar, models.Kindergarten.name_en).filter(
            models.Kindergarten.id.in_(kg_ids)
        ).all():
            kg_names[kg.id] = {"name_ar": kg.name_ar, "name_en": kg.name_en}

    ranked = []
    for kg_id, data in per_kg.items():
        required = data["required"]
        if required < min_required:
            continue
        submitted = data["submitted"]
        score = (submitted + k * prior) / (required + k)
        names = kg_names.get(kg_id, {"name_ar": "", "name_en": ""})
        ranked.append({
            "kindergarten_id": kg_id,
            "name_ar": names["name_ar"],
            "name_en": names["name_en"],
            "required": required,
            "submitted": submitted,
            "delivered": data["delivered"],
            "viewed": data["viewed"],
            "raw_rate": data["submission_rate"],
            "bayesian_score": round(score, 4),
            "is_low_performer": data["submission_rate"] < settings.GOVERNANCE_LOW_PERF_THRESHOLD,
        })

    ranked.sort(key=lambda x: x["bayesian_score"], reverse=True)

    # Add rank numbers
    for i, entry in enumerate(ranked, 1):
        entry["rank"] = i

    return ranked


# ---------------------------------------------------------------------------
# Low performer detection
# ---------------------------------------------------------------------------

def detect_low_performers(
    funnel_data: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Return kindergartens whose submission rate falls below the threshold.
    """
    threshold = settings.GOVERNANCE_LOW_PERF_THRESHOLD
    min_required = settings.GOVERNANCE_MIN_REPORTS_FOR_RANKING
    per_kg = funnel_data.get("per_kindergarten", {})

    kg_ids = list(per_kg.keys())
    kg_names = {}
    if kg_ids:
        for kg in db.query(models.Kindergarten.id, models.Kindergarten.name_ar, models.Kindergarten.name_en).filter(
            models.Kindergarten.id.in_(kg_ids)
        ).all():
            kg_names[kg.id] = {"name_ar": kg.name_ar, "name_en": kg.name_en}

    low = []
    for kg_id, data in per_kg.items():
        if data["required"] < min_required:
            continue
        if data["submission_rate"] < threshold:
            names = kg_names.get(kg_id, {"name_ar": "", "name_en": ""})
            low.append({
                "kindergarten_id": kg_id,
                "name_ar": names["name_ar"],
                "name_en": names["name_en"],
                "submission_rate": data["submission_rate"],
                "required": data["required"],
                "submitted": data["submitted"],
                "gap": data["required"] - data["submitted"],
            })

    low.sort(key=lambda x: x["submission_rate"])
    return low


# ---------------------------------------------------------------------------
# Reminder cooldown
# ---------------------------------------------------------------------------

def check_reminder_cooldown(
    db: Session,
    target_type: str,
    target_id: int,
) -> Tuple[bool, Optional[datetime]]:
    """
    Check whether a governance reminder can be sent (cooldown expired).
    Returns (can_send, last_sent_at).
    """
    now = datetime.now(timezone.utc)
    latest = (
        db.query(models.GovernanceReminder)
        .filter(
            models.GovernanceReminder.target_type == target_type,
            models.GovernanceReminder.target_id == target_id,
            models.GovernanceReminder.cooldown_expires_at > now,
        )
        .order_by(models.GovernanceReminder.sent_at.desc())
        .first()
    )

    if latest:
        return False, latest.sent_at
    return True, None


def send_governance_reminder(
    db: Session,
    admin_user: models.User,
    target_type: str,
    target_id: int,
    reminder_type: str,
    metrics_snapshot: Optional[Dict[str, Any]] = None,
) -> models.GovernanceReminder:
    """
    Create a GovernanceReminder record and optionally notify the target.
    """
    now = datetime.now(timezone.utc)
    cooldown_hours = settings.GOVERNANCE_REMINDER_COOLDOWN_HOURS
    cooldown_expires = now + timedelta(hours=cooldown_hours)

    reminder = models.GovernanceReminder(
        target_type=target_type,
        target_id=target_id,
        reminder_type=reminder_type,
        sent_by=admin_user.id,
        sent_at=now,
        cooldown_expires_at=cooldown_expires,
        payload=metrics_snapshot,
    )
    db.add(reminder)

    # Create in-app notification for the target user(s)
    if target_type == "supervisor":
        _create_governance_notification(db, target_id, reminder_type, metrics_snapshot)
    elif target_type == "kindergarten":
        # Notify all managers of that kindergarten
        managers = (
            db.query(models.User)
            .filter(
                models.User.kindergarten_id == target_id,
                models.User.role == models.UserRole.MANAGER,
                models.User.status == models.UserStatus.ACTIVE,
            )
            .all()
        )
        for mgr in managers:
            _create_governance_notification(db, mgr.id, reminder_type, metrics_snapshot)

    db.commit()
    db.refresh(reminder)
    return reminder


def _create_governance_notification(
    db: Session,
    user_id: int,
    reminder_type: str,
    metrics: Optional[Dict[str, Any]],
) -> None:
    """Create an in-app notification for a governance reminder."""
    notification = models.Notification(
        user_id=user_id,
        notification_type=models.NotificationType.GOVERNANCE_REMINDER,
        channel=models.NotificationChannel.IN_APP,
        status=models.NotificationStatus.PENDING,
        payload={
            "reminder_type": reminder_type,
            "metrics": metrics,
        },
    )
    db.add(notification)
