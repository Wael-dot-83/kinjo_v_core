"""Registry for Admin official-agency reports.

The registry is intentionally declarative: UI cards, available filters, export
availability, privacy rules, and unsupported-data states are generated from it.
"""
from __future__ import annotations

import os
from typing import Any

AGENCY_REPORT_REGISTRY: dict[str, dict[str, Any]] = {
    "moe": {
        "name_ar": "وزارة التربية والتعليم",
        "name_en": "Ministry of Education",
        "description_ar": "تقدير الأطفال المؤهلين للالتحاق بـ KG2 حسب سكن ولي الأمر والجنس.",
        "icon": "bi-mortarboard",
        "reports": {
            "kg2_eligibility": {
                "title_ar": "تقرير الأطفال المؤهلين لـ KG2",
                "title_en": "KG2 eligibility report",
                "description_ar": "عدد الأطفال الذين أتموا خمس سنوات حسب تاريخ الحسم، مصنفين حسب محافظة ومدينة سكن ولي الأمر والجنس.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "geography_basis": ["parent_residence"],
                "default_geography_basis": "parent_residence",
                "filters": ["admission_year", "governorate", "city", "gender", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "ParentProfile"],
                "required_fields": [
                    "Child.date_of_birth",
                    "Child.gender",
                    "ParentProfile.home_governorate",
                    "ParentProfile.home_district",
                ],
            }
        },
    },
    "moh": {
        "name_ar": "وزارة الصحة",
        "name_en": "Ministry of Health",
        "description_ar": "تقارير المطاعيم والغيابات الصحية عند توفر بيانات صحية منظمة.",
        "icon": "bi-heart-pulse",
        "reports": {
            "vaccination_due_children": {
                "title_ar": "الأطفال المستحقون للمطاعيم",
                "title_en": "Children due for vaccination",
                "status": "requires_structured_data",
                "reason_ar": "يتطلب جدول مطاعيم وطني وسجل مطاعيم منظم لكل طفل.",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city", "age_group"],
                "exports": ["json"],
                "data_sources": ["NationalImmunizationSchedule", "ChildVaccinationRecord"],
            },
            "health_absence_summary": {
                "title_ar": "الغيابات الصحية للأطفال",
                "title_en": "Health absence summary",
                "status": "requires_structured_data",
                "reason_ar": "سبب الغياب الحالي نص حر ولا يجوز تصنيفه صحيًا دون حقل منظم.",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city"],
                "exports": ["json"],
                "data_sources": ["AbsenceRequest", "AbsenceReasonCategory"],
            },
        },
    },
    "dos": {
        "name_ar": "دائرة الإحصاءات العامة",
        "name_en": "Department of Statistics",
        "description_ar": "ملف إحصائي تجميعي للأطفال والحضانات مع قواعد السرية الإحصائية.",
        "icon": "bi-bar-chart-line",
        "reports": {
            "children_statistical_profile": {
                "title_ar": "الملف الإحصائي للأطفال",
                "title_en": "Children statistical profile",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "gender", "age_group", "aggregation_level", "geography_basis"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "ParentProfile", "EnrollmentApplication"],
            }
        },
    },
    "ncfa": {
        "name_ar": "المجلس الوطني لشؤون الأسرة",
        "name_en": "National Council for Family Affairs",
        "description_ar": "تقارير الأسرة والطفولة والرعاية اليومية والسلامة والتواصل العددي.",
        "icon": "bi-people",
        "reports": {
            "child_family_profile": {
                "title_ar": "تقرير الأسرة والطفل",
                "title_en": "Child and family profile",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "gender", "age_group", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "ParentProfile", "EnrollmentApplication"],
            },
            "family_communication_counts": {
                "title_ar": "التواصل العددي مع الأسرة",
                "title_en": "Family communication counts",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "kindergarten_id"],
                "exports": ["json"],
                "data_sources": ["Message"],
            },
        },
    },
    "mol": {
        "name_ar": "وزارة العمل",
        "name_en": "Ministry of Labor",
        "description_ar": "تقارير القوى العاملة والإشراف والحضور والتدريب والامتثال للنسب.",
        "icon": "bi-briefcase",
        "reports": {
            "workforce_summary": {
                "title_ar": "ملخص القوى العاملة في الحضانات",
                "title_en": "Kindergarten workforce summary",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "kindergarten_id", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["User", "Kindergarten", "Class", "SupervisorAssignment"],
            },
            "training_compliance": {
                "title_ar": "التدريب والتأهيل",
                "title_en": "Training compliance",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "kindergarten_id"],
                "exports": ["json"],
                "data_sources": ["TrainingModule", "StaffTrainingCompletion"],
            },
        },
    },
    "mosd": {
        "name_ar": "وزارة التنمية الاجتماعية",
        "name_en": "Ministry of Social Development",
        "description_ar": "تقارير الرعاية والحماية وجودة الحضانات والوصول للخدمة.",
        "icon": "bi-shield-check",
        "reports": {
            "kindergarten_registry": {
                "title_ar": "الحضانات المسجلة وحالتها",
                "title_en": "Kindergarten registry and status",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "status", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Kindergarten"],
            },
            "child_safety_protection": {
                "title_ar": "السلامة وحماية الطفل",
                "title_en": "Child safety and protection",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city", "severity", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Incident", "Kindergarten"],
            },
        },
    },
    "ssc": {
        "name_ar": "المؤسسة العامة للضمان الاجتماعي",
        "name_en": "Social Security Corporation",
        "description_ar": "تقارير الاشتراكات والشمول في الضمان للعاملين في رياض الأطفال عند توفر البيانات المنظمة.",
        "icon": "bi-shield-lock",
        "is_official": True,
        "reports": {
            "coverage_summary": {
                "title_ar": "ملخص شمول العاملين في الضمان",
                "title_en": "Worker social-security coverage summary",
                "status": "requires_structured_data",
                "reason_ar": "يتطلب سجل اشتراكات الضمان المنظم لكل موظف في رياض الأطفال.",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city", "kindergarten_id"],
                "exports": ["json"],
                "data_sources": ["User", "Kindergarten"],
            },
            "nursery_contributions": {
                "title_ar": "مساهمات رياض الأطفال في الضمان",
                "title_en": "Kindergarten social-security contributions",
                "status": "requires_structured_data",
                "reason_ar": "يتطلب بيانات الاشتراكات والمساهمات الشهرية للمنشأة.",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city"],
                "exports": ["json"],
                "data_sources": ["Kindergarten"],
            },
        },
    },
    "mopic": {
        "name_ar": "وزارة التخطيط والتعاون الدولي",
        "name_en": "Ministry of Planning and International Cooperation",
        "description_ar": "تقارير فجوات الوصول وأولويات المحافظات وجاهزية التخطيط.",
        "icon": "bi-diagram-3",
        "reports": {
            "service_access_gaps": {
                "title_ar": "فجوات الوصول لخدمات الطفولة المبكرة",
                "title_en": "Early childhood service access gaps",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "aggregation_level", "geography_basis"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "ParentProfile", "Kindergarten", "EnrollmentApplication"],
            }
        },
    },
}

