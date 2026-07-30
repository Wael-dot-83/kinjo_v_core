"""
Correlation discovery engine.
Automated pairwise Pearson/Spearman scanner with domain-filter and causal probes.
"""
import logging
import math
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today, jordan_day_bounds
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, and_, cast, Float, Date
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    AttendanceStatus,
    Class,
    DailyReport,
    DailyReportStatus,
    Incident,
    Kindergarten,
    KindergartenStatus,
    EnrollmentApplication,
    EnrollmentStatus,
)

logger = logging.getLogger(__name__)

MIN_SAMPLE_SIZE = 14
SIGNIFICANCE_THRESHOLD = 0.05
EFFECT_SIZE_THRESHOLD = 0.5


def pearson_r(x: List[float], y: List[float]) -> Tuple[float, float]:
    n = len(x)
    if n < 2:
        return 0.0, 1.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(a * b for a, b in zip(x, y))
    sum_x2 = sum(a * a for a in x)
    sum_y2 = sum(b * b for b in y)
    num = n * sum_xy - sum_x * sum_y
    denom = math.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
    if denom == 0:
        return 0.0, 1.0
    r = num / denom
    r = max(-1.0, min(1.0, r))
    se = math.sqrt((1 - r * r) / max(n - 2, 1))
    if se == 0:
        p = 0.0 if abs(r) > 0 else 1.0
    else:
        t_stat = r / se
        p = _t_distribution_pvalue(abs(t_stat), n - 2)
    return round(r, 4), round(p, 6)


def spearman_rho(x: List[float], y: List[float]) -> Tuple[float, float]:
    rank_x = _rank(x)
    rank_y = _rank(y)
    return pearson_r(rank_x, rank_y)


