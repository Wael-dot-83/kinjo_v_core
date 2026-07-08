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

_JORDAN_TZ = timezone(timedelta(hours=3))

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
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
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
        delivered_statuses = [
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
        ]

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
            .outerjoin(models.DailyReportView, models.DailyReportView.daily_report_id == models.DailyReport.id)
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
                "submission_rate": min(1.0, round(rr["submitted"] / required, 4)) if required else 0,
                "delivery_rate": min(1.0, round(rr["delivered"] / rr["submitted"], 4)) if rr["submitted"] else 0,
                "view_rate": min(1.0, round(viewed / rr["delivered"], 4)) if rr["delivered"] else 0,
            }
            per_kg[kg_id] = entry
            agg["required"] += required
            agg["submitted"] += rr["submitted"]
            agg["delivered"] += rr["delivered"]
            agg["viewed"] += viewed

        agg["submission_rate"] = min(1.0, round(agg["submitted"] / agg["required"], 4)) if agg["required"] else 0
        agg["delivery_rate"] = min(1.0, round(agg["delivered"] / agg["submitted"], 4)) if agg["submitted"] else 0
        agg["view_rate"] = min(1.0, round(agg["viewed"] / agg["delivered"], 4)) if agg["delivered"] else 0

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
            models.DailyReport.date,
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

    from datetime import timezone
    def _as_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    # Group by KG
    kg_deltas: Dict[int, List[float]] = {}
    for row in rows:
        if not row.created_at or not row.submitted_at:
            continue
        created = _as_utc_naive(row.created_at)
        submitted = _as_utc_naive(row.submitted_at)
        delta_hours = abs((submitted - created).total_seconds() / 3600.0)
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
                    (models.DailyReport.status.in_([
                        models.DailyReportStatus.REJECTED,
                        models.DailyReportStatus.RETURNED
                    ]), 1),
                    else_=0,
                )
            ).label("rejected"),
            func.sum(
                case(
                    (
                        and_(
                            models.DailyReport.status.in_([
                                models.DailyReportStatus.APPROVED,
                                models.DailyReportStatus.SENT_TO_PARENT,
                            ]),
                            models.DailyReport.rejected_reason.is_(None)
                        ),
                        1
                    ),
                    else_=0,
                )
            ).label("approved_first"),
            func.sum(
                case(
                    (models.DailyReport.status.in_([
                        models.DailyReportStatus.APPROVED,
                        models.DailyReportStatus.SENT_TO_PARENT,
                        models.DailyReportStatus.REJECTED,
                        models.DailyReportStatus.RETURNED
                    ]), 1),
                    else_=0,
                )
            ).label("total_resolved"),
        )
        .filter(
            models.DailyReport.date >= start_date,
            models.DailyReport.date <= end_date,
            models.DailyReport.status != models.DailyReportStatus.DRAFT,
        )
    )
    if kindergarten_id:
        q = q.filter(models.DailyReport.kindergarten_id == kindergarten_id)

    q = q.group_by(models.DailyReport.kindergarten_id)

    per_kg = {}
    agg_total = 0
    agg_rejected = 0
    agg_approved_first = 0
    agg_resolved = 0

    for row in q.all():
        total = row.total or 0
        rejected = int(row.rejected or 0)
        approved_first = int(row.approved_first or 0)
        total_resolved = int(row.total_resolved or 0)
        
        per_kg[row.kindergarten_id] = {
            "kindergarten_id": row.kindergarten_id,
            "total": total,
            "rejected": rejected,
            "approved": approved_first,
            "rejection_rate": round(rejected / total, 4) if total else 0,
            "first_pass_rate": round(approved_first / total_resolved, 4) if total_resolved else 0,
        }
        agg_total += total
        agg_rejected += rejected
        agg_approved_first += approved_first
        agg_resolved += total_resolved

    aggregate = {
        "total": agg_total,
        "rejected": agg_rejected,
        "approved": agg_approved_first,
        "rejection_rate": round(agg_rejected / agg_total, 4) if agg_total else 0,
        "first_pass_rate": round(agg_approved_first / agg_resolved, 4) if agg_resolved else 0,
    }

    return {"per_kindergarten": per_kg, "aggregate": aggregate}


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
    now = datetime.now(_JORDAN_TZ)
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
    now = datetime.now(_JORDAN_TZ)
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


# ---------------------------------------------------------------------------
# GQI sub-indicators (the 4 components beyond the funnel)
# ---------------------------------------------------------------------------

# Regulatory maximum staff-to-child ratio in Jordan (1 staff per N children).
_MAX_CHILDREN_PER_STAFF = 8


