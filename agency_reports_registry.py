"""Registry for Admin official-agency reports.

The registry is intentionally declarative: UI cards, available filters, export
availability, privacy rules, and unsupported-data states are generated from it.
"""
from __future__ import annotations

from typing import Any

AGENCY_REPORT_REGISTRY: dict[str, dict[str, Any]] = {
    "moe": {
        "name_ar": "وزارة التربية والتعليم",
        "name_en": "Ministry of Education",
        "description_ar": "تقدير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2 حسب سكن ولي الأمر والجنس.",
        "icon": "bi-mortarboard",
        "reports": {
            "kg2_eligibility": {
                "title_ar": "تقرير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2",
                "title_en": "KG2 eligibility report",
                "description_ar": "عدد الأطفال البالغين خمس سنوات بحلول تاريخ الحسم، مصنّفين حسب المحافظة واللواء وسكن ولي الأمر والجنس.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "geography_basis": ["parent_residence"],
                "default_geography_basis": "parent_residence",
                "filters": ["admission_year", "governorate", "district", "area", "gender", "aggregation_level"],
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
        "description_ar": "تقارير إحصائية دورية مفصلة لمتخذي القرار وفق المعايير المعتمدة.",
        "icon": "bi-bar-chart-line",
        "reports": {
            "children_demographics": {
                "title_ar": "التركيبة الديموغرافية للأطفال",
                "title_en": "Children demographics",
                "description_ar": "توزيع الأطفال المسجّلين حسب المحافظة والجنس والفئة العمرية، استناداً إلى سكن ولي الأمر.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "gender", "age_group", "aggregation_level", "geography_basis"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "ParentProfile", "EnrollmentApplication"],
            },
            "enrollment_participation_0_60": {
                "title_ar": "مشاركة والتحاق الأطفال (0-60 شهراً)",
                "title_en": "Enrollment participation 0-60 months",
                "description_ar": "أعداد الأطفال (0–60 شهراً) ذوي التسجيل النشط، موزّعين حسب الموقع الجغرافي والفئة العمرية.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "gender", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "EnrollmentApplication"],
            },
            "institutions_active_licensed": {
                "title_ar": "مؤسسات الطفولة المبكرة النشطة والمرخصة",
                "title_en": "Active licensed institutions",
                "description_ar": "عدد مؤسسات الطفولة المبكرة حسب حالتها التشغيلية (نشطة/معلقة/مغلقة) والموقع الجغرافي.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "status", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Kindergarten"],
            },
            "capacity_occupancy_overcrowding": {
                "title_ar": "السعة الاستيعابية ومعدلات الإشغال والاكتظاظ",
                "title_en": "Capacity occupancy & overcrowding",
                "description_ar": "الطاقة الاستيعابية الصفّية مقابل عدد المسجّلين النشطين ونسبة الإشغال، مصنّفةً حسب الموقع.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Kindergarten", "Class"],
            },
            "monthly_attendance_absence": {
                "title_ar": "معدلات الحضور والغياب الشهرية",
                "title_en": "Monthly attendance & absence",
                "description_ar": "توزيع سجلات الحضور حسب الحالة (حاضر/غائب/متأخر/بعذر) والموقع الجغرافي خلال الفترة المحددة.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["period", "governorate", "city", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["AttendanceLog", "AbsenceRequest"],
            },
            "supervisors_child_ratio": {
                "title_ar": "معدل الأطفال لكل مشرفة",
                "title_en": "Supervisors child ratio",
                "description_ar": "عدد المشرفات مقابل الأطفال المسجّلين ومعدّل الأطفال لكل مشرفة، موزّعاً حسب الموقع.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Class", "SupervisorAssignment", "EnrollmentApplication"],
            },
            "incidents_safety_1000_child_days": {
                "title_ar": "معدل حوادث السلامة لكل 1000 يوم طفل",
                "title_en": "Incidents safety 1000 child days",
                "description_ar": "حوادث السلامة المسجّلة حسب درجة الخطورة والموقع، مع معدّل الحوادث لكل 1000 يوم حضور طفل.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["period", "governorate", "city", "severity", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Incident", "Kindergarten"],
            },
            "geographic_service_gaps": {
                "title_ar": "فجوات الخدمة الجغرافية والتوزيع المكاني",
                "title_en": "Geographic service gaps",
                "description_ar": "توزيع الأطفال مقابل الحضانات النشطة ومعدّل الأطفال لكل حضانة، لإبراز الفجوات الجغرافية في خدمات الطفولة.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "parent_residence",
                "filters": ["governorate", "city", "aggregation_level", "geography_basis"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "Kindergarten", "ParentProfile"],
            },
            "data_quality_completeness": {
                "title_ar": "مؤشر جودة واكتمال البيانات",
                "title_en": "Data quality completeness",
                "description_ar": "نسبة اكتمال البيانات: عدد الأطفال بدون تاريخ ميلاد أو جنس مسجّل، موزّعين حسب الموقع الجغرافي.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "kindergarten_location",
                "filters": ["governorate", "city", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Child", "Kindergarten"],
            },
            "annual_quarterly_trends": {
                "title_ar": "الاتجاهات السنوية والربعية للمؤشرات الرئيسية",
                "title_en": "Annual quarterly trends",
                "description_ar": "عدد الحضانات النشطة والأطفال المسجّلين موزّعين حسب سنة الإنشاء، لإبراز الاتجاه الزمني للقطاع.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "default_geography_basis": "national",
                "filters": ["period", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Kindergarten", "Child", "EnrollmentApplication"],
            },
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
                "description_ar": "الملف الديموغرافي للأطفال المسجّلين وأسرهم: التوزيع حسب الجنس والعمر والمحافظة وحالة التسجيل.",
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
                "description_ar": "عدد الرسائل والمحادثات بين الحضانة والأسرة، موزّعةً حسب نوع المحادثة والفترة الزمنية.",
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
                "description_ar": "عدد المدراء والمشرفات العاملين في الحضانات حسب الدور والموقع الجغرافي.",
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
                "description_ar": "نسبة إكمال التدريب: سجلات التدريب المكتملة مقابل الإجمالي لكل حضانة وفترة زمنية.",
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
                "description_ar": "الحضانات المسجّلة وفق حالتها التشغيلية والموقع الجغرافي، لدعم الرقابة والترخيص.",
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
                "description_ar": "حوادث السلامة وحماية الطفل المسجّلة حسب درجة الخطورة والموقع، لدعم متطلبات التقارير الرقابية.",
                "status": "ready",
                "privacy_level": "aggregated_only",
                "filters": ["period", "governorate", "city", "severity", "aggregation_level"],
                "exports": ["csv", "json"],
                "data_sources": ["Incident", "Kindergarten"],
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
                "description_ar": "مقارنة بين توزيع الأطفال وتوافر الحضانات، لتحديد المناطق ذات الطلب العالي وشُحّ الخدمة.",
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


def custom_report_schema() -> dict[str, Any]:
    """Declarative schema consumed by the frontend and the validator."""
    agencies = []
    for a in CUSTOM_REPORT_AGENCIES:
        entry = dict(a)
        reg = AGENCY_REPORT_REGISTRY.get(a["code"], {})
        entry["description_ar"] = reg.get("description_ar", "")
        agencies.append(entry)
    return {
        "agencies": agencies,
        "levels": CUSTOM_REPORT_LEVELS,
        "periods": CUSTOM_REPORT_PERIODS,
        "domains": CUSTOM_REPORT_DOMAINS,
    }



