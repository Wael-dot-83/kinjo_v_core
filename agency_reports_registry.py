"""Registry for Admin official-agency reports.

The registry is intentionally declarative: UI cards, available filters, export
availability, privacy rules, and unsupported-data states are generated from it.
"""
from __future__ import annotations

from typing import Any

AGENCY_REPORT_REGISTRY: dict[str, dict[str, Any]] = {
    "moe": {
        "name_ar": "وزارة التربية",
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