def _ratio_compliance_score(
    db: Session,
    kindergarten_id: Optional[int] = None,
) -> float:
    """
    Score = fraction of kindergartens where (enrolled_children / staff_count) ≤ threshold.
    Kindergartens with zero staff or zero enrolled children are excluded.
    Returns a value in [0.0, 1.0].
    """
    # Enrolled children per KG
    enroll_q = (
        db.query(
            models.Class.kindergarten_id,
            func.sum(models.Class.enrolled_children_count).label("enrolled"),
        )
        .filter(models.Class.is_active.is_(True))
    )
    if kindergarten_id:
        enroll_q = enroll_q.filter(models.Class.kindergarten_id == kindergarten_id)
    enroll_q = enroll_q.group_by(models.Class.kindergarten_id)
    enrolled_by_kg: Dict[int, int] = {row.kindergarten_id: int(row.enrolled or 0) for row in enroll_q.all()}

    # Staff (MANAGER + SUPERVISOR) per KG
    staff_q = (
        db.query(
            models.User.kindergarten_id,
            func.count(models.User.id).label("staff_count"),
        )
        .filter(
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            models.User.status == models.UserStatus.ACTIVE,
            models.User.kindergarten_id.isnot(None),
        )
    )
    if kindergarten_id:
        staff_q = staff_q.filter(models.User.kindergarten_id == kindergarten_id)
    staff_q = staff_q.group_by(models.User.kindergarten_id)
    staff_by_kg: Dict[int, int] = {row.kindergarten_id: int(row.staff_count or 0) for row in staff_q.all()}

    all_kg_ids = set(enrolled_by_kg.keys()) | set(staff_by_kg.keys())
    compliant = 0
    total = 0
    for kg_id in all_kg_ids:
        enrolled = enrolled_by_kg.get(kg_id, 0)
        staff = staff_by_kg.get(kg_id, 0)
        if enrolled == 0 or staff == 0:
            continue
        total += 1
        if (enrolled / staff) <= _MAX_CHILDREN_PER_STAFF:
            compliant += 1

    return round(compliant / total, 4) if total else 1.0


def _license_validity_score(
    db: Session,
    kindergarten_id: Optional[int] = None,
) -> float:
    """
    Score = fraction of active kindergartens with a valid (non-expired) license on file.
    Kindergartens without any license entry are excluded from denominator.
    Returns a value in [0.0, 1.0].
    """
    today = datetime.now(_JORDAN_TZ).date()

    q = (
        db.query(
            models.Kindergarten.id,
            models.Kindergarten.license_valid_until,
        )
        .filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            models.Kindergarten.license_valid_until.isnot(None),
        )
    )
    if kindergarten_id:
        q = q.filter(models.Kindergarten.id == kindergarten_id)

    rows = q.all()
    if not rows:
        return 1.0

    valid = sum(1 for row in rows if row.license_valid_until >= today)
    return round(valid / len(rows), 4)


def _training_coverage_score(
    db: Session,
    kindergarten_id: Optional[int] = None,
) -> float:
    """
    Score = completed mandatory training records / (staff count × mandatory module count).
    Staff = MANAGER + SUPERVISOR users with a kindergarten assignment.
    Returns a value in [0.0, 1.0].
    """
    mandatory_count = (
        db.query(func.count(models.TrainingModule.id))
        .filter(models.TrainingModule.is_mandatory.is_(True))
        .scalar()
        or 0
    )
    if mandatory_count == 0:
        return 1.0

    # Count eligible staff
    staff_q = (
        db.query(func.count(models.User.id))
        .filter(
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            models.User.status == models.UserStatus.ACTIVE,
            models.User.kindergarten_id.isnot(None),
        )
    )
    if kindergarten_id:
        staff_q = staff_q.filter(models.User.kindergarten_id == kindergarten_id)
    staff_total = int(staff_q.scalar() or 0)
    if staff_total == 0:
        return 1.0

    expected = staff_total * mandatory_count

    # Count completed mandatory training records
    completed_q = (
        db.query(func.count(models.StaffTrainingCompletion.id))
        .join(
            models.TrainingModule,
            models.TrainingModule.id == models.StaffTrainingCompletion.training_module_id,
        )
        .filter(
            models.TrainingModule.is_mandatory.is_(True),
            models.StaffTrainingCompletion.status == models.TrainingStatus.COMPLETED,
        )
    )
    if kindergarten_id:
        completed_q = completed_q.filter(
            models.StaffTrainingCompletion.kindergarten_id == kindergarten_id
        )
    completed = int(completed_q.scalar() or 0)

    return round(min(1.0, completed / expected), 4)