# ---------------------------------------------------------------------------
# Custom Reports (التقارير المخصصة) — declarative schema
#
# The custom-report builder lets an admin assemble an aggregated report from
# an agency (recipient), a reporting level, a time period, geography, and a
# set of indicators grouped by domain. The schema is declarative so the UI is
# fully backend-driven (no hardcoded/mock option lists in the frontend) and
# the backend can validate every submitted filter against it.
# ---------------------------------------------------------------------------

# Recipient agencies for a custom report. Registry agencies are reused where
# they exist; SSC (Social Security Corporation) is added per requirements.
CUSTOM_REPORT_AGENCIES: list[dict[str, Any]] = [
    {"code": "mosd", "name_ar": "وزارة التنمية الاجتماعية", "name_en": "Ministry of Social Development"},
    {"code": "moe", "name_ar": "وزارة التربية والتعليم", "name_en": "Ministry of Education"},
    {"code": "moh", "name_ar": "وزارة الصحة", "name_en": "Ministry of Health"},
    {"code": "mol", "name_ar": "وزارة العمل", "name_en": "Ministry of Labor"},
    {"code": "ssc", "name_ar": "المؤسسة العامة للضمان الاجتماعي", "name_en": "Social Security Corporation"},
    {"code": "dos", "name_ar": "دائرة الإحصاءات العامة", "name_en": "Department of Statistics"},
    {"code": "ncfa", "name_ar": "المجلس الوطني لشؤون الأسرة", "name_en": "National Council for Family Affairs"},
]

