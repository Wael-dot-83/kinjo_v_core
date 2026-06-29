"""
Jordan Heat Map — shared constants and configuration.

This module is the single source of truth for:
- The 12 Jordan governorates and their codes, names, centroids
- The 6 main indicators and their labels (Arabic / English)
- The sub-indicators per main indicator
- The risk thresholds and the canonical color scale
- Recommended actions and thresholds per sub-indicator

Anywhere in the codebase that needs a governorate, indicator, or risk color
MUST import from this module instead of redefining the list.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Jordan Governorates (the 12 administrative governorates)
# ---------------------------------------------------------------------------
# Code format: JO-<ISO-3166-2 like> upper-case. Names follow project standard:
#   name_en — English label used in DB columns and CSV exports
#   name_ar — Arabic label used in UI (RTL)
#   center  — (longitude, latitude) for map centroid / marker placement
GOVERNORATES: List[Dict] = [
    {"code": "JO-AM", "slug": "amman",   "name_en": "Amman",   "name_ar": "عمان",     "center": [35.95, 31.95], "display_order": 1},
    {"code": "JO-IR", "slug": "irbid",   "name_en": "Irbid",   "name_ar": "إربد",     "center": [35.85, 32.55], "display_order": 2},
    {"code": "JO-ZA", "slug": "zarqa",   "name_en": "Zarqa",   "name_ar": "الزرقاء",  "center": [36.10, 32.07], "display_order": 3},
    {"code": "JO-MA", "slug": "mafraq",  "name_en": "Mafraq",  "name_ar": "المفرق",   "center": [36.20, 32.34], "display_order": 4},
    {"code": "JO-JA", "slug": "jerash",  "name_en": "Jerash",  "name_ar": "جرش",      "center": [35.90, 32.28], "display_order": 5},
    {"code": "JO-AJ", "slug": "ajloun",  "name_en": "Ajloun",  "name_ar": "عجلون",    "center": [35.75, 32.33], "display_order": 6},
    {"code": "JO-BA", "slug": "balqa",   "name_en": "Balqa",   "name_ar": "البلقاء",   "center": [35.78, 32.04], "display_order": 7},
    {"code": "JO-MD", "slug": "madaba",  "name_en": "Madaba",  "name_ar": "مادبا",    "center": [35.79, 31.72], "display_order": 8},
    {"code": "JO-KA", "slug": "karak",   "name_en": "Karak",   "name_ar": "الكرك",    "center": [35.70, 31.18], "display_order": 9},
    {"code": "JO-TA", "slug": "tafileh", "name_en": "Tafileh", "name_ar": "الطفيلة",   "center": [35.60, 30.83], "display_order": 10},
    {"code": "JO-MN", "slug": "maan",    "name_en": "Ma'an",   "name_ar": "معان",     "center": [35.73, 30.20], "display_order": 11},
    {"code": "JO-AQ", "slug": "aqaba",   "name_en": "Aqaba",   "name_ar": "العقبة",   "center": [35.00, 29.53], "display_order": 12},
]

GOVERNORATE_BY_SLUG: Dict[str, Dict] = {g["slug"]: g for g in GOVERNORATES}
GOVERNORATE_BY_CODE: Dict[str, Dict] = {g["code"]: g for g in GOVERNORATES}

# Lookup for the existing string-typed `governorate` column in the
# kindergartens / incidents / reports tables.  Maps Arabic & English variants
# to a stable slug we can use as a URL parameter and in `data-gov-id`.
GOVERNORATE_NAME_ALIASES: Dict[str, str] = {}
for g in GOVERNORATES:
    GOVERNORATE_NAME_ALIASES[g["name_en"].lower()] = g["slug"]
    GOVERNORATE_NAME_ALIASES[g["name_en"]] = g["slug"]
    GOVERNORATE_NAME_ALIASES[g["name_ar"]] = g["slug"]
    GOVERNORATE_NAME_ALIASES[g["name_ar"].replace("أ", "ا").replace("إ", "ا")] = g["slug"]
    GOVERNORATE_NAME_ALIASES[g["name_ar"].replace("ة", "ه")] = g["slug"]
# Official Jordanian admin name for Amman governorate
GOVERNORATE_NAME_ALIASES["العاصمة"] = "amman"
GOVERNORATE_NAME_ALIASES["عاصمة"] = "amman"


def normalize_governorate(value: str) -> str:
    """Return the canonical slug for a free-form governorate string."""
    if not value:
        return ""
    v = str(value).strip()
    if v in GOVERNORATE_BY_SLUG:
        return v
    if v in GOVERNORATE_BY_CODE:
        return GOVERNORATE_BY_CODE[v]["slug"]
    return GOVERNORATE_NAME_ALIASES.get(v, GOVERNORATE_NAME_ALIASES.get(v.lower(), v.lower()))


# ---------------------------------------------------------------------------
# Main indicators (6 composite indicators)
# ---------------------------------------------------------------------------
# Each main indicator is a 0–100 score; higher = better (with the
# exception of safety_incidents where higher score = safer operations).
MAIN_INDICATORS: List[Dict] = [
    {
        "key": "nursery_status",
        "name_en": "Nursery Status",
        "name_ar": "حالة الروضات",
        "color": "#0E334F",
        "description_en": "Active vs inactive nurseries in the governorate.",
        "description_ar": "الروضات النشطة مقابل غير النشطة في المحافظة.",
    },
    {
        "key": "children_registration",
        "name_en": "Children & Registration",
        "name_ar": "الأطفال والتسجيل",
        "color": "#28A745",
        "description_en": "Registration completion and age distribution.",
        "description_ar": "نسبة التسجيل وتوزيع الأطفال حسب الفئة العمرية.",
    },
    {
        "key": "staff_classrooms",
        "name_en": "Staff & Classrooms",
        "name_ar": "الموظفون والفصول",
        "color": "#155ECF",
        "description_en": "Supervisor coverage and child-to-staff ratios.",
        "description_ar": "تغطية المشرفين ونسب الأطفال إلى الموظفين.",
    },
    {
        "key": "safety_incidents",
        "name_en": "Safety & Incidents",
        "name_ar": "السلامة والحوادث",
        "color": "#FFC107",
        "description_en": "Severity-adjusted safety incident score.",
        "description_ar": "نقاط السلامة المعدلة حسب خطورة الحوادث.",
    },
    {
        "key": "reports_attendance",
        "name_en": "Reports & Attendance",
        "name_ar": "التقارير والحضور",
        "color": "#06B6D4",
        "description_en": "Daily report completeness and absence profile.",
        "description_ar": "اكتمال التقارير اليومية وملف الغياب.",
    },
    {
        "key": "tasks_governance",
        "name_en": "Tasks & Governance",
        "name_ar": "المهام والحوكمة",
        "color": "#8B5CF6",
        "description_en": "Governance score, training and overdue tasks.",
        "description_ar": "نقطة الحوكمة والتدريب والمهام المتأخرة.",
    },
]

INDICATOR_KEYS: List[str] = [i["key"] for i in MAIN_INDICATORS]
INDICATOR_BY_KEY: Dict[str, Dict] = {i["key"]: i for i in MAIN_INDICATORS}

# The minimum acceptable score (alert threshold) for each main indicator.
INDICATOR_ALERT_THRESHOLD: Dict[str, float] = {
    "nursery_status":        70.0,
    "children_registration": 75.0,
    "staff_classrooms":      80.0,
    "safety_incidents":      85.0,
    "reports_attendance":    70.0,
    "tasks_governance":      65.0,
}


# ---------------------------------------------------------------------------
# Sub-indicators (per main indicator)
# ---------------------------------------------------------------------------
SUB_INDICATORS: Dict[str, List[Dict]] = {
    "nursery_status": [
        {"key": "active_nurseries",      "name_en": "Active nurseries",      "name_ar": "روضات نشطة",          "unit": "count", "threshold_high": 200, "threshold_low": 50,  "higher_is_better": True},
        {"key": "inactive_nurseries",    "name_en": "Inactive nurseries",    "name_ar": "روضات غير نشطة",       "unit": "count", "threshold_high": 30,  "threshold_low": 10,  "higher_is_better": False},
        {"key": "active_pct",            "name_en": "Active %",              "name_ar": "نسبة النشطة",          "unit": "pct",   "threshold_high": 90,  "threshold_low": 75,  "higher_is_better": True},
        {"key": "inactive_pct",          "name_en": "Inactive %",            "name_ar": "نسبة غير النشطة",      "unit": "pct",   "threshold_high": 25,  "threshold_low": 10,  "higher_is_better": False},
    ],
    "children_registration": [
        {"key": "registered_children",   "name_en": "Registered children",   "name_ar": "أطفال مسجلين",         "unit": "count", "threshold_high": 5000, "threshold_low": 1000, "higher_is_better": True},
        {"key": "unregistered_children", "name_en": "Unregistered children", "name_ar": "أطفال غير مسجلين",     "unit": "count", "threshold_high": 500,  "threshold_low": 100,  "higher_is_better": False},
        {"key": "registration_rate",     "name_en": "Registration rate",     "name_ar": "نسبة التسجيل",          "unit": "pct",   "threshold_high": 90,   "threshold_low": 75,   "higher_is_better": True},
        {"key": "age_distribution",      "name_en": "Children by age group", "name_ar": "الأطفال حسب العمر",     "unit": "count", "threshold_high": 1500, "threshold_low": 200,  "higher_is_better": True},
    ],
    "staff_classrooms": [
        {"key": "supervisors_count",     "name_en": "Supervisors",           "name_ar": "المشرفون",            "unit": "count", "threshold_high": 80,  "threshold_low": 20, "higher_is_better": True},
        {"key": "classrooms_count",      "name_en": "Classrooms",            "name_ar": "الفصول",              "unit": "count", "threshold_high": 150, "threshold_low": 40, "higher_is_better": True},
        {"key": "classrooms_no_supervisor","name_en": "Unsupervised classrooms","name_ar": "فصول بدون مشرف",   "unit": "count", "threshold_high": 10,  "threshold_low": 0,  "higher_is_better": False},
        {"key": "child_supervisor_ratio","name_en": "Child-supervisor ratio","name_ar": "نسبة طفل/مشرف",      "unit": "ratio", "threshold_high": 25,  "threshold_low": 15, "higher_is_better": False},
        {"key": "child_teacher_ratio",   "name_en": "Child-teacher ratio",   "name_ar": "نسبة طفل/معلمة",     "unit": "ratio", "threshold_high": 20,  "threshold_low": 12, "higher_is_better": False},
    ],
    "safety_incidents": [
        {"key": "incidents_total",       "name_en": "Total incidents",       "name_ar": "مجموع الحوادث",       "unit": "count", "threshold_high": 50,  "threshold_low": 5,  "higher_is_better": False},
        {"key": "incidents_critical",    "name_en": "Critical incidents",    "name_ar": "حوادث حرجة",          "unit": "count", "threshold_high": 5,   "threshold_low": 0,  "higher_is_better": False},
        {"key": "protection_cases",      "name_en": "Protection cases",      "name_ar": "حالات الحماية",        "unit": "count", "threshold_high": 8,   "threshold_low": 0,  "higher_is_better": False},
        {"key": "incident_severity",     "name_en": "Severity level",        "name_ar": "مستوى الخطورة",        "unit": "score", "threshold_high": 30,  "threshold_low": 5,  "higher_is_better": False},
    ],
    "reports_attendance": [
        {"key": "reports_submitted",     "name_en": "Daily reports submitted","name_ar": "تقارير مقدمة",        "unit": "count", "threshold_high": 50,  "threshold_low": 10, "higher_is_better": True},
        {"key": "reports_missing",       "name_en": "Missing reports",       "name_ar": "تقارير مفقودة",        "unit": "count", "threshold_high": 10,  "threshold_low": 0,  "higher_is_better": False},
        {"key": "absence_rate",          "name_en": "Absence rate",          "name_ar": "نسبة الغياب",          "unit": "pct",   "threshold_high": 20,  "threshold_low": 5,  "higher_is_better": False},
        {"key": "health_absences",       "name_en": "Health absences",       "name_ar": "غيابات صحية",          "unit": "count", "threshold_high": 20,  "threshold_low": 0,  "higher_is_better": False},
        {"key": "repeated_health",       "name_en": "Repeated health absences","name_ar": "غيابات صحية متكررة","unit": "count", "threshold_high": 5,   "threshold_low": 0,  "higher_is_better": False},
    ],
    "tasks_governance": [
        {"key": "delayed_tasks",         "name_en": "Delayed tasks",         "name_ar": "مهام متأخرة",          "unit": "count", "threshold_high": 30,  "threshold_low": 5,  "higher_is_better": False},
        {"key": "governance_score",      "name_en": "Governance score",      "name_ar": "نقطة الحوكمة",         "unit": "score", "threshold_high": 85,  "threshold_low": 60, "higher_is_better": True},
        {"key": "training_completion",   "name_en": "Training completion",   "name_ar": "إكمال التدريب",        "unit": "pct",   "threshold_high": 90,  "threshold_low": 70, "higher_is_better": True},
        {"key": "compliance_status",     "name_en": "Compliance status",     "name_ar": "حالة الامتثال",        "unit": "pct",   "threshold_high": 90,  "threshold_low": 75, "higher_is_better": True},
    ],
}


# ---------------------------------------------------------------------------
# Risk thresholds (0–100 scale)
# ---------------------------------------------------------------------------
# A higher indicator value is treated as "healthier", therefore a high
# indicator value yields a low risk score and vice-versa.  The map shows the
# risk score (or the selected indicator value, depending on the UI mode).
RISK_LEVELS: List[Dict] = [
    {"key": "low",      "name_en": "Low",      "name_ar": "منخفض",   "min": 0,  "max": 24,  "color": "#28A745"},
    {"key": "medium",   "name_en": "Medium",   "name_ar": "متوسط",   "min": 25, "max": 49,  "color": "#FFC107"},
    {"key": "high",     "name_en": "High",     "name_ar": "مرتفع",   "min": 50, "max": 74,  "color": "#FD7E14"},
    {"key": "critical", "name_en": "Critical", "name_ar": "حرج",     "min": 75, "max": 100, "color": "#DC3545"},
]
RISK_BY_KEY: Dict[str, Dict] = {r["key"]: r for r in RISK_LEVELS}


def risk_level_for_score(score: float) -> Dict:
    """Return the canonical risk-level dict for a 0-100 risk score."""
    s = max(0.0, min(100.0, float(score or 0)))
    if s < 25:
        return RISK_BY_KEY["low"]
    if s < 50:
        return RISK_BY_KEY["medium"]
    if s < 75:
        return RISK_BY_KEY["high"]
    return RISK_BY_KEY["critical"]


def risk_level_for_indicator(indicator_key: str, value: float) -> Dict:
    """Return the risk level for a given main indicator value (0-100, higher is better)."""
    threshold = INDICATOR_ALERT_THRESHOLD.get(indicator_key, 70.0)
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    # Invert: 0-100 health → 100-0 risk
    risk = max(0.0, min(100.0, 100.0 - v))
    return risk_level_for_score(risk)


# ---------------------------------------------------------------------------
# Recommended actions per risk level
# ---------------------------------------------------------------------------
RECOMMENDED_ACTIONS: Dict[str, Dict[str, str]] = {
    "low":      {"en": "Continue routine monitoring.",
                 "ar": "متابعة المراقبة الدورية."},
    "medium":   {"en": "Schedule a review within 30 days.",
                 "ar": "جدولة مراجعة خلال 30 يوماً."},
    "high":     {"en": "Assign supervisor and remediate within 14 days.",
                 "ar": "تعيين مشرف ومعالجة الوضع خلال 14 يوماً."},
    "critical": {"en": "Escalate to senior management and remediate within 7 days.",
                 "ar": "التصعيد للإدارة العليا ومعالجة الوضع خلال 7 أيام."},
}


# ---------------------------------------------------------------------------
# Correlation strength levels
# ---------------------------------------------------------------------------
CORRELATION_LEVELS: List[Dict] = [
    {"key": "weak",       "name_en": "Weak",       "name_ar": "ضعيفة",       "min": 0.0,  "max": 0.29, "color": "#94A3B8"},
    {"key": "moderate",   "name_en": "Moderate",   "name_ar": "متوسطة",     "min": 0.30, "max": 0.59, "color": "#3B82F6"},
    {"key": "strong",     "name_en": "Strong",     "name_ar": "قوية",       "min": 0.60, "max": 0.79, "color": "#F59E0B"},
    {"key": "very_strong","name_en": "Very Strong","name_ar": "قوية جداً", "min": 0.80, "max": 1.00, "color": "#DC3545"},
]


def correlation_level_for(value: float) -> Dict:
    a = abs(float(value or 0))
    for level in CORRELATION_LEVELS:
        if level["min"] <= a <= level["max"]:
            return level
    return CORRELATION_LEVELS[-1] if a >= 0.80 else CORRELATION_LEVELS[0]