def _incident_sla_score(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> float:
    """
    Score = fraction of follow-up-required incidents where closed_at ≤ followup_sla_deadline.
    Only counts incidents that have a deadline set and were opened in [start_date, end_date].
    Returns a value in [0.0, 1.0].
    """
    q = (
        db.query(
            models.Incident.followup_sla_deadline,
            models.Incident.closed_at,
        )
        .filter(
            models.Incident.followup_required_flag.is_(True),
            models.Incident.followup_sla_deadline.isnot(None),
            func.date(models.Incident.occurred_at) >= start_date,
            func.date(models.Incident.occurred_at) <= end_date,
        )
    )
    if kindergarten_id:
        q = q.filter(models.Incident.kindergarten_id == kindergarten_id)

    rows = q.all()
    if not rows:
        return 1.0

    on_time = 0
    for row in rows:
        if row.closed_at is not None and row.followup_sla_deadline is not None:
            # Normalize both to UTC-naive for comparison
            closed = row.closed_at.replace(tzinfo=None) if row.closed_at.tzinfo else row.closed_at
            deadline = row.followup_sla_deadline.replace(tzinfo=None) if row.followup_sla_deadline.tzinfo else row.followup_sla_deadline
            if closed <= deadline:
                on_time += 1

    return round(on_time / len(rows), 4)


# ---------------------------------------------------------------------------
# Full GQI — composite of 5 sub-indicators at equal 20 % weight
# ---------------------------------------------------------------------------

def compute_full_gqi(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Governance Quality Index (GQI) — weighted composite of 7 sub-indicators.

    Sub-indicators (each in [0, 1]):
      1. report_submission  — daily report funnel submission rate (40%)
      2. delivery_rate      — report delivery compliance (20%)
      3. approval_quality   — first pass approval rate (15%)
      4. review_rate        — view rate (10%)
      5. training_coverage  — mandatory training completion rate (5%)
      6. license_validity   — active, non-expired licenses (5%)
      7. incident_sla       — follow-up SLA compliance rate (5%)

    Guardrails:
      - submission < 70%: cap GQI at 60
      - submission < 50%: cap GQI at 40
      - submission < 30%: cap GQI at 20
    """
    funnel = compute_governance_funnel(db, start_date, end_date, kindergarten_id)
    quality = compute_quality_metrics(db, start_date, end_date, kindergarten_id)
    
    funnel_agg = funnel.get("aggregate", {})
    quality_agg = quality.get("aggregate", {})

    s1 = float(funnel_agg.get("submission_rate", 0.0))
    s2 = float(funnel_agg.get("delivery_rate", 0.0))
    s3 = float(quality_agg.get("first_pass_rate", 0.0))
    s4 = float(funnel_agg.get("view_rate", 0.0))

    try:
        s5 = _training_coverage_score(db, kindergarten_id)
    except Exception:
        s5 = 0.0

    try:
        s6 = _license_validity_score(db, kindergarten_id)
    except Exception:
        s6 = 0.0

    try:
        s7 = _incident_sla_score(db, start_date, end_date, kindergarten_id)
    except Exception:
        s7 = 0.0

    # Weighted sum based on proposed weighting
    weighted_sum = (s1 * 0.40) + (s2 * 0.20) + (s3 * 0.15) + (s4 * 0.10) + (s5 * 0.05) + (s6 * 0.05) + (s7 * 0.05)
    gqi = round(weighted_sum * 100, 2)

    # Apply Governance Guardrails (Caps based on Submission Compliance)
    submission_pct = s1 * 100
    if submission_pct < 30:
        gqi = min(gqi, 20.0)
    elif submission_pct < 50:
        gqi = min(gqi, 40.0)
    elif submission_pct < 70:
        gqi = min(gqi, 60.0)

    # Health Classification
    if gqi >= 80:
        health_status = "Healthy"
    elif gqi >= 60:
        health_status = "Warning"
    elif gqi >= 40:
        health_status = "High Risk"
    else:
        health_status = "Critical"

    return {
        "gqi": gqi,
        "health_status": health_status,
        "sub_indicators": {
            "report_submission": round(s1 * 100, 2),
            "delivery_compliance": round(s2 * 100, 2),
            "approval_quality": round(s3 * 100, 2),
            "review_rate": round(s4 * 100, 2),
            "training_coverage": round(s5 * 100, 2),
            "license_validity": round(s6 * 100, 2),
            "incident_sla": round(s7 * 100, 2),
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "kindergarten_id": kindergarten_id,
    }
