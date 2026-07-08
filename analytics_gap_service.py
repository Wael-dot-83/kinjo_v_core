"""
Analytics Gap Service — All 33 Missing Metrics
Covers: Network (1-7), Governorate (8-14), KG (15-22),
        Child (23-27), Predictive (28-31), Governance (32-33)

Each metric returns raw value + Chart.js-ready chart object with:
- Bilingual labels (ar/en)
- Semantic colours (green/amber/red)
- Thresholds / reference lines
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, distinct, func, or_
from sqlalchemy.orm import Session

import models
from schemas.chart_dto import (
    ChartConfig,
    ChartDataset,
    LayerMetricsResponse,
    MetricResponse,
)

# ─── Jordan timezone ─────────────────────────────────────────────────────────
_JORDAN_TZ = timezone(timedelta(hours=3))

def _today() -> date:
    return datetime.now(_JORDAN_TZ).date()

# ─── Colour palette ──────────────────────────────────────────────────────────
C_GOOD    = "#2ecc71"
C_WARN    = "#f1c40f"
C_CRIT    = "#e74c3c"
C_INFO    = "#3498db"
C_PURPLE  = "#9b59b6"
C_ORANGE  = "#e67e22"
C_TEAL    = "#1abc9c"

SEMANTIC_COLORS = {"good": C_GOOD, "warning": C_WARN, "critical": C_CRIT}

# ─── Stat helpers ─────────────────────────────────────────────────────────────

def _gini(values: List[float]) -> float:
    """Gini coefficient — 0 = perfect equality, 1 = max inequality."""
    if not values:
        return 0.0
    vs = sorted(values)
    n = len(vs)
    total = sum(vs)
    if total == 0:
        return 0.0
    coef = 2.0 * sum((i + 1) * v for i, v in enumerate(vs)) / (n * total) - (n + 1) / n
    return round(max(0.0, min(1.0, coef)), 4)


def _cv(values: List[float]) -> float:
    """Coefficient of variation (std/mean × 100)."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in values) / len(values)
    return round(sqrt(var) / mean * 100, 2)