# Reporting levels. child-level is aggregated-only and privacy-gated.
CUSTOM_REPORT_LEVELS: list[dict[str, Any]] = [
    {"code": "national", "name_ar": "المملكة", "name_en": "Jordan"},
    {"code": "governorate", "name_ar": "المحافظة", "name_en": "Governorate"},
    {"code": "city", "name_ar": "المدينة أو اللواء", "name_en": "City/District"},
    {"code": "kindergarten", "name_ar": "الحضانة", "name_en": "Kindergarten"},
    {"code": "class", "name_ar": "الصف", "name_en": "Class"},
    {"code": "child", "name_ar": "الطفل (تجميعي)", "name_en": "Child (aggregated)"},
    {"code": "supervisor", "name_ar": "المشرف", "name_en": "Supervisor"},
    {"code": "manager", "name_ar": "المدير", "name_en": "Manager"},
]

# Time periods. "custom" uses start_date/end_date; the rest are relative to today.
CUSTOM_REPORT_PERIODS: list[dict[str, Any]] = [
    {"code": "day", "name_ar": "يوم", "name_en": "Day", "days": 1},
    {"code": "week", "name_ar": "أسبوع", "name_en": "Week", "days": 7},
    {"code": "month", "name_ar": "شهر", "name_en": "Month", "days": 30},
    {"code": "quarter", "name_ar": "3 أشهر", "name_en": "3 months", "days": 90},
    {"code": "half_year", "name_ar": "6 أشهر", "name_en": "6 months", "days": 180},
    {"code": "year", "name_ar": "سنة", "name_en": "Year", "days": 365},
    {"code": "custom", "name_ar": "نطاق تاريخ مخصص", "name_en": "Custom range", "days": None},
]