def _rank(values: List[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _t_distribution_pvalue(t_stat: float, df: int) -> float:
    if df <= 0:
        return 1.0
    x = df / (df + t_stat * t_stat)
    p = _incomplete_beta(df / 2.0, 0.5, x)
    return min(1.0, max(0.0, p))


def _incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
        a * math.log(x) + b * math.log(1 - x)
    )
    if x < (a + 1) / (a + b + 2):
        return bt * _beta_cf(a, b, x) / a
    return 1.0 - bt * _beta_cf(b, a, 1 - x) / b


def _beta_cf(a: float, b: float, x: float, max_iter: int = 200) -> float:
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-8:
            break
    return h


def interpret_strength(rho: float) -> str:
    abv = abs(rho)
    if abv >= 0.7:
        return "strong"
    if abv >= 0.5:
        return "medium"
    if abv >= 0.3:
        return "weak"
    return "negligible"


class CorrelationEngine:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _daily_attendance_rate(self, db: Session, days: int) -> List[Tuple[date, float]]:
        cutoff = _today() - timedelta(days=max(MIN_SAMPLE_SIZE, days))
        rows = (
            db.query(
                AttendanceLog.date,
                func.count(AttendanceLog.id).label("total"),
                func.sum(
                    func.cast(
                        AttendanceLog.status == AttendanceStatus.PRESENT,
                        Float,
                    )
                ).label("present"),
            )
            .filter(AttendanceLog.date >= cutoff)
            .group_by(AttendanceLog.date)
            .order_by(AttendanceLog.date)
            .all()
        )
        result = []
        for row in rows:
            total = int(row[1])
            present = float(row[2] or 0)
            if total > 0:
                result.append((row[0], present / total * 100.0))
        return result

    def _daily_incident_count(self, db: Session, days: int) -> List[Tuple[date, float]]:
        cutoff = _today() - timedelta(days=max(MIN_SAMPLE_SIZE, days))
        rows = (
            db.query(
                func.date(Incident.created_at).label("d"),
                func.count(Incident.id),
            )
            .filter(Incident.created_at >= jordan_day_bounds(cutoff)[0])
            .group_by(func.date(Incident.created_at))
            .order_by("d")
            .all()
        )
        return [(row[0], float(row[1])) for row in rows]

    def _daily_report_count(self, db: Session, days: int) -> List[Tuple[date, float]]:
        cutoff = _today() - timedelta(days=max(MIN_SAMPLE_SIZE, days))
        rows = (
            db.query(
                DailyReport.date,
                func.count(DailyReport.id),
            )
            .filter(
                DailyReport.date >= cutoff,
                DailyReport.status.in_([
                    DailyReportStatus.SUBMITTED,
                    DailyReportStatus.APPROVED,
                    DailyReportStatus.SENT_TO_PARENT,
                ]),
            )
            .group_by(DailyReport.date)
            .order_by(DailyReport.date)
            .all()
        )
        return [(row[0], float(row[1])) for row in rows]

    def _daily_enrollment_count(self, db: Session, days: int) -> List[Tuple[date, float]]:
        cutoff = self._utcnow_naive() - timedelta(days=max(MIN_SAMPLE_SIZE, days))
        rows = (
            db.query(
                func.date(EnrollmentApplication.created_at).label("d"),
                func.count(EnrollmentApplication.id),
            )
            .filter(EnrollmentApplication.created_at >= jordan_day_bounds(cutoff.date())[0])
            .group_by(func.date(EnrollmentApplication.created_at))
            .order_by("d")
            .all()
        )
        return [(row[0], float(row[1])) for row in rows]

    def _align_series(
        self,
        series_a: List[Tuple[date, float]],
        series_b: List[Tuple[date, float]],
    ) -> Tuple[List[float], List[float]]:
        dates_a = {d: v for d, v in series_a}
        dates_b = {d: v for d, v in series_b}
        common = sorted(set(dates_a.keys()) & set(dates_b.keys()))
        if not common:
            return [], []
        return ([dates_a[d] for d in common], [dates_b[d] for d in common])

    def discover_correlations(self, db: Session, days: int = 90) -> Dict[str, Any]:
        metrics = {
            "attendance_rate": self._daily_attendance_rate(db, days),
            "incident_count": self._daily_incident_count(db, days),
            "report_count": self._daily_report_count(db, days),
            "enrollment_count": self._daily_enrollment_count(db, days),
        }

        flagged = []
        names = list(metrics.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                name_a, name_b = names[i], names[j]
                series_a, series_b = metrics[name_a], metrics[name_b]
                x, y = self._align_series(series_a, series_b)
                n = len(x)
                if n < MIN_SAMPLE_SIZE:
                    flagged.append({
                        "metric_a": name_a,
                        "metric_b": name_b,
                        "sample_size": n,
                        "pearson_r": None,
                        "pearson_p": None,
                        "spearman_rho": None,
                        "spearman_p": None,
                        "confidence": "insufficient",
                        "interpretation": f"insufficient data (n={n}, min={MIN_SAMPLE_SIZE})",
                    })
                    continue

                r_p, p_p = pearson_r(x, y)
                r_s, p_s = spearman_rho(x, y)

                confidence = "high" if p_s < 0.01 else ("medium" if p_s < 0.05 else "low")
                significant = abs(r_s) >= EFFECT_SIZE_THRESHOLD and p_s < SIGNIFICANCE_THRESHOLD

                flagged.append({
                    "metric_a": name_a,
                    "metric_b": name_b,
                    "sample_size": n,
                    "pearson_r": r_p,
                    "pearson_p": p_p,
                    "spearman_rho": r_s,
                    "spearman_p": p_s,
                    "confidence": confidence,
                    "significant": significant,
                    "strength": interpret_strength(r_s),
                    "direction": "positive" if r_s > 0 else "negative",
                    "interpretation": (
                        f"{'Significant ' if significant else ''}"
                        f"{interpret_strength(r_s)} {('positive' if r_s > 0 else 'negative')} "
                        f"correlation (ρ={r_s:.3f}, p={p_s:.4f}, n={n})"
                    ),
                })

        flagged.sort(key=lambda r: abs(r["spearman_rho"] or 0), reverse=True)

        significant_findings = [f for f in flagged if f.get("significant")]
        insufficient = [f for f in flagged if f["confidence"] == "insufficient"]
        weak = [f for f in flagged if not f.get("significant") and f["confidence"] != "insufficient"]

        return {
            "total_pairs": len(flagged),
            "significant_count": len(significant_findings),
            "insufficient_data_count": len(insufficient),
            "weak_count": len(weak),
            "all_correlations": flagged,
            "significant_findings": significant_findings,
            "metadata": {
                "min_sample_size": MIN_SAMPLE_SIZE,
                "significance_threshold": SIGNIFICANCE_THRESHOLD,
                "effect_size_threshold": EFFECT_SIZE_THRESHOLD,
                "period_days": days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }


correlation_engine = CorrelationEngine()