def _slope(values: List[float]) -> float:
    """OLS slope of evenly-spaced series."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return round(num / den, 4) if den else 0.0


def _linear_forecast(values: List[float], horizon: int) -> List[float]:
    """Extend a series forward by `horizon` steps using OLS."""
    n = len(values)
    if n < 2:
        return [values[-1]] * horizon if values else [0.0] * horizon
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    intercept = y_mean - slope * x_mean
    return [round(intercept + slope * (n + i), 2) for i in range(horizon)]


def _nps(scores: List[int]) -> float:
    """NPS = % promoters (9-10) − % detractors (0-6)."""
    if not scores:
        return 0.0
    total = len(scores)
    promoters  = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) / total * 100, 1)


def _colour_by_threshold(val: float, warn: float, crit: float,
                          lower_is_better: bool = False) -> str:
    if lower_is_better:
        if val >= crit:
            return C_CRIT
        if val >= warn:
            return C_WARN
        return C_GOOD
    else:
        if val < crit:
            return C_CRIT
        if val < warn:
            return C_WARN
        return C_GOOD


# ─── Chart helpers ────────────────────────────────────────────────────────────

def _chart(
    chart_type: str,
    labels: List[str],
    en_label: str,
    ar_label: str,
    data: List[float],
    bg: Optional[List[str]] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> ChartConfig:
    if bg is None:
        bg = [C_INFO] * len(data)
    return ChartConfig(
        type=chart_type,
        labels=labels,
        datasets=[ChartDataset(
            label={"en": en_label, "ar": ar_label},
            data=data,
            backgroundColor=bg,
            borderColor=[c.replace("33", "ff") for c in bg],
        )],
        thresholds=thresholds,
        colors=SEMANTIC_COLORS,
    )


def _gauge_chart(en_label: str, ar_label: str, val: float,
                 warn: float, crit: float,
                 lower_is_better: bool = False) -> ChartConfig:
    color = _colour_by_threshold(val, warn, crit, lower_is_better)
    return _chart(
        "gauge", [en_label], en_label, ar_label, [val],
        bg=[color],
        thresholds={"warning": warn, "critical": crit},
    )


# ─── Main service ─────────────────────────────────────────────────────────────

class AnalyticsGapService:

    def __init__(self, db: Session) -> None:
        self.db = db

    # ═══════════════════════════════════════════════════════════════════════
    # NETWORK LAYER — Metrics 1-7
    # ═══════════════════════════════════════════════════════════════════════

    def get_network_metrics(self, locale: str = "ar") -> LayerMetricsResponse:
        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=30)

        # 1. EQUITY INDEX — Gini of KG-level attendance rates
        # ─────────────────────────────────────────────────────
        # Attendance rate per KG over last 30 days
        att_rows = (
            self.db.query(
                models.AttendanceLog.class_id,
                func.count(models.AttendanceLog.id).label("total"),
                func.sum(
                    case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)
                ).label("present"),
            )
            .filter(models.AttendanceLog.date.between(window_start, today))
            .group_by(models.AttendanceLog.class_id)
            .all()
        )
        # Map class_id → kg_id, then aggregate
        class_to_kg = dict(
            self.db.query(models.Class.id, models.Class.kindergarten_id)
            .filter(models.Class.is_active == True)
            .all()
        )
        kg_att: Dict[int, Tuple[int, int]] = {}  # kg_id → (present, total)
        for row in att_rows:
            kg_id = class_to_kg.get(row.class_id)
            if kg_id is None:
                continue
            p, t = kg_att.get(kg_id, (0, 0))
            kg_att[kg_id] = (p + (row.present or 0), t + (row.total or 0))

        kg_rates = [p / t * 100 for p, t in kg_att.values() if t > 0]
        equity_val = _gini(kg_rates)
        # Low Gini = good (equitable); high Gini = inequitable
        equity_color = _colour_by_threshold(equity_val, 0.2, 0.35, lower_is_better=True)

        metrics.append(MetricResponse(
            metric="equity_index",
            value=round(equity_val, 4),
            chart=_chart(
                "gauge",
                ["Equity Index" if locale == "en" else "مؤشر الإنصاف"],
                "Network Equity Index", "مؤشر إنصاف الشبكة",
                [round(equity_val, 4)],
                bg=[equity_color],
                thresholds={"warning": 0.2, "critical": 0.35},
            ),
            locale=locale,
        ))

        # 2. CAPACITY PRESSURE — enrolled / total capacity %
        # ─────────────────────────────────────────────────────
        cap_row = self.db.query(
            func.sum(models.Class.capacity_total).label("capacity"),
            func.sum(models.Class.enrolled_children_count).label("enrolled"),
        ).filter(models.Class.is_active == True, models.Class.deleted_at == None).first()

        total_cap = cap_row.capacity or 0
        total_enr = cap_row.enrolled or 0
        pressure = round(total_enr / total_cap * 100, 1) if total_cap else 0.0
        pressure_color = _colour_by_threshold(pressure, 85, 95, lower_is_better=True)

        metrics.append(MetricResponse(
            metric="capacity_pressure",
            value=pressure,
            chart=_gauge_chart(
                "Capacity Pressure (%)", "ضغط السعة الاستيعابية (%)",
                pressure, warn=85, crit=95, lower_is_better=True,
            ),
            locale=locale,
        ))

        # 3. DIGITAL ENGAGEMENT — % parents who viewed reports (last 30 days)
        # ─────────────────────────────────────────────────────
        total_parents = self.db.query(func.count(models.ParentProfile.id)).scalar() or 1
        engaged_parents = (
            self.db.query(func.count(distinct(models.DailyReportView.parent_user_id)))
            .join(models.DailyReport, models.DailyReportView.daily_report_id == models.DailyReport.id)
            .filter(models.DailyReport.date >= window_start)
            .scalar()
        ) or 0
        engagement = round(engaged_parents / total_parents * 100, 1)
        eng_color = _colour_by_threshold(engagement, 60, 40)

        metrics.append(MetricResponse(
            metric="digital_engagement",
            value=engagement,
            chart=_gauge_chart(
                "Digital Engagement (%)", "المشاركة الرقمية (%)",
                engagement, warn=60, crit=40,
            ),
            locale=locale,
        ))

        # 4. LICENSE EXPIRY DISTRIBUTION — pie by bucket
        # ─────────────────────────────────────────────────────
        soon30  = today + timedelta(days=30)
        soon90  = today + timedelta(days=90)
        kgs_all = self.db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
        expired_count  = sum(1 for k in kgs_all if k.license_valid_until and k.license_valid_until < today)
        exp30_count    = sum(1 for k in kgs_all if k.license_valid_until and today <= k.license_valid_until <= soon30)
        exp90_count    = sum(1 for k in kgs_all if k.license_valid_until and soon30 < k.license_valid_until <= soon90)
        valid_count    = sum(1 for k in kgs_all if k.license_valid_until and k.license_valid_until > soon90)
        no_lic_count   = sum(1 for k in kgs_all if not k.license_valid_until)

        metrics.append(MetricResponse(
            metric="license_expiry_distribution",
            value=expired_count,
            chart=_chart(
                "pie",
                ["Expired" if locale == "en" else "منتهي",
                 "≤30 days" if locale == "en" else "≤30 يوم",
                 "31–90 days" if locale == "en" else "31–90 يوم",
                 "Valid" if locale == "en" else "سارٍ",
                 "No license" if locale == "en" else "بلا ترخيص"],
                "License Expiry Distribution", "توزيع انتهاء التراخيص",
                [float(expired_count), float(exp30_count), float(exp90_count),
                 float(valid_count), float(no_lic_count)],
                bg=[C_CRIT, C_ORANGE, C_WARN, C_GOOD, C_INFO],
                thresholds={"expired_alert": 0, "expiring_soon_alert": 5},
            ),
            locale=locale,
        ))

        # 5. NETWORK ATTENDANCE RATE — overall last 30 days
        # ─────────────────────────────────────────────────────
        net_att = self.db.query(
            func.count(models.AttendanceLog.id).label("total"),
            func.sum(
                case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)
            ).label("present"),
        ).filter(models.AttendanceLog.date.between(window_start, today)).first()

        net_total   = net_att.total   or 0
        net_present = net_att.present or 0
        net_att_rate = round(net_present / net_total * 100, 1) if net_total else 0.0

        metrics.append(MetricResponse(
            metric="network_attendance_rate",
            value=net_att_rate,
            chart=_gauge_chart(
                "Network Attendance Rate (%)", "معدل حضور الشبكة (%)",
                net_att_rate, warn=85, crit=75,
            ),
            locale=locale,
        ))

        # 6. STAFF TURNOVER PROXY — % inactive/suspended among MANAGER+SUPERVISOR
        # ─────────────────────────────────────────────────────
        # No departure tracking table exists; proxy = INACTIVE/SUSPENDED as % of all staff
        staff_total = (
            self.db.query(func.count(models.User.id))
            .filter(
                models.User.role.in_(["MANAGER", "SUPERVISOR"]),
                models.User.deleted_at == None,
            )
            .scalar()
        ) or 1
        staff_inactive = (
            self.db.query(func.count(models.User.id))
            .filter(
                models.User.role.in_(["MANAGER", "SUPERVISOR"]),
                models.User.status.in_(["INACTIVE", "SUSPENDED"]),
                models.User.deleted_at == None,
            )
            .scalar()
        ) or 0
        turnover_rate = round(staff_inactive / staff_total * 100, 1)
        turnover_color = _colour_by_threshold(turnover_rate, 10, 20, lower_is_better=True)

        metrics.append(MetricResponse(
            metric="staff_turnover_proxy",
            value=turnover_rate,
            chart=_chart(
                "gauge",
                ["Staff Attrition %" if locale == "en" else "نسبة استنزاف الموظفين %"],
                "Staff Attrition Rate (%)", "معدل استنزاف الموظفين (%)",
                [turnover_rate],
                bg=[turnover_color],
                thresholds={"warning": 10, "critical": 20},
            ),
            locale=locale,
        ))

        # 7. NETWORK IMPROVEMENT VELOCITY — slope of weekly attendance trend
        # ─────────────────────────────────────────────────────
        # Build weekly attendance rates for last 12 weeks
        weekly_rates: List[float] = []
        for w in range(11, -1, -1):
            wk_start = today - timedelta(days=(w + 1) * 7)
            wk_end   = today - timedelta(days=w * 7)
            row = self.db.query(
                func.count(models.AttendanceLog.id).label("total"),
                func.sum(
                    case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)
                ).label("present"),
            ).filter(models.AttendanceLog.date.between(wk_start, wk_end)).first()
            t = row.total or 0
            p = row.present or 0
            weekly_rates.append(p / t * 100 if t else 0.0)

        velocity = _slope(weekly_rates)  # pp per week
        velocity_color = C_GOOD if velocity >= 0 else C_CRIT
        week_labels = [f"W-{11 - i}" for i in range(12)]

        metrics.append(MetricResponse(
            metric="network_improvement_velocity",
            value=round(velocity, 3),
            chart=_chart(
                "line",
                week_labels,
                "Weekly Attendance Rate (%)", "معدل الحضور الأسبوعي (%)",
                [round(r, 1) for r in weekly_rates],
                bg=[velocity_color] * 12,
                thresholds={"slope_warning": -0.5, "slope_critical": -1.0},
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="network", metrics=metrics, locale=locale)

    # ═══════════════════════════════════════════════════════════════════════
    # GOVERNORATE LAYER — Metrics 8-14
    # gov_name: Kindergarten.governorate string value
    # ═══════════════════════════════════════════════════════════════════════

    def get_governorate_metrics(
        self, gov_name: str, locale: str = "ar"
    ) -> LayerMetricsResponse:
        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=30)

        kg_ids_subq = (
            self.db.query(models.Kindergarten.id)
            .filter(
                models.Kindergarten.governorate == gov_name,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            )
            .subquery()
        )
        kg_ids = [r[0] for r in self.db.query(kg_ids_subq).all()]

        if not kg_ids:
            # Return empty layer
            return LayerMetricsResponse(
                layer="governorate",
                metrics=[MetricResponse(
                    metric="no_data", value=0.0,
                    chart=_chart("bar", ["No data"], "No data", "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", [0.0]),
                    locale=locale,
                )],
                locale=locale,
            )

        # 8. INTER-KG VARIANCE — CV of KG attendance rates in this governorate
        # ─────────────────────────────────────────────────────
        cls_ids = [r[0] for r in
                   self.db.query(models.Class.id)
                   .filter(models.Class.kindergarten_id.in_(kg_ids),
                           models.Class.is_active == True).all()]

        kg_rates_by_name: Dict[str, float] = {}
        for kg_id in kg_ids:
            kg_cls = [c for c in cls_ids
                      if any(
                          r.class_id == c and r.kindergarten_id == kg_id
                          for r in []
                      )]
            # Direct query per KG for attendance rate
            row = (
                self.db.query(
                    func.count(models.AttendanceLog.id).label("tot"),
                    func.sum(case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("pres"),
                )
                .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
                .filter(
                    models.Class.kindergarten_id == kg_id,
                    models.AttendanceLog.date.between(window_start, today),
                )
                .first()
            )
            t = row.tot or 0
            p = row.pres or 0
            if t > 0:
                kg = self.db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
                name = kg.name_en or kg.name_ar if kg else str(kg_id)
                kg_rates_by_name[name] = round(p / t * 100, 1)

        rates_list = list(kg_rates_by_name.values())
        cv = _cv(rates_list)
        cv_color = _colour_by_threshold(cv, 15, 25, lower_is_better=True)

        bar_colors = [
            _colour_by_threshold(r, 85, 75) for r in rates_list
        ]
        metrics.append(MetricResponse(
            metric="interkg_variance",
            value=round(cv, 2),
            chart=_chart(
                "bar",
                list(kg_rates_by_name.keys()),
                "KG Attendance Rates (%)", "معدلات حضور الحضانات (%)",
                rates_list,
                bg=bar_colors,
                thresholds={"cv_warning": 15, "cv_critical": 25},
            ),
            locale=locale,
        ))

        # 9. CHRONIC ABSENTEEISM RATE — % children absent >20% of days in last 30 days
        # ─────────────────────────────────────────────────────
        # Count working days approximation: 22 days in 30-day window (Mon-Fri minus ~4 holidays)
        working_days = 22
        absent_threshold = working_days * 0.20  # 20% = 4.4 → 5 days absent

        # Children enrolled in this governorate's KGs
        total_enrolled = (
            self.db.query(func.count(distinct(models.EnrollmentApplication.child_id)))
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .scalar()
        ) or 0

        # Children with ≥ absent_threshold ABSENT days (group by child, then count qualifying)
        from sqlalchemy import text as sa_text
        child_absent_counts = (
            self.db.query(
                models.AttendanceLog.child_id,
                func.count(models.AttendanceLog.id).label("absent_days"),
            )
            .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
            .filter(
                models.Class.kindergarten_id.in_(kg_ids),
                models.AttendanceLog.date.between(window_start, today),
                models.AttendanceLog.status == "ABSENT",
            )
            .group_by(models.AttendanceLog.child_id)
            .all()
        )
        chronic_count = sum(1 for _, absent_days in child_absent_counts if absent_days >= absent_threshold)

        chronic_rate = round(chronic_count / total_enrolled * 100, 1) if total_enrolled else 0.0
        metrics.append(MetricResponse(
            metric="chronic_absenteeism_rate",
            value=chronic_rate,
            chart=_gauge_chart(
                "Chronic Absenteeism Rate (%)", "معدل التغيب المزمن (%)",
                chronic_rate, warn=10, crit=20, lower_is_better=True,
            ),
            locale=locale,
        ))

        # 10. PARENT NPS — Net Promoter Score from survey responses
        # ─────────────────────────────────────────────────────
        nps_scores = [
            r[0]
            for r in (
                self.db.query(models.SurveyResponse.nps_score)
                .join(models.Survey, models.SurveyResponse.survey_id == models.Survey.id)
                .filter(
                    models.Survey.kindergarten_id.in_(kg_ids),
                    models.SurveyResponse.nps_score != None,
                    models.Survey.start_date >= (today - timedelta(days=180)),
                )
                .all()
            )
        ]
        nps_val = _nps(nps_scores)
        promoters  = sum(1 for s in nps_scores if s >= 9)
        passives   = sum(1 for s in nps_scores if 7 <= s <= 8)
        detractors = sum(1 for s in nps_scores if s <= 6)
        nps_color  = _colour_by_threshold(nps_val, 30, 0)

        metrics.append(MetricResponse(
            metric="parent_nps",
            value=nps_val,
            chart=_chart(
                "bar",
                ["Promoters (9-10)" if locale == "en" else "مروّجون (9-10)",
                 "Passives (7-8)"  if locale == "en" else "محايدون (7-8)",
                 "Detractors (0-6)" if locale == "en" else "معارضون (0-6)"],
                "NPS Breakdown", "تفصيل صافي نقاط الترويج",
                [float(promoters), float(passives), float(detractors)],
                bg=[C_GOOD, C_WARN, C_CRIT],
                thresholds={"nps_warning": 30, "nps_critical": 0},
            ),
            locale=locale,
        ))

        # 11. INCIDENT DENSITY — incidents per 100 child-days
        # ─────────────────────────────────────────────────────
        att_days = (
            self.db.query(func.count(models.AttendanceLog.id))
            .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
            .filter(
                models.Class.kindergarten_id.in_(kg_ids),
                models.AttendanceLog.date.between(window_start, today),
                models.AttendanceLog.status.in_(["PRESENT", "LATE"]),
            )
            .scalar()
        ) or 0

        incident_count = (
            self.db.query(func.count(models.Incident.id))
            .filter(
                models.Incident.kindergarten_id.in_(kg_ids),
                models.Incident.occurred_at >= datetime.combine(window_start, datetime.min.time()),
                models.Incident.deleted_at == None,
            )
            .scalar()
        ) or 0

        density = round(incident_count / att_days * 100, 2) if att_days else 0.0
        density_color = _colour_by_threshold(density, 2, 5, lower_is_better=True)

        # Per-KG breakdown for heatmap-style bar
        _kg_name_map = {
            k.id: (k.name_en or k.name_ar)
            for k in self.db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()
        }
        kg_incident_data: List[Tuple[str, float]] = []
        for kg_id in kg_ids:
            kg_name = _kg_name_map.get(kg_id, str(kg_id))
            kd_days = (
                self.db.query(func.count(models.AttendanceLog.id))
                .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
                .filter(
                    models.Class.kindergarten_id == kg_id,
                    models.AttendanceLog.date.between(window_start, today),
                    models.AttendanceLog.status.in_(["PRESENT", "LATE"]),
                )
                .scalar()
            ) or 0
            ki_count = (
                self.db.query(func.count(models.Incident.id))
                .filter(
                    models.Incident.kindergarten_id == kg_id,
                    models.Incident.occurred_at >= datetime.combine(window_start, datetime.min.time()),
                    models.Incident.deleted_at == None,
                )
                .scalar()
            ) or 0
            kg_incident_data.append((kg_name, round(ki_count / kd_days * 100, 2) if kd_days else 0.0))

        metrics.append(MetricResponse(
            metric="incident_density",
            value=density,
            chart=_chart(
                "bar",
                [n for n, _ in kg_incident_data],
                "Incident Density (per 100 child-days)",
                "كثافة الحوادث (لكل 100 يوم طفل)",
                [v for _, v in kg_incident_data],
                bg=[_colour_by_threshold(v, 2, 5, lower_is_better=True)
                    for _, v in kg_incident_data],
                thresholds={"warning": 2, "critical": 5},
            ),
            locale=locale,
        ))

        # 12. REPORT SUBMISSION RATE — % daily reports submitted vs expected
        # ─────────────────────────────────────────────────────
        expected_r = (
            self.db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.kindergarten_id.in_(kg_ids),
                models.DailyReport.date.between(window_start, today),
            )
            .scalar()
        ) or 0
        submitted_r = (
            self.db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.kindergarten_id.in_(kg_ids),
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.status.in_(["SUBMITTED", "APPROVED", "SENT_TO_PARENT"]),
            )
            .scalar()
        ) or 0
        submit_rate = round(submitted_r / expected_r * 100, 1) if expected_r else 0.0

        metrics.append(MetricResponse(
            metric="report_submission_rate",
            value=submit_rate,
            chart=_gauge_chart(
                "Report Submission Rate (%)", "معدل تقديم التقارير (%)",
                submit_rate, warn=85, crit=70,
            ),
            locale=locale,
        ))

        # 13. ENROLLMENT GROWTH RATE — MoM change in active enrollments
        # ─────────────────────────────────────────────────────
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        this_month = (
            self.db.query(func.count(models.EnrollmentApplication.id))
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                func.date(models.EnrollmentApplication.created_at) >= this_month_start,
            )
            .scalar()
        ) or 0
        last_month = (
            self.db.query(func.count(models.EnrollmentApplication.id))
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                func.date(models.EnrollmentApplication.created_at) >= last_month_start,
                func.date(models.EnrollmentApplication.created_at) < this_month_start,
            )
            .scalar()
        ) or 0
        growth = round((this_month - last_month) / last_month * 100, 1) if last_month else 0.0
        growth_color = C_GOOD if growth >= 0 else C_CRIT

        metrics.append(MetricResponse(
            metric="enrollment_growth_rate",
            value=growth,
            chart=_chart(
                "bar",
                ["Last Month" if locale == "en" else "الشهر الماضي",
                 "This Month" if locale == "en" else "هذا الشهر"],
                "Monthly Enrollment Growth", "نمو التسجيل الشهري",
                [float(last_month), float(this_month)],
                bg=[C_INFO, growth_color],
                thresholds={"target_growth": 5},
            ),
            locale=locale,
        ))

        # 14. AVG GQI — average governance quality index for governorate's KGs
        # ─────────────────────────────────────────────────────
        gqi_rows = (
            self.db.query(
                models.Kindergarten.name_en,
                models.Kindergarten.name_ar,
                models.GovernanceScore.governance_quality_index,
            )
            .join(models.GovernanceScore,
                  models.GovernanceScore.kindergarten_id == models.Kindergarten.id)
            .filter(models.Kindergarten.id.in_(kg_ids))
            .order_by(models.GovernanceScore.created_at.desc())
            .all()
        )
        # Dedupe: take latest per KG
        seen: set = set()
        gqi_data: List[Tuple[str, float]] = []
        for name_en, name_ar, gqi in gqi_rows:
            label = name_en or name_ar or "?"
            if label not in seen:
                seen.add(label)
                gqi_data.append((label, round(gqi, 1)))

        avg_gqi = round(sum(v for _, v in gqi_data) / len(gqi_data), 1) if gqi_data else 0.0
        metrics.append(MetricResponse(
            metric="avg_gqi",
            value=avg_gqi,
            chart=_chart(
                "bar",
                [n for n, _ in gqi_data] or ["No data"],
                "GQI per Kindergarten", "مؤشر جودة الحوكمة لكل حضانة",
                [v for _, v in gqi_data] or [0.0],
                bg=[_colour_by_threshold(v, 70, 55) for _, v in gqi_data] or [C_INFO],
                thresholds={"warning": 70, "critical": 55},
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="governorate", metrics=metrics, locale=locale)

    # ═══════════════════════════════════════════════════════════════════════
    # KINDERGARTEN LAYER — Metrics 15-22
    # ═══════════════════════════════════════════════════════════════════════

    def get_kg_metrics(self, kg_id: int, locale: str = "ar") -> LayerMetricsResponse:
        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=30)

        # 15. CHILD RISK COMPOSITE — % children flagged as high-risk
        # High-risk: attendance rate < 75% OR has HIGH/CRITICAL incident in last 30 days
        # ─────────────────────────────────────────────────────
        active_children = [
            r[0] for r in (
                self.db.query(distinct(models.EnrollmentApplication.child_id))
                .filter(
                    models.EnrollmentApplication.kindergarten_id == kg_id,
                    models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                )
                .all()
            )
        ]
        total_ch = len(active_children)

        high_risk_count = 0
        risk_scores: List[float] = []
        child_risk_labels: List[str] = []

        if active_children:
            # Attendance rate per child
            att_by_child = dict(
                self.db.query(
                    models.AttendanceLog.child_id,
                    func.count(models.AttendanceLog.id).label("tot"),
                    func.sum(
                        case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)
                    ).label("pres"),
                )
                .filter(
                    models.AttendanceLog.child_id.in_(active_children),
                    models.AttendanceLog.date.between(window_start, today),
                )
                .group_by(models.AttendanceLog.child_id)
                .all()
            )
            # Incident count per child
            inc_by_child = dict(
                self.db.query(
                    models.Incident.child_id,
                    func.count(models.Incident.id),
                )
                .filter(
                    models.Incident.child_id.in_(active_children),
                    models.Incident.kindergarten_id == kg_id,
                    models.Incident.severity_level.in_(["HIGH", "CRITICAL"]),
                    models.Incident.occurred_at >= datetime.combine(window_start, datetime.min.time()),
                    models.Incident.deleted_at == None,
                )
                .group_by(models.Incident.child_id)
                .all()
            )

            for cid in active_children:
                row = att_by_child.get(cid, (0, 0, 0))
                if isinstance(row, (list, tuple)) and len(row) == 3:
                    _, tot, pres = row[0], row[1], row[2]
                else:
                    tot, pres = 0, 0
                att_rate = pres / tot * 100 if tot else 0.0
                inc_count = inc_by_child.get(cid, 0)

                # Risk score: 0-100
                # Low attendance contributes up to 50 pts; incidents add 25 pts each (capped 50)
                risk = max(0, (75 - att_rate) / 75 * 50) if att_rate < 75 else 0
                risk += min(50, inc_count * 25)
                risk_scores.append(round(min(100, risk), 1))
                if risk >= 50:
                    high_risk_count += 1

        risk_rate = round(high_risk_count / total_ch * 100, 1) if total_ch else 0.0

        # Histogram of risk scores: buckets 0-25, 25-50, 50-75, 75-100
        buckets = [0, 0, 0, 0]
        for r in risk_scores:
            buckets[min(3, int(r // 25))] += 1

        metrics.append(MetricResponse(
            metric="child_risk_composite",
            value=risk_rate,
            chart=_chart(
                "bar",
                ["Low (0-25)" if locale == "en" else "منخفض (0-25)",
                 "Medium (25-50)" if locale == "en" else "متوسط (25-50)",
                 "High (50-75)" if locale == "en" else "مرتفع (50-75)",
                 "Critical (75-100)" if locale == "en" else "حرج (75-100)"],
                "Child Risk Score Distribution", "توزيع درجة مخاطر الأطفال",
                [float(b) for b in buckets],
                bg=[C_GOOD, C_WARN, C_ORANGE, C_CRIT],
                thresholds={"high_risk_pct_warning": 15, "high_risk_pct_critical": 30},
            ),
            locale=locale,
        ))

        # 16. PARENT ENGAGEMENT RATE — % parents who viewed reports (last 30 days)
        # ─────────────────────────────────────────────────────
        total_kg_parents = (
            self.db.query(func.count(distinct(models.User.id)))
            .join(models.ParentProfile, models.ParentProfile.user_id == models.User.id)
            .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
            .filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .scalar()
        ) or 1
        engaged_kg_parents = (
            self.db.query(func.count(distinct(models.DailyReportView.parent_user_id)))
            .join(models.DailyReport, models.DailyReportView.daily_report_id == models.DailyReport.id)
            .filter(
                models.DailyReport.kindergarten_id == kg_id,
                models.DailyReport.date >= window_start,
            )
            .scalar()
        ) or 0
        parent_eng = round(engaged_kg_parents / total_kg_parents * 100, 1)

        metrics.append(MetricResponse(
            metric="parent_engagement_rate",
            value=parent_eng,
            chart=_gauge_chart(
                "Parent Engagement Rate (%)", "معدل مشاركة أولياء الأمور (%)",
                parent_eng, warn=65, crit=40,
            ),
            locale=locale,
        ))

        # 17. TEACHER TIMELINESS SCORE — % reports submitted within 24h
        # Submitted means submitted_at - created_at ≤ 24h
        # ─────────────────────────────────────────────────────
        reports_with_submit = (
            self.db.query(
                models.DailyReport.created_at,
                models.DailyReport.submitted_at,
            )
            .filter(
                models.DailyReport.kindergarten_id == kg_id,
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.submitted_at != None,
            )
            .all()
        )
        on_time_count = sum(
            1 for cr, su in reports_with_submit
            if su and cr and (su - cr).total_seconds() <= 86400
        )
        total_submitted_r = len(reports_with_submit)
        timeliness = round(on_time_count / total_submitted_r * 100, 1) if total_submitted_r else 0.0

        metrics.append(MetricResponse(
            metric="teacher_timeliness_score",
            value=timeliness,
            chart=_gauge_chart(
                "Teacher Report Timeliness (%)", "درجة توقيت تقارير المعلمات (%)",
                timeliness, warn=80, crit=60,
            ),
            locale=locale,
        ))

        # 18. MEAL COMPLIANCE RATE — avg % of 4 meals consumed
        # ─────────────────────────────────────────────────────
        meal_rows = (
            self.db.query(
                models.DailyReport.breakfast,
                models.DailyReport.snack,
                models.DailyReport.milk,
                models.DailyReport.lunch,
            )
            .filter(
                models.DailyReport.kindergarten_id == kg_id,
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.status != models.DailyReportStatus.DRAFT,
            )
            .all()
        )
        meal_totals = {"breakfast": 0, "snack": 0, "milk": 0, "lunch": 0}
        for row in meal_rows:
            if row.breakfast: meal_totals["breakfast"] += 1
            if row.snack:     meal_totals["snack"]     += 1
            if row.milk:      meal_totals["milk"]       += 1
            if row.lunch:     meal_totals["lunch"]      += 1

        n_reports = len(meal_rows) or 1
        meal_rates = {m: round(c / n_reports * 100, 1) for m, c in meal_totals.items()}
        avg_meal = round(sum(meal_rates.values()) / 4, 1)
        meal_labels = {
            "breakfast": ("Breakfast" if locale == "en" else "إفطار"),
            "snack":     ("Snack"     if locale == "en" else "وجبة خفيفة"),
            "milk":      ("Milk"      if locale == "en" else "حليب"),
            "lunch":     ("Lunch"     if locale == "en" else "غداء"),
        }

        metrics.append(MetricResponse(
            metric="meal_compliance_rate",
            value=avg_meal,
            chart=_chart(
                "bar",
                [meal_labels[m] for m in ["breakfast", "snack", "milk", "lunch"]],
                "Meal Compliance Rate (%)", "معدل الالتزام بالوجبات (%)",
                [meal_rates[m] for m in ["breakfast", "snack", "milk", "lunch"]],
                bg=[_colour_by_threshold(meal_rates[m], 80, 60)
                    for m in ["breakfast", "snack", "milk", "lunch"]],
                thresholds={"warning": 80, "critical": 60},
            ),
            locale=locale,
        ))

        # 19. HEALTH ALERT DENSITY — % reports flagged (sick mood or health_notes)
        # ─────────────────────────────────────────────────────
        total_reports_kg = (
            self.db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.kindergarten_id == kg_id,
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.status != models.DailyReportStatus.DRAFT,
            )
            .scalar()
        ) or 1
        health_flagged = (
            self.db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.kindergarten_id == kg_id,
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.status != models.DailyReportStatus.DRAFT,
                or_(
                    models.DailyReport.mood == "sick",
                    and_(
                        models.DailyReport.health_notes != None,
                        models.DailyReport.health_notes != "",
                    ),
                ),
            )
            .scalar()
        ) or 0
        health_density = round(health_flagged / total_reports_kg * 100, 1)

        metrics.append(MetricResponse(
            metric="health_alert_density",
            value=health_density,
            chart=_gauge_chart(
                "Health Alert Density (%)", "كثافة التنبيهات الصحية (%)",
                health_density, warn=10, crit=20, lower_is_better=True,
            ),
            locale=locale,
        ))

        # 20. DATA QUALITY SCORE — profile completeness for children & KG
        # ─────────────────────────────────────────────────────
        # Child completeness: first_name, last_name, date_of_birth, gender
        child_fields = ["first_name", "last_name", "date_of_birth", "gender"]
        ch_count = self.db.query(func.count(models.Child.id)).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.Child.deleted_at == None,
        ).scalar() or 1

        ch_complete = self.db.query(func.count(models.Child.id)).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.Child.deleted_at == None,
            models.Child.first_name != None,
            models.Child.last_name != None,
            models.Child.date_of_birth != None,
            models.Child.gender != None,
        ).scalar() or 0

        child_score = round(ch_complete / ch_count * 100, 1)

        # KG completeness: name_ar, governorate, city, area, contact_phone, address_line
        kg_obj = self.db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
        kg_score = 0.0
        if kg_obj:
            kg_fields = [kg_obj.name_ar, kg_obj.governorate, kg_obj.district,
                         kg_obj.area, kg_obj.contact_phone, kg_obj.address_line]
            kg_score = round(sum(1 for f in kg_fields if f) / len(kg_fields) * 100, 1)

        overall_quality = round(0.6 * child_score + 0.4 * kg_score, 1)

        metrics.append(MetricResponse(
            metric="data_quality_score",
            value=overall_quality,
            chart=_chart(
                "bar",
                ["Child Profiles" if locale == "en" else "ملفات الأطفال",
                 "KG Profile" if locale == "en" else "ملف الحضانة",
                 "Overall" if locale == "en" else "الإجمالي"],
                "Data Quality Score (%)", "درجة جودة البيانات (%)",
                [child_score, kg_score, overall_quality],
                bg=[
                    _colour_by_threshold(child_score, 85, 70),
                    _colour_by_threshold(kg_score, 85, 70),
                    _colour_by_threshold(overall_quality, 85, 70),
                ],
                thresholds={"warning": 85, "critical": 70},
            ),
            locale=locale,
        ))

        # 21. AGE APPROPRIATENESS INDEX — % children within correct class age range
        # ─────────────────────────────────────────────────────
        enrollments = (
            self.db.query(
                models.EnrollmentApplication.child_id,
                models.EnrollmentApplication.class_id,
                models.Child.date_of_birth,
                models.Class.min_age_months,
                models.Class.max_age_months,
            )
            .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
            .join(models.Class, models.Class.id == models.EnrollmentApplication.class_id)
            .filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                models.EnrollmentApplication.class_id != None,
            )
            .all()
        )
        appropriate = 0
        for _, _, dob, min_m, max_m in enrollments:
            if dob:
                age_months = (today - dob).days // 30
                if min_m <= age_months <= max_m:
                    appropriate += 1

        age_idx = round(appropriate / len(enrollments) * 100, 1) if enrollments else 100.0

        metrics.append(MetricResponse(
            metric="age_appropriateness_index",
            value=age_idx,
            chart=_chart(
                "pie",
                ["Age-Appropriate" if locale == "en" else "ملائم عمرياً",
                 "Misplaced" if locale == "en" else "غير ملائم"],
                "Age Appropriateness Index (%)", "مؤشر الملاءمة العمرية (%)",
                [float(appropriate), float(max(0, len(enrollments) - appropriate))],
                bg=[C_GOOD, C_CRIT],
                thresholds={"warning": 90, "critical": 80},
            ),
            locale=locale,
        ))

        # 22. SAFEGUARDING RESOLUTION RATE — % cases closed within SLA deadline
        # ─────────────────────────────────────────────────────
        sg_cases = (
            self.db.query(models.SafeguardingCase)
            .filter(models.SafeguardingCase.kindergarten_id == kg_id)
            .all()
        )
        total_sg = len(sg_cases)
        resolved_on_time = sum(
            1 for c in sg_cases
            if c.closed_at and (
                c.sla_closure_deadline is None or c.closed_at <= c.sla_closure_deadline
            )
        )
        sg_rate = round(resolved_on_time / total_sg * 100, 1) if total_sg else 100.0

        metrics.append(MetricResponse(
            metric="safeguarding_resolution_rate",
            value=sg_rate,
            chart=_gauge_chart(
                "Safeguarding Resolution Rate (%)", "معدل حل قضايا الحماية (%)",
                sg_rate, warn=80, crit=60,
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="kindergarten", metrics=metrics, locale=locale)

    # ═══════════════════════════════════════════════════════════════════════
    # CHILD LAYER — Metrics 23-27
    # ═══════════════════════════════════════════════════════════════════════

    def get_child_metrics(self, child_id: int, locale: str = "ar") -> LayerMetricsResponse:
        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=30)

        child = self.db.query(models.Child).filter(models.Child.id == child_id).first()
        child_name = f"{child.first_name} {child.last_name}" if child else str(child_id)

        # 23. CHILD ATTENDANCE PATTERN — last 30 days breakdown bar
        # ─────────────────────────────────────────────────────
        att_logs = (
            self.db.query(models.AttendanceLog.status)
            .filter(
                models.AttendanceLog.child_id == child_id,
                models.AttendanceLog.date.between(window_start, today),
            )
            .all()
        )
        status_counts = {"PRESENT": 0, "LATE": 0, "EXCUSED": 0, "ABSENT": 0}
        for (s,) in att_logs:
            key = str(s.value if hasattr(s, "value") else s)
            if key in status_counts:
                status_counts[key] += 1

        total_att_days = sum(status_counts.values()) or 1
        att_rate_child = round((status_counts["PRESENT"] + status_counts["LATE"]) / total_att_days * 100, 1)

        status_labels = {
            "PRESENT": ("Present" if locale == "en" else "حاضر"),
            "LATE":    ("Late"    if locale == "en" else "متأخر"),
            "EXCUSED": ("Excused" if locale == "en" else "معذور"),
            "ABSENT":  ("Absent"  if locale == "en" else "غائب"),
        }
        metrics.append(MetricResponse(
            metric="child_attendance_pattern",
            value=att_rate_child,
            chart=_chart(
                "bar",
                [status_labels[s] for s in ["PRESENT", "LATE", "EXCUSED", "ABSENT"]],
                "Attendance Pattern (last 30 days)",
                "نمط الحضور (آخر 30 يوماً)",
                [float(status_counts[s]) for s in ["PRESENT", "LATE", "EXCUSED", "ABSENT"]],
                bg=[C_GOOD, C_WARN, C_INFO, C_CRIT],
                thresholds={"min_attendance_rate": 75},
            ),
            locale=locale,
        ))

        # 24. CHILD DEVELOPMENT PROFILE — observations by domain × mastery (radar)
        # ─────────────────────────────────────────────────────
        obs_rows = (
            self.db.query(
                models.Observation.domain,
                models.Observation.mastery_level,
                func.count(models.Observation.id).label("cnt"),
            )
            .filter(models.Observation.child_id == child_id)
            .group_by(models.Observation.domain, models.Observation.mastery_level)
            .all()
        )

        # Compute domain score: ON_TRACK=1, EXCEEDS=1.2, NEEDS_SUPPORT=0.5
        mastery_weights = {"ON_TRACK": 1.0, "EXCEEDS": 1.2, "NEEDS_SUPPORT": 0.5}
        domains = [d.value for d in models.LearningDomain]
        domain_scores: Dict[str, float] = {d: 0.0 for d in domains}
        domain_counts: Dict[str, int]   = {d: 0    for d in domains}
        for domain, mastery, cnt in obs_rows:
            d = domain.value if hasattr(domain, "value") else str(domain)
            m = mastery.value if mastery and hasattr(mastery, "value") else str(mastery)
            w = mastery_weights.get(m, 0.75)
            domain_scores[d] = domain_scores.get(d, 0.0) + w * cnt
            domain_counts[d] = domain_counts.get(d, 0)  + cnt

        radar_values = [
            round(min(100, domain_scores[d] / domain_counts[d] * 100), 1)
            if domain_counts[d] > 0 else 0.0
            for d in domains
        ]
        domain_labels_map = {
            "SOCIAL_EMOTIONAL": ("Social-Emotional" if locale == "en" else "اجتماعي-عاطفي"),
            "PHYSICAL":         ("Physical"         if locale == "en" else "جسدي"),
            "COGNITIVE":        ("Cognitive"        if locale == "en" else "معرفي"),
            "LANGUAGE":         ("Language"         if locale == "en" else "لغوي"),
        }
        radar_labels = [domain_labels_map.get(d, d) for d in domains]
        avg_dev_score = round(sum(radar_values) / len(radar_values), 1) if radar_values else 0.0

        metrics.append(MetricResponse(
            metric="child_development_profile",
            value=avg_dev_score,
            chart=_chart(
                "radar",
                radar_labels,
                "Development Profile by Domain",
                "ملف التطور بحسب المجال",
                radar_values,
                bg=[C_TEAL] * len(radar_values),
                thresholds={"min_domain_score": 60},
            ),
            locale=locale,
        ))

        # 25. CHILD ENGAGEMENT SCORE — meal avg + nap rate + mood score
        # ─────────────────────────────────────────────────────
        dr_rows = (
            self.db.query(
                models.DailyReport.breakfast,
                models.DailyReport.snack,
                models.DailyReport.milk,
                models.DailyReport.lunch,
                models.DailyReport.nap_duration_minutes,
                models.DailyReport.mood,
            )
            .filter(
                models.DailyReport.child_id == child_id,
                models.DailyReport.date.between(window_start, today),
                models.DailyReport.status != models.DailyReportStatus.DRAFT,
            )
            .all()
        )
        if dr_rows:
            n = len(dr_rows)
            meal_score = round(
                sum(sum([b or 0, s or 0, m or 0, l or 0])
                    for b, s, m, l, _, __ in dr_rows) / (4 * n) * 100, 1
            )
            nap_rate = round(
                sum(1 for *_, nap, __ in dr_rows if nap and nap > 0) / n * 100, 1
            )
            mood_weights = {"happy": 100, "normal": 75, "tired": 50, "sad": 25, "sick": 0}
            mood_score = round(
                sum(mood_weights.get(str(mood) if mood else "normal", 75)
                    for *_, mood in dr_rows) / n, 1
            )
            engagement_score = round(0.4 * meal_score + 0.3 * nap_rate + 0.3 * mood_score, 1)
        else:
            meal_score = nap_rate = mood_score = engagement_score = 0.0

        metrics.append(MetricResponse(
            metric="child_engagement_score",
            value=engagement_score,
            chart=_chart(
                "bar",
                ["Meal Score" if locale == "en" else "درجة الوجبات",
                 "Nap Rate"   if locale == "en" else "معدل القيلولة",
                 "Mood Score" if locale == "en" else "درجة المزاج",
                 "Engagement" if locale == "en" else "المشاركة الكلية"],
                "Child Engagement Breakdown",
                "تفصيل مشاركة الطفل",
                [meal_score, nap_rate, mood_score, engagement_score],
                bg=[
                    _colour_by_threshold(meal_score, 80, 60),
                    _colour_by_threshold(nap_rate, 70, 50),
                    _colour_by_threshold(mood_score, 75, 50),
                    _colour_by_threshold(engagement_score, 75, 55),
                ],
                thresholds={"warning": 75, "critical": 55},
            ),
            locale=locale,
        ))

        # 26. CHILD INCIDENT HISTORY — incidents by severity (last 90 days)
        # ─────────────────────────────────────────────────────
        inc_90 = today - timedelta(days=90)
        inc_rows = (
            self.db.query(
                models.Incident.severity_level,
                func.count(models.Incident.id).label("cnt"),
            )
            .filter(
                models.Incident.child_id == child_id,
                models.Incident.occurred_at >= datetime.combine(inc_90, datetime.min.time()),
                models.Incident.deleted_at == None,
            )
            .group_by(models.Incident.severity_level)
            .all()
        )
        sev_map: Dict[str, int] = {}
        for sev, cnt in inc_rows:
            s = sev.value if hasattr(sev, "value") else str(sev)
            sev_map[s] = cnt

        sev_labels_map = {
            "LOW":      ("Low"      if locale == "en" else "منخفض"),
            "MEDIUM":   ("Medium"   if locale == "en" else "متوسط"),
            "HIGH":     ("High"     if locale == "en" else "مرتفع"),
            "CRITICAL": ("Critical" if locale == "en" else "حرج"),
        }
        ordered_sevs = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        metrics.append(MetricResponse(
            metric="child_incident_history",
            value=float(sum(sev_map.values())),
            chart=_chart(
                "bar",
                [sev_labels_map[s] for s in ordered_sevs],
                "Incidents by Severity (last 90 days)",
                "الحوادث بحسب الخطورة (آخر 90 يوماً)",
                [float(sev_map.get(s, 0)) for s in ordered_sevs],
                bg=[C_INFO, C_WARN, C_ORANGE, C_CRIT],
                thresholds={"high_severity_alert": 1},
            ),
            locale=locale,
        ))

        # 27. CHILD HEALTH ALERTS — health alert count + sick mood days
        # ─────────────────────────────────────────────────────
        ha_count = (
            self.db.query(func.count(models.HealthAlert.id))
            .filter(models.HealthAlert.child_id == child_id)
            .scalar()
        ) or 0
        sick_days = (
            self.db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.child_id == child_id,
                models.DailyReport.mood == "sick",
                models.DailyReport.date.between(window_start, today),
            )
            .scalar()
        ) or 0

        metrics.append(MetricResponse(
            metric="child_health_alerts",
            value=float(ha_count + sick_days),
            chart=_chart(
                "bar",
                ["Health Alerts" if locale == "en" else "تنبيهات صحية",
                 "Sick Days (30d)" if locale == "en" else "أيام مرض (30 يوم)"],
                "Child Health Signals",
                "إشارات صحة الطفل",
                [float(ha_count), float(sick_days)],
                bg=[C_ORANGE, C_CRIT],
                thresholds={"alert_warning": 2, "alert_critical": 5},
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="child", metrics=metrics, locale=locale)

    # ═══════════════════════════════════════════════════════════════════════
    # PREDICTIVE LAYER — Metrics 28-31
    # ═══════════════════════════════════════════════════════════════════════

    def get_predictive_metrics(self, locale: str = "ar") -> LayerMetricsResponse:
        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=90)

        # 28. DROPOUT RISK — per-KG composite risk score
        # High risk = low attendance trend + incident spike + low enrollment growth
        # ─────────────────────────────────────────────────────
        kgs = (
            self.db.query(models.Kindergarten)
            .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
            .all()
        )
        kg_risk_labels: List[str] = []
        kg_risk_values: List[float] = []

        for kg in kgs:
            # 90-day attendance trend slope
            week_rates_kg: List[float] = []
            for w in range(12, 0, -1):
                wk_s = today - timedelta(days=w * 7)
                wk_e = today - timedelta(days=(w - 1) * 7)
                row = (
                    self.db.query(
                        func.count(models.AttendanceLog.id).label("tot"),
                        func.sum(case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("pres"),
                    )
                    .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
                    .filter(
                        models.Class.kindergarten_id == kg.id,
                        models.AttendanceLog.date.between(wk_s, wk_e),
                    )
                    .first()
                )
                t = row.tot or 0
                p = row.pres or 0
                week_rates_kg.append(p / t * 100 if t else 0.0)

            trend_slope = _slope(week_rates_kg)
            last_att = week_rates_kg[-1] if week_rates_kg else 0.0

            # High-severity incidents last 90 days
            hi_inc = (
                self.db.query(func.count(models.Incident.id))
                .filter(
                    models.Incident.kindergarten_id == kg.id,
                    models.Incident.severity_level.in_(["HIGH", "CRITICAL"]),
                    models.Incident.occurred_at >= datetime.combine(window_start, datetime.min.time()),
                    models.Incident.deleted_at == None,
                )
                .scalar()
            ) or 0

            # Risk: attendance deficit contributes 40%, negative trend 30%, incidents 30%
            att_risk  = max(0, (85 - last_att) / 85 * 40) if last_att < 85 else 0
            trend_risk = max(0, min(30, -trend_slope * 10)) if trend_slope < 0 else 0
            inc_risk   = min(30, hi_inc * 10)
            risk_score = round(att_risk + trend_risk + inc_risk, 1)

            kg_risk_labels.append(kg.name_en or kg.name_ar or str(kg.id))
            kg_risk_values.append(risk_score)

        avg_risk = round(sum(kg_risk_values) / len(kg_risk_values), 1) if kg_risk_values else 0.0

        metrics.append(MetricResponse(
            metric="dropout_risk",
            value=avg_risk,
            chart=_chart(
                "bar",
                kg_risk_labels[:15],  # top 15 KGs for readability
                "Dropout / Disengagement Risk Score (0-100)",
                "درجة خطر التسرب / عدم المشاركة (0-100)",
                kg_risk_values[:15],
                bg=[
                    _colour_by_threshold(v, 30, 60, lower_is_better=True)
                    for v in kg_risk_values[:15]
                ],
                thresholds={"warning": 30, "critical": 60},
            ),
            locale=locale,
        ))

        # 29. PERFORMANCE TRAJECTORY — classify each KG as improving/stable/declining
        # ─────────────────────────────────────────────────────
        improving = stable = declining = 0
        for kg in kgs:
            # Re-use kg_risk_labels order
            idx = kg_risk_labels.index(kg.name_en or kg.name_ar or str(kg.id)) \
                  if (kg.name_en or kg.name_ar or str(kg.id)) in kg_risk_labels else -1
            if idx < 0:
                continue
            # Build 90-day weekly attendance
            wk_rates: List[float] = []
            for w in range(12, 0, -1):
                wk_s = today - timedelta(days=w * 7)
                wk_e = today - timedelta(days=(w - 1) * 7)
                row = (
                    self.db.query(
                        func.count(models.AttendanceLog.id).label("tot"),
                        func.sum(case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("pres"),
                    )
                    .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
                    .filter(
                        models.Class.kindergarten_id == kg.id,
                        models.AttendanceLog.date.between(wk_s, wk_e),
                    )
                    .first()
                )
                t = row.tot or 0
                p = row.pres or 0
                wk_rates.append(p / t * 100 if t else 0.0)

            sl = _slope(wk_rates)
            if sl > 0.3:
                improving += 1
            elif sl < -0.3:
                declining += 1
            else:
                stable += 1

        traj_labels = [
            "Improving" if locale == "en" else "متحسّن",
            "Stable"    if locale == "en" else "مستقر",
            "Declining" if locale == "en" else "متراجع",
        ]
        metrics.append(MetricResponse(
            metric="performance_trajectory",
            value=float(improving),
            chart=_chart(
                "pie",
                traj_labels,
                "KG Performance Trajectory",
                "مسار أداء الحضانات",
                [float(improving), float(stable), float(declining)],
                bg=[C_GOOD, C_WARN, C_CRIT],
            ),
            locale=locale,
        ))

        # 30. ENROLLMENT FORECAST — linear 30-day forecast
        # ─────────────────────────────────────────────────────
        # Build monthly enrollment counts for last 12 months
        monthly_enr: List[float] = []
        month_labels: List[str] = []
        for m in range(11, -1, -1):
            ms = (today.replace(day=1) - timedelta(days=m * 30)).replace(day=1)
            me = (ms + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            cnt = (
                self.db.query(func.count(models.EnrollmentApplication.id))
                .filter(
                    models.EnrollmentApplication.status.in_(["ACTIVE", "ACCEPTED"]),
                    func.date(models.EnrollmentApplication.created_at).between(ms, me),
                )
                .scalar()
            ) or 0
            monthly_enr.append(float(cnt))
            month_labels.append(ms.strftime("%b %Y"))

        # Forecast next 3 months
        forecast_vals = _linear_forecast(monthly_enr, 3)
        next_months = [
            (today.replace(day=1) + timedelta(days=(i + 1) * 30)).strftime("%b %Y")
            for i in range(3)
        ]

        all_labels = month_labels + next_months
        all_values = monthly_enr + forecast_vals
        # Forecast points in a different colour
        bg_colors = [C_INFO] * 12 + [C_PURPLE] * 3

        metrics.append(MetricResponse(
            metric="enrollment_forecast",
            value=forecast_vals[-1] if forecast_vals else 0.0,
            chart=ChartConfig(
                type="line",
                labels=all_labels,
                datasets=[
                    ChartDataset(
                        label={"en": "Historical Enrollment", "ar": "التسجيل التاريخي"},
                        data=monthly_enr + [None] * 3,  # type: ignore[list-item]
                        backgroundColor=[C_INFO] * 12 + ["transparent"] * 3,
                        borderColor=[C_INFO] * 15,
                    ),
                    ChartDataset(
                        label={"en": "Forecast", "ar": "التوقع"},
                        data=[None] * 12 + forecast_vals,  # type: ignore[list-item]
                        backgroundColor=["transparent"] * 12 + [C_PURPLE] * 3,
                        borderColor=[C_PURPLE] * 15,
                    ),
                ],
                thresholds=None,
                colors=SEMANTIC_COLORS,
            ),
            locale=locale,
        ))

        # 31. ANOMALY CROSS-CORRELATION — detect if attendance drop co-occurs with incident spike
        # ─────────────────────────────────────────────────────
        # Pearson correlation between weekly attendance rate and weekly incident count (last 12 weeks)
        weekly_att: List[float] = []
        weekly_inc: List[float] = []
        w_labels: List[str] = []
        for w in range(11, -1, -1):
            wk_s = today - timedelta(days=(w + 1) * 7)
            wk_e = today - timedelta(days=w * 7)
            a_row = self.db.query(
                func.count(models.AttendanceLog.id).label("tot"),
                func.sum(case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("pres"),
            ).filter(models.AttendanceLog.date.between(wk_s, wk_e)).first()
            t = a_row.tot or 0
            p = a_row.pres or 0
            weekly_att.append(p / t * 100 if t else 0.0)

            i_count = (
                self.db.query(func.count(models.Incident.id))
                .filter(
                    models.Incident.occurred_at.between(
                        datetime.combine(wk_s, datetime.min.time()),
                        datetime.combine(wk_e, datetime.max.time()),
                    ),
                    models.Incident.deleted_at == None,
                )
                .scalar()
            ) or 0
            weekly_inc.append(float(i_count))
            w_labels.append(f"W-{11 - w}")

        # Pearson r
        def pearson(xs: List[float], ys: List[float]) -> float:
            n = len(xs)
            if n < 3:
                return 0.0
            mx = sum(xs) / n
            my = sum(ys) / n
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            dx  = sqrt(sum((x - mx) ** 2 for x in xs))
            dy  = sqrt(sum((y - my) ** 2 for y in ys))
            return round(num / (dx * dy), 3) if dx * dy else 0.0

        corr = pearson(weekly_att, weekly_inc)
        corr_color = C_CRIT if corr < -0.5 else (C_WARN if corr < -0.2 else C_GOOD)

        metrics.append(MetricResponse(
            metric="anomaly_cross_correlation",
            value=corr,
            chart=ChartConfig(
                type="line",
                labels=w_labels,
                datasets=[
                    ChartDataset(
                        label={"en": "Attendance Rate (%)", "ar": "معدل الحضور (%)"},
                        data=weekly_att,
                        backgroundColor=[C_INFO] * 12,
                        borderColor=[C_INFO] * 12,
                    ),
                    ChartDataset(
                        label={"en": "Incident Count", "ar": "عدد الحوادث"},
                        data=weekly_inc,
                        backgroundColor=[C_CRIT] * 12,
                        borderColor=[C_CRIT] * 12,
                    ),
                ],
                thresholds={"strong_neg_corr": -0.5, "pearson_r": corr},
                colors=SEMANTIC_COLORS,
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="predictive", metrics=metrics, locale=locale)

    # ═══════════════════════════════════════════════════════════════════════
    # GOVERNANCE LAYER — Metrics 32-33
    # ═══════════════════════════════════════════════════════════════════════

    def get_governance_metrics(self, locale: str = "ar") -> LayerMetricsResponse:
        from governance_kpi_service import compute_full_gqi

        metrics: List[MetricResponse] = []
        today = _today()
        window_start = today - timedelta(days=30)
        
        # Pull centralized GQI
        gqi_data = compute_full_gqi(self.db, window_start, today, None)
        enhanced_gqi = gqi_data["gqi"]
        sub_indicators = gqi_data["sub_indicators"]
        
        si_report = sub_indicators.get("report_submission", 0)
        si_training = sub_indicators.get("training_coverage", 0)

        sub_scores = {
            "Report Submission" if locale == "en" else "تقديم التقارير":     si_report,
            "Delivery Compliance" if locale == "en" else "توصيل التقارير":   sub_indicators.get("delivery_compliance", 0),
            "Approval Quality"  if locale == "en" else "جودة الاعتماد":      sub_indicators.get("approval_quality", 0),
            "Review Rate"       if locale == "en" else "معدل المشاهدة":      sub_indicators.get("review_rate", 0),
            "Training Coverage" if locale == "en" else "تغطية التدريب":      si_training,
            "License Validity"  if locale == "en" else "صلاحية التراخيص":    sub_indicators.get("license_validity", 0),
            "Incident SLA"      if locale == "en" else "SLA الحوادث":        sub_indicators.get("incident_sla", 0),
        }
        
        gqi_colors = [_colour_by_threshold(v, 80, 60) for v in sub_scores.values()]

        # 32. ENHANCED GQI — radar over 7 sub-indicators
        metrics.append(MetricResponse(
            metric="enhanced_gqi",
            value=enhanced_gqi,
            chart=_chart(
                "radar",
                list(sub_scores.keys()),
                "Enhanced Governance Quality Index (7 sub-indicators)",
                "مؤشر جودة الحوكمة المحسّن (7 مؤشرات فرعية)",
                list(sub_scores.values()),
                bg=gqi_colors,
                thresholds={"warning": 80, "critical": 60},
            ),
            locale=locale,
        ))

        # ── Data Quality (wired from DataQualityMetric) ──
        dqm_row = (
            self.db.query(
                func.avg(models.DataQualityMetric.completeness_percent),
                func.avg(models.DataQualityMetric.timeliness_score),
                func.avg(models.DataQualityMetric.consistency_score),
            )
            .filter(models.DataQualityMetric.entity_type == "NETWORK")
            .first()
        )
        if dqm_row and dqm_row[0] is not None:
            si_dq = round(
                (dqm_row[0] or 0) * 0.4
                + (dqm_row[1] or 0) * 0.4
                + (dqm_row[2] or 0) * 0.2,
                1,
            )
        else:
            ch_total = self.db.query(func.count(models.Child.id)).filter(models.Child.deleted_at == None).scalar() or 1
            ch_complete = (
                self.db.query(func.count(models.Child.id))
                .filter(
                    models.Child.deleted_at == None,
                    models.Child.first_name != None,
                    models.Child.last_name != None,
                    models.Child.date_of_birth != None,
                )
                .scalar()
            ) or 0
            si_dq = round(ch_complete / ch_total * 100, 1)

        # 33. NETWORK HEALTH COMPOSITE — stacked bar of all major KPIs
        net_att_row = self.db.query(
            func.count(models.AttendanceLog.id).label("tot"),
            func.sum(case((models.AttendanceLog.status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("pres"),
        ).filter(models.AttendanceLog.date.between(window_start, today)).first()
        net_att_rate  = round((net_att_row.pres or 0) / (net_att_row.tot or 1) * 100, 1)

        cap_row2 = self.db.query(
            func.sum(models.Class.capacity_total).label("cap"),
            func.sum(models.Class.enrolled_children_count).label("enr"),
        ).filter(models.Class.is_active == True, models.Class.deleted_at == None).first()
        capacity_util = round((cap_row2.enr or 0) / (cap_row2.cap or 1) * 100, 1)

        composite_scores = {
            "Attendance"   if locale == "en" else "الحضور":             net_att_rate,
            "GQI"          if locale == "en" else "جودة الحوكمة":       enhanced_gqi,
            "Data Quality" if locale == "en" else "جودة البيانات":      si_dq,
            "Report Rate"  if locale == "en" else "معدل التقارير":       si_report,
            "Training"     if locale == "en" else "التدريب":             si_training,
            "Capacity"     if locale == "en" else "الاستيعاب":           capacity_util,
        }
        composite_vals = list(composite_scores.values())
        overall_health = round(sum(composite_vals) / len(composite_vals), 1)
        health_colors  = [_colour_by_threshold(v, 80, 65) for v in composite_vals]

        metrics.append(MetricResponse(
            metric="network_health_composite",
            value=overall_health,
            chart=_chart(
                "bar",
                list(composite_scores.keys()),
                "Network Health Composite Score",
                "درجة صحة الشبكة الإجمالية",
                composite_vals,
                bg=health_colors,
                thresholds={"warning": 80, "critical": 65},
            ),
            locale=locale,
        ))

        return LayerMetricsResponse(layer="governance", metrics=metrics, locale=locale)