# Domains → indicators. `status: "ready"` means the indicator is computed from
# real data; `status: "requires_structured_data"` indicators are surfaced but
# never fabricated — they are reported in data_quality.notes instead.
CUSTOM_REPORT_DOMAINS: list[dict[str, Any]] = [
    {
        "code": "children_enrollment",
        "name_ar": "الأطفال والتسجيل",
        "name_en": "Children & enrollment",
        "indicators": [
            {"code": "children_count", "name_ar": "عدد الأطفال", "status": "ready"},
            {"code": "gender_distribution", "name_ar": "التوزيع حسب الجنس", "status": "ready"},
            {"code": "age_distribution_6mo", "name_ar": "التوزيع العمري كل 6 أشهر", "status": "ready"},
            {"code": "enrollment_status", "name_ar": "حالة التسجيل", "status": "ready"},
        ],
    },
    {
        "code": "kindergartens_capacity",
        "name_ar": "الحضانات والطاقة الاستيعابية",
        "name_en": "Kindergartens & capacity",
        "indicators": [
            {"code": "kindergarten_count", "name_ar": "عدد الحضانات", "status": "ready"},
            {"code": "kindergarten_status", "name_ar": "النشط / غير النشط / المسودة", "status": "ready"},
            {"code": "occupancy_rate", "name_ar": "نسبة الإشغال", "status": "ready"},
        ],
    },
    {
        "code": "attendance",
        "name_ar": "الحضور والغياب",
        "name_en": "Attendance",
        "indicators": [
            {"code": "attendance_rate", "name_ar": "نسبة الحضور", "status": "ready"},
            {"code": "absence_requests", "name_ar": "طلبات الغياب", "status": "ready"},
        ],
    },
    {
        "code": "daily_reports",
        "name_ar": "التقارير اليومية",
        "name_en": "Daily reports",
        "indicators": [
            {"code": "daily_report_completion", "name_ar": "معدل إنجاز التقارير اليومية", "status": "ready"},
            {"code": "late_reports", "name_ar": "التقارير المتأخرة", "status": "ready"},
        ],
    },
    {
        "code": "safety_incidents",
        "name_ar": "السلامة والحوادث",
        "name_en": "Safety & incidents",
        "indicators": [
            {"code": "critical_incidents", "name_ar": "الحوادث الحرجة", "status": "ready"},
            {"code": "incidents_by_severity", "name_ar": "الحوادث حسب الخطورة", "status": "ready"},
        ],
    },
    {
        "code": "staff_supervisors",
        "name_ar": "الموظفون والمشرفون",
        "name_en": "Staff & supervisors",
        "indicators": [
            {"code": "staff_count", "name_ar": "عدد الموظفين", "status": "ready"},
            {"code": "unassigned_classes", "name_ar": "الفصول غير المسندة لمشرف", "status": "ready"},
        ],
    },
    {
        "code": "governance_compliance",
        "name_ar": "الحوكمة والالتزام",
        "name_en": "Governance & compliance",
        "indicators": [
            {"code": "unassigned_children", "name_ar": "الأطفال غير المسجلين في صف", "status": "ready"},
        ],
    },
    {
        "code": "data_quality",
        "name_ar": "جودة البيانات",
        "name_en": "Data quality",
        "indicators": [
            {"code": "data_quality_score", "name_ar": "مؤشر جودة البيانات", "status": "ready"},
        ],
    },
    {
        "code": "health",
        "name_ar": "المؤشرات الصحية",
        "name_en": "Health indicators",
        "indicators": [
            {"code": "vaccination_coverage", "name_ar": "تغطية المطاعيم", "status": "requires_structured_data"},
        ],
    },
    {
        "code": "decision_support",
        "name_ar": "مؤشرات دعم القرار",
        "name_en": "Decision support",
        "indicators": [
            {"code": "service_access_ratio", "name_ar": "أطفال لكل حضانة نشطة", "status": "ready"},
        ],
    },
]


def agency_logo_meta(code: str | None) -> dict[str, Any]:
    """Single source of truth for agency logo/branding metadata.

    `available` is re-checked against the filesystem at call time, so dropping
    an approved official SVG into static/img/agencies/<code>.svg promotes it to
    official automatically. Until then every entry reports available=False and
    the UI renders a neutral initials fallback (never an official logo).
    """
    meta = AGENCY_LOGOS.get(code or "")
    if not meta:
        return {
            "path": None,
            "alt_ar": "",
            "alt_en": "",
            "available": False,
            "official": False,
            "fallback_label": (code or "").upper(),
        }
    rel = meta["logo"].lstrip("/static/")
    file_path = os.path.join("static", rel)
    available = bool(meta.get("asset_present")) and os.path.exists(file_path)
    return {
        "path": meta["logo"] if available else None,
        "alt_ar": meta.get("alt_ar", ""),
        "alt_en": meta.get("alt_en", ""),
        "available": available,
        "official": available,
        "fallback_label": meta.get("fallback", (code or "").upper()),
    }


def custom_report_schema() -> dict[str, Any]:
    """Declarative schema consumed by the frontend and the validator."""
    agencies = []
    for a in CUSTOM_REPORT_AGENCIES:
        entry = dict(a)
        entry["logo"] = agency_logo_meta(a["code"])
        reg = AGENCY_REPORT_REGISTRY.get(a["code"], {})
        entry["description_ar"] = reg.get("description_ar", "")
        agencies.append(entry)
    return {
        "agencies": agencies,
        "levels": CUSTOM_REPORT_LEVELS,
        "periods": CUSTOM_REPORT_PERIODS,
        "domains": CUSTOM_REPORT_DOMAINS,
    }


SENSITIVE_FIELD_DENYLIST = {
    "child_name",
    "parent_name",
    "first_name",
    "last_name",
    "national_id",
    "mother_national_id",
    "passport_number",
    "phone_number",
    "home_address_line",
    "photo_url",
    "photo_metadata",
    "health_notes",
    "medical_notes",
    "allergy_notes",
    "special_needs_notes",
    "description",
    "parent_response",
    "resolution_notes",
    "message_body",
    "feedback_text",
}


# ---------------------------------------------------------------------------
# Official agency scope
# ---------------------------------------------------------------------------
OFFICIAL_AGENCY_CODES: frozenset = frozenset({
    "mosd", "moe", "moh", "mol", "ssc", "dos", "ncfa",
})
for _code, _agency in AGENCY_REPORT_REGISTRY.items():
    _agency.setdefault("is_official", _code in OFFICIAL_AGENCY_CODES)

# ---------------------------------------------------------------------------
# Centralized agency logo / branding metadata
# ---------------------------------------------------------------------------
AGENCY_LOGOS: dict = {
    "mosd": {"name_ar": "وزارة التنمية الاجتماعية", "name_en": "Ministry of Social Development", "logo": "/static/img/agencies/mosd.svg", "fallback": "MOSD", "alt_ar": "شعار وزارة التنمية الاجتماعية", "alt_en": "Ministry of Social Development logo", "asset_present": False},
    "moe": {"name_ar": "وزارة التربية والتعليم", "name_en": "Ministry of Education", "logo": "/static/img/agencies/moe.svg", "fallback": "MOE", "alt_ar": "شعار وزارة التربية والتعليم", "alt_en": "Ministry of Education logo", "asset_present": False},
    "moh": {"name_ar": "وزارة الصحة", "name_en": "Ministry of Health", "logo": "/static/img/agencies/moh.svg", "fallback": "MOH", "alt_ar": "شعار وزارة الصحة", "alt_en": "Ministry of Health logo", "asset_present": False},
    "mol": {"name_ar": "وزارة العمل", "name_en": "Ministry of Labor", "logo": "/static/img/agencies/mol.svg", "fallback": "MOL", "alt_ar": "شعار وزارة العمل", "alt_en": "Ministry of Labor logo", "asset_present": False},
    "ssc": {"name_ar": "المؤسسة العامة للضمان الاجتماعي", "name_en": "Social Security Corporation", "logo": "/static/img/agencies/ssc.svg", "fallback": "SSC", "alt_ar": "شعار المؤسسة العامة للضمان الاجتماعي", "alt_en": "Social Security Corporation logo", "asset_present": False},
    "dos": {"name_ar": "دائرة الإحصاءات العامة", "name_en": "Department of Statistics", "logo": "/static/img/agencies/dos.svg", "fallback": "DOS", "alt_ar": "شعار دائرة الإحصاءات العامة", "alt_en": "Department of Statistics logo", "asset_present": False},
    "ncfa": {"name_ar": "المجلس الوطني لشؤون الأسرة", "name_en": "National Council for Family Affairs", "logo": "/static/img/agencies/ncfa.svg", "fallback": "NCFA", "alt_ar": "شعار المجلس الوطني لشؤون الأسرة", "alt_en": "National Council for Family Affairs logo", "asset_present": False},
}

AGENCY_DISPLAY_ORDER: list = ["mosd", "moe", "moh", "mol", "ssc", "dos", "ncfa"]
