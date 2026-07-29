"""
KPI and Governance Reporting Services
Implements all KPIs from Section 5 of the SRS
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from bisect import bisect_left, bisect_right
from math import ceil
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, literal_column, Integer
from pydantic import BaseModel

import models
from database import get_db
from dependencies import get_current_user, require_admin, require_admin_or_manager
import validators
from translations import setup_translator
from child_age_policy import get_child_age_bounds
from cache_service import dashboard_cache
from config import settings
from kpi_standards import (
    STANDARDS,
    HARD_OVERRIDE_RULES,
    BandColor,
    ConfidenceLevel,
    ThresholdDirection,
    compute_confidence,
    assign_band,
    get_band_label,
    get_band_meaning,
    get_band_action,
    get_threshold_source_dict,
    list_all_standards,
    list_hard_override_rules,
    MIN_COVERAGE_FOR_RATING,
)

# Set up translator for Arabic/English support
_ = setup_translator("ar")  # Default to Arabic, can be made configurable

# Import new models/enums
from models import TrainingStatus, TrainingModule, StaffTrainingCompletion, KPITarget

router = APIRouter()

_JORDAN_TZ = timezone(timedelta(hours=3))


def _today_jordan() -> date:
    """Current date in Jordan UTC+3. Use everywhere instead of date.today()."""
    return datetime.now(_JORDAN_TZ).date()


KPI_SUPPORTED_DIMENSION_TYPES: Tuple[str, ...] = (
    models.AnalyticsDimensionType.NETWORK.value,
    models.AnalyticsDimensionType.GOVERNORATE.value,
    models.AnalyticsDimensionType.DISTRICT.value,
    models.AnalyticsDimensionType.AREA.value,
    models.AnalyticsDimensionType.KINDERGARTEN.value,
)


# --- Enhanced Pydantic Models for KPI Dashboard ---
class TrendDataPoint(BaseModel):
    date: date
    value: float

class KPIThreshold(BaseModel):
    green_min: Optional[float] = None
    amber_min: Optional[float] = None
    amber_max: Optional[float] = None
    red_max: Optional[float] = None
    lower_is_better: bool = False

class KPIExplanation(BaseModel):
    ar: str
    en: str

class KPIManagerNote(BaseModel):
    ar: str
    en: str

class KPIActionItem(BaseModel):
    action: str
    priority: str
    ar: str
    en: str

class KPICardData(BaseModel):
    value: float
    unit: Optional[str] = None
    trend_indicator: Optional[str] = None  # "up", "down", "flat"
    trend_change: Optional[float] = None  # percentage change vs prev period
    previous_value: Optional[float] = None  # value from previous period
    band: Optional[str] = None  # "green", "amber", "red", "gray", "insufficient_data"
    threshold: Optional[KPIThreshold] = None
    explanation: Optional[KPIExplanation] = None
    manager_note: Optional[KPIManagerNote] = None
    action_items: Optional[List[KPIActionItem]] = None
    alert: Optional[str] = None  # "anomaly", "threshold_breached"
    tooltip: Optional[str] = None
    has_data: bool = True
    data_coverage: Optional[float] = None
    no_data_reason: Optional[str] = None
    # --- enriched fields for decision-grade transparency ---
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    formula: Optional[str] = None
    confidence: Optional[str] = None          # "high", "medium", "low", "insufficient"
    min_denominator_met: Optional[bool] = None
    threshold_source: Optional[dict] = None   # source metadata from kpi_standards
    meaning_ar: Optional[str] = None
    meaning_en: Optional[str] = None
    decision_guidance_ar: Optional[str] = None
    decision_guidance_en: Optional[str] = None

class StudentDistributionItem(BaseModel):
    label: str
    value: int

class TopBottomPerformer(BaseModel):
    id: int
    name: str
    value: float
    rank: Optional[int] = None
    governorate: Optional[str] = None

class AlertsSummary(BaseModel):
    type: str
    message: str
    priority: str
    entity_id: Optional[int] = None

class KPISummaryResponse(BaseModel):
    period_start: date
    period_end: date
    attendance_rate: Optional[float] = None
    incident_rate: Optional[float] = None
    serious_incident_rate: Optional[float] = None
    ratio_compliance: Optional[float] = None
    gqi_score: Optional[float] = None

class KPIDashboardResponse(BaseModel):
    period_start: date
    period_end: date
    kindergarten_id: Optional[int] = None # if filtered for single KG
    governorate: Optional[str] = None # if filtered for single Governorate
    district: Optional[str] = None
    area: Optional[str] = None
    dimension_type: Optional[str] = None
    dimension_id: Optional[str] = None

    overall_gcei: KPICardData
    attendance_rate: KPICardData
    ratio_compliance: KPICardData
    training_completion_rate: KPICardData
    report_submission_rate: KPICardData

    incident_rate: KPICardData
    serious_incident_rate: KPICardData
    incident_followup_sla: KPICardData
    chronic_absence_rate: KPICardData

    capacity_utilization_rate: KPICardData
    active_enrollments: KPICardData
    new_enrollments: KPICardData

    student_distribution: List[StudentDistributionItem]
    top_performers_by_gcei: List[TopBottomPerformer]
    low_performers_by_gcei: List[TopBottomPerformer]
    
    attendance_trend: List[TrendDataPoint] 
    incidents_trend: List[TrendDataPoint]
    enrollment_trend: List[TrendDataPoint]
    gcei_trend: List[TrendDataPoint]

    alerts: List[AlertsSummary]


# --- KPI Definitions and Explanations ---
KPI_DEFINITIONS = {
    "overall_gcei": {
        "name_ar": "مؤشر الحوكمة وتجربة الطفل",
        "name_en": "Governance & Child Experience Index",
        "description_ar": "درجة شاملة تقيس جودة أداء الحضانة (0-100)",
        "description_en": "Comprehensive score measuring kindergarten performance quality (0-100)",
        "formula_ar": "60% إدارة وحوكمة + 40% تجربة الطفل",
        "formula_en": "60% Governance + 40% Child Experience",
        "threshold": KPIThreshold(green_min=80, amber_min=60, amber_max=79.99),
        "explanation": KPIExplanation(
            ar="""مؤشر شامل يقيم أداء الحضانة من خلال دمج عاملين رئيسيين:
• الحوكمة والإدارة (60%): تشمل الامتثال للمعايير، جودة التقارير، والإجراءات الإدارية
• تجربة الطفل (40%): تركز على رضا الأطفال، جودة الأنشطة التعليمية، والرعاية اليومية
الدرجة الأعلى تشير إلى حضانة متميزة في جميع الجوانب.""",
            en="""A comprehensive index evaluating kindergarten performance through two main factors:
• Governance & Management (60%): Includes compliance with standards, report quality, and administrative procedures
• Child Experience (40%): Focuses on child satisfaction, educational activity quality, and daily care
Higher scores indicate an excellent kindergarten across all aspects."""
        ),
        "manager_note": KPIManagerNote(
            ar="""🎉 أداء متميز! روضتك تحقق معايير التميز في الإدارة والرعاية.
📈 استمر في تطوير البرامج التعليمية وتعزيز التواصل مع أولياء الأمور.
🎯 الهدف: الحفاظ على مستوى 80+ لضمان تجربة تعليمية متميزة.""",
            en="""🎉 Excellent performance! Your kindergarten meets excellence standards in management and care.
📈 Continue developing educational programs and strengthening parent communication.
🎯 Goal: Maintain 80+ level to ensure outstanding educational experience."""
        ),
        "action_items": [
            KPIActionItem(
                action="comprehensive_audit",
                priority="HIGH",
                ar="إجراء تدقيق شامل لجميع العمليات الإدارية والتعليمية",
                en="Conduct comprehensive audit of all administrative and educational operations"
            ),
            KPIActionItem(
                action="parent_feedback_system",
                priority="HIGH",
                ar="تطوير نظام لجمع وتحليل ملاحظات أولياء الأمور",
                en="Develop system to collect and analyze parent feedback"
            ),
            KPIActionItem(
                action="staff_development_plan",
                priority="MEDIUM",
                ar="إعداد خطة تطوير مهني لجميع الموظفين",
                en="Create professional development plan for all staff"
            ),
            KPIActionItem(
                action="quality_standards_review",
                priority="MEDIUM",
                ar="مراجعة وتحديث معايير الجودة المعتمدة",
                en="Review and update adopted quality standards"
            )
        ]
    },
    "attendance_rate": {
        "name_ar": "نسبة الحضور",
        "name_en": "Attendance Rate",
        "description_ar": "نسبة الأطفال الذين يحضرون يومياً",
        "description_en": "Percentage of children attending daily",
        "formula_ar": "(أيام الحضور الفعلية ÷ أيام الحضور المتوقعة) × 100",
        "formula_en": "(Actual Attendance Days ÷ Expected Attendance Days) × 100",
        "threshold": KPIThreshold(green_min=90, amber_min=70, amber_max=89.99),
        "explanation": KPIExplanation(
            ar="""يُظهر هذا المؤشر مدى التزام الأطفال بالحضور المنتظم في الحضانة:
• يُحسب بناءً على أيام الحضور الفعلية مقارنة بالأيام المتوقعة
• يعكس جاذبية البرامج التعليمية وجودة الرعاية
• يؤثر على التعلم والتطور الاجتماعي للأطفال
• يساعد في تحديد الأطفال الذين يحتاجون لمتابعة خاصة
الهدف: 90% كحد أدنى لضمان استفادة الأطفال الكاملة من البرامج.""",
            en="""This indicator shows children's commitment to regular kindergarten attendance:
• Calculated based on actual attendance days compared to expected days
• Reflects attractiveness of educational programs and care quality
• Affects children's learning and social development
• Helps identify children needing special follow-up
Goal: 90% minimum to ensure children fully benefit from programs."""
        ),
        "manager_note": KPIManagerNote(
            ar="""🎯 حضور ممتاز! هذا يعني أن برامجكم التعليمية جذابة ومفيدة.
📞 راقب الحالات الخاصة وتواصل مع أولياء الأمور المعنيين.
📊 الهدف: الحفاظ على 90%+ لتحقيق أقصى استفادة تعليمية.
💡 نصيحة: ركز على الأنشطة المتنوعة والتواصل اليومي مع الأهل.""",
            en="""🎯 Excellent attendance! This means your educational programs are attractive and beneficial.
📞 Monitor special cases and communicate with concerned parents.
📊 Goal: Maintain 90%+ for maximum educational benefit.
💡 Tip: Focus on diverse activities and daily parent communication."""
        ),
        "action_items": [
            KPIActionItem(
                action="parent_communication_campaign",
                priority="HIGH",
                ar="إطلاق حملة تواصل مع أولياء الأمور لشرح أهمية الحضور المنتظم",
                en="Launch parent communication campaign explaining importance of regular attendance"
            ),
            KPIActionItem(
                action="attendance_tracking_system",
                priority="HIGH",
                ar="تطوير نظام تتبع دقيق للحضور مع إشعارات تلقائية",
                en="Develop accurate attendance tracking system with automatic notifications"
            ),
            KPIActionItem(
                action="program_enhancement",
                priority="MEDIUM",
                ar="تحسين البرامج التعليمية والأنشطة اليومية لزيادة الجاذبية",
                en="Enhance educational programs and daily activities to increase attractiveness"
            ),
            KPIActionItem(
                action="flexible_scheduling",
                priority="MEDIUM",
                ar="دراسة إمكانية جدولة مرنة للأطفال ذوي الاحتياجات الخاصة",
                en="Study possibility of flexible scheduling for children with special needs"
            ),
            KPIActionItem(
                action="success_stories",
                priority="LOW",
                ar="مشاركة قصص نجاح الأطفال المنتظمين مع أولياء الأمور",
                en="Share success stories of regular children with parents"
            )
        ]
    },
    "ratio_compliance": {
        "name_ar": "نسبة الالتزام بالنسب",
        "name_en": "Staff-Child Ratio Compliance",
        "description_ar": "نسبة الوقت الذي يتم فيه الالتزام بنسبة المعلم للأطفال",
        "description_en": "Percentage of time complying with staff-child ratios",
        "formula_ar": "(الوقت المطابق للنسب ÷ إجمالي الوقت) × 100",
        "formula_en": "(Time compliant with ratios ÷ Total time) × 100",
        "threshold": KPIThreshold(green_min=95, amber_min=80, amber_max=94.99),
        "explanation": KPIExplanation(
            ar="""يضمن هذا المؤشر سلامة الأطفال وجودة الرعاية من خلال مراقبة النسب المعتمدة:
• يراقب الامتثال للنسب القانونية للمعلمين والأطفال
• يؤثر مباشرة على جودة الرعاية والاهتمام الفردي
• يساعد في منع الحوادث وتحسين التعلم
• يختلف حسب الفئة العمرية للأطفال
الهدف: 95% كحد أدنى لضمان رعاية آمنة وفعالة.""",
            en="""This indicator ensures child safety and care quality by monitoring approved ratios:
• Monitors compliance with legal teacher-child ratios
• Directly affects care quality and individual attention
• Helps prevent accidents and improve learning
• Varies according to children's age groups
Goal: 95% minimum for safe and effective care."""
        ),
        "manager_note": KPIManagerNote(
            ar="""🛡️ امتثال ممتاز للنسب! هذا يضمن سلامة الأطفال وجودة الرعاية.
👥 راقب التوزيع اليومي للموظفين وتأكد من التغطية في جميع الأوقات.
📋 الهدف: الحفاظ على 95%+ لتلبية المعايير الدولية.
⚡ نصيحة: استخدم جدولة ذكية لتوزيع الموظفين حسب الحاجة.""",
            en="""🛡️ Excellent ratio compliance! This ensures child safety and care quality.
👥 Monitor daily staff distribution and ensure coverage at all times.
📋 Goal: Maintain 95%+ to meet international standards.
⚡ Tip: Use smart scheduling to distribute staff according to needs."""
        ),
        "action_items": [
            KPIActionItem(
                action="staff_scheduling_optimization",
                priority="CRITICAL",
                ar="تحسين جدولة الموظفين لضمان تغطية كاملة في جميع الأوقات",
                en="Optimize staff scheduling to ensure full coverage at all times"
            ),
            KPIActionItem(
                action="ratio_monitoring_system",
                priority="HIGH",
                ar="تطوير نظام مراقبة فوري للنسب مع إشعارات تلقائية",
                en="Develop real-time ratio monitoring system with automatic alerts"
            ),
            KPIActionItem(
                action="backup_staff_plan",
                priority="HIGH",
                ar="إعداد خطة طوارئ للموظفين الاحتياطيين في حالات الغياب",
                en="Create emergency backup staff plan for absence situations"
            ),
            KPIActionItem(
                action="age_group_optimization",
                priority="MEDIUM",
                ar="تخصيص الموظفين حسب الفئات العمرية والاحتياجات الخاصة",
                en="Assign staff according to age groups and special needs"
            ),
            KPIActionItem(
                action="training_ratio_awareness",
                priority="MEDIUM",
                ar="تدريب الموظفين على أهمية النسب وتأثيرها على السلامة",
                en="Train staff on ratio importance and safety impact"
            ),
            KPIActionItem(
                action="parent_ratio_communication",
                priority="LOW",
                ar="إبلاغ أولياء الأمور بالنسب المعتمدة وفوائدها",
                en="Inform parents about approved ratios and their benefits"
            )
        ]
    },
    "incident_rate": {
        "name_ar": "معدل الحوادث",
        "name_en": "Incident Rate",
        "description_ar": "عدد الحوادث لكل 1,000 طفل-يوم",
        "description_en": "Number of incidents per 1,000 attended child-days",
        "formula_ar": "(عدد الحوادث ÷ أيام حضور الأطفال) × 1,000",
        "formula_en": "(Number of incidents ÷ attended child-days) × 1,000",
        "threshold": KPIThreshold(green_min=0, amber_min=2.01, amber_max=5.0, red_max=5.0, lower_is_better=True),
        "explanation": KPIExplanation(
            ar="""يُقيم هذا المؤشر مستوى السلامة في الحضانة من خلال تتبع الحوادث:
• يشمل جميع الحوادث: صغيرة (كدمات، سقوط بسيط) وكبيرة
• يُحسب لكل 1,000 يوم-طفل للمقارنة العادلة
• يعكس فعالية إجراءات السلامة والوقاية
• يساعد في تحديد المخاطر ومنع تكرارها
الهدف: اقتراب من الصفر لضمان بيئة آمنة تماماً.""",
            en="""This indicator evaluates kindergarten safety level by tracking incidents:
• Includes all incidents: minor (bruises, small falls) and major
• Calculated per 1,000 attended child-days for fair comparison
• Reflects effectiveness of safety procedures and prevention
• Helps identify risks and prevent recurrence
Goal: Approach zero for a completely safe environment."""
        ),
        "manager_note": KPIManagerNote(
            ar="""✅ بيئة آمنة جداً! هذا يعني أن إجراءات السلامة فعالة.
🔍 راقب الحوادث اليومية وتعلم من كل واقعة للتحسين المستمر.
🎯 الهدف: الحفاظ على معدلات منخفضة (أقل من 2.0 لكل 1,000 يوم-طفل).
🛡️ نصيحة: ركز على الوقاية والتدريب المستمر للموظفين.""",
            en="""✅ Very safe environment! This means safety procedures are effective.
🔍 Monitor daily incidents and learn from each case for continuous improvement.
🎯 Goal: Maintain low rates (below 2.0 per 1,000 attended child-days).
🛡️ Tip: Focus on prevention and continuous staff training."""
        ),
        "action_items": [
            KPIActionItem(
                action="safety_audit_comprehensive",
                priority="CRITICAL",
                ar="إجراء تدقيق شامل للسلامة في جميع مرافق الحضانة",
                en="Conduct comprehensive safety audit of all kindergarten facilities"
            ),
            KPIActionItem(
                action="incident_reporting_system",
                priority="HIGH",
                ar="تطوير نظام إبلاغ فوري عن الحوادث مع تحليل الجذور",
                en="Develop immediate incident reporting system with root cause analysis"
            ),
            KPIActionItem(
                action="staff_safety_training",
                priority="HIGH",
                ar="تدريب شهري للموظفين على إجراءات السلامة والوقاية",
                en="Monthly staff training on safety procedures and prevention"
            ),
            KPIActionItem(
                action="emergency_response_drill",
                priority="HIGH",
                ar="إجراء تدريبات طوارئ ربع سنوية لجميع السيناريوهات",
                en="Conduct quarterly emergency drills for all scenarios"
            ),
            KPIActionItem(
                action="equipment_safety_check",
                priority="MEDIUM",
                ar="فحص أسبوعي للمعدات والألعاب وإصلاح أي تلف",
                en="Weekly inspection of equipment and toys with repair of any damage"
            ),
            KPIActionItem(
                action="parent_safety_communication",
                priority="MEDIUM",
                ar="إبلاغ أولياء الأمور بإجراءات السلامة والحوادث المهمة",
                en="Inform parents about safety procedures and important incidents"
            ),
            KPIActionItem(
                action="risk_assessment_update",
                priority="LOW",
                ar="تحديث تقييم المخاطر كل 6 أشهر وتحديث الإجراءات",
                en="Update risk assessment every 6 months and update procedures"
            )
        ]
    },
    "serious_incident_rate": {
        "name_ar": "الحوادث الخطرة",
        "name_en": "Serious Incident Rate",
        "description_ar": "الحوادث التي تتطلب تدخلاً طبياً لكل 1,000 طفل-يوم",
        "description_en": "Incidents requiring medical intervention per 1,000 attended child-days",
        "formula_ar": "(الحوادث الخطرة ÷ أيام حضور الأطفال) × 1,000",
        "formula_en": "(Serious incidents ÷ attended child-days) × 1,000",
        "threshold": KPIThreshold(green_min=0, amber_min=0.001, amber_max=0.5, red_max=0.5, lower_is_better=True),
        "explanation": KPIExplanation(
            ar="""يُراقب هذا المؤشر الحوادث الخطيرة التي تهدد صحة الأطفال:
• تشمل الحوادث التي تتطلب تدخلاً طبياً أو إسعافاً
• قد تتطلب إبلاغ الجهات الرسمية والأهل فوراً
• تُحقق فيها لتحديد المسؤوليات ومنع التكرار
• تؤثر على سمعة الحضانة وثقة أولياء الأمور
الهدف: الصفر المطلق لضمان أقصى درجات السلامة.""",
            en="""This indicator monitors serious incidents threatening children's health:
• Includes incidents requiring medical intervention or ambulance
• May require immediate notification of authorities and parents
• Investigated to determine responsibilities and prevent recurrence
• Affects kindergarten reputation and parent trust
Goal: Absolute zero for maximum safety levels."""
        ),
        "manager_note": KPIManagerNote(
            ar="""🛑 مستوى سلامة ممتاز! هذا يعني بيئة آمنة للأطفال.
⚠️ راقب أي حوادث خطيرة عن كثب واتخذ إجراءات فورية.
🚨 الهدف: الصفر - لا حوادث خطيرة على الإطلاق.
📞 نصيحة: كن مستعداً دائماً للطوارئ وتواصل مع الأهل فوراً.""",
            en="""🛑 Excellent safety level! This means a safe environment for children.
⚠️ Monitor any serious incidents closely and take immediate action.
🚨 Goal: Zero - no serious incidents whatsoever.
📞 Tip: Always be prepared for emergencies and communicate with parents immediately."""
        ),
        "action_items": [
            KPIActionItem(
                action="emergency_response_plan",
                priority="CRITICAL",
                ar="تطوير خطة استجابة طوارئ شاملة مع تدريبات منتظمة",
                en="Develop comprehensive emergency response plan with regular drills"
            ),
            KPIActionItem(
                action="medical_emergency_protocol",
                priority="CRITICAL",
                ar="إعداد بروتوكول طبي طوارئ مع اتفاقيات مع المستشفيات القريبة",
                en="Establish medical emergency protocol with agreements with nearby hospitals"
            ),
            KPIActionItem(
                action="first_aid_certification",
                priority="HIGH",
                ar="تدريب واعتماد جميع الموظفين على الإسعافات الأولية",
                en="Train and certify all staff in first aid procedures"
            ),
            KPIActionItem(
                action="parent_emergency_contacts",
                priority="HIGH",
                ar="تحديث قاعدة بيانات جهات الاتصال الطارئة لأولياء الأمور",
                en="Update database of emergency contact information for parents"
            ),
            KPIActionItem(
                action="incident_investigation_process",
                priority="HIGH",
                ar="تطوير عملية تحقيق منهجية في الحوادث الخطيرة",
                en="Develop systematic investigation process for serious incidents"
            ),
            KPIActionItem(
                action="safety_equipment_upgrade",
                priority="MEDIUM",
                ar="ترقية معدات السلامة والإسعافات الأولية",
                en="Upgrade safety equipment and first aid supplies"
            ),
            KPIActionItem(
                action="authority_reporting_system",
                priority="MEDIUM",
                ar="إعداد نظام إبلاغ فوري للجهات الرسمية عند الحاجة",
                en="Establish immediate reporting system to authorities when needed"
            )
        ]
    },
    "incident_followup_sla": {
        "name_ar": "متابعة الحوادث",
        "name_en": "Incident Follow-up SLA",
        "description_ar": "نسبة الحوادث المغلقة خلال 48 ساعة",
        "description_en": "Percentage of incidents closed within 48 hours",
        "formula_ar": "(الحوادث المغلقة خلال 48 ساعة ÷ إجمالي الحوادث) × 100",
        "formula_en": "(Incidents closed within 48 hours ÷ Total incidents) × 100",
        "threshold": KPIThreshold(green_min=100, amber_min=90, amber_max=99.99),
        "explanation": KPIExplanation(
            ar="""يُقيم هذا المؤشر سرعة وفعالية التعامل مع الحوادث:
• يجب إغلاق ملف كل حادثة خلال 48 ساعة من وقوعها
• يشمل التحقيق، الإجراءات التصحيحية، والإبلاغ للأهل
• يعكس كفاءة الإجراءات الإدارية والتواصل
• يساعد في بناء الثقة مع أولياء الأمور
الهدف: 100% لضمان متابعة فورية وفعالة.""",
            en="""This indicator evaluates speed and effectiveness of incident handling:
• Each incident file must be closed within 48 hours of occurrence
• Includes investigation, corrective actions, and parent notification
• Reflects administrative procedures efficiency and communication
• Helps build trust with parents
Goal: 100% for immediate and effective follow-up."""
        ),
        "manager_note": KPIManagerNote(
            ar="""⚡ متابعة ممتازة! هذا يعني تعامل سريع وفعال مع الحوادث.
📋 راقب الحالات المعلقة وتأكد من إغلاقها في الوقت المحدد.
🎯 الهدف: 100% - لا تتجاوز 48 ساعة لأي حادثة.
📝 نصيحة: حدد مسؤوليات واضحة واستخدم قوالب جاهزة للمتابعة.""",
            en="""⚡ Excellent follow-up! This means quick and effective incident handling.
📋 Monitor pending cases and ensure they are closed on time.
🎯 Goal: 100% - no incident exceeds 48 hours.
📝 Tip: Define clear responsibilities and use ready-made templates for follow-up."""
        ),
        "action_items": [
            KPIActionItem(
                action="followup_process_standardization",
                priority="HIGH",
                ar="توحيد عملية متابعة الحوادث مع خطوات واضحة ومواعيد نهائية",
                en="Standardize incident follow-up process with clear steps and deadlines"
            ),
            KPIActionItem(
                action="incident_tracking_system",
                priority="HIGH",
                ar="تطوير نظام تتبع إلكتروني للحوادث مع تذكيرات تلقائية",
                en="Develop electronic incident tracking system with automatic reminders"
            ),
            KPIActionItem(
                action="staff_responsibility_assignment",
                priority="MEDIUM",
                ar="تحديد مسؤوليات واضحة لكل موظف في عملية متابعة الحوادث",
                en="Define clear responsibilities for each staff member in incident follow-up"
            ),
            KPIActionItem(
                action="parent_communication_templates",
                priority="MEDIUM",
                ar="إعداد قوالب جاهزة للتواصل مع أولياء الأمور حول الحوادث",
                en="Prepare ready-made templates for communicating with parents about incidents"
            ),
            KPIActionItem(
                action="followup_training_program",
                priority="MEDIUM",
                ar="تدريب الموظفين على إجراءات المتابعة والإبلاغ الفعال",
                en="Train staff on follow-up procedures and effective reporting"
            ),
            KPIActionItem(
                action="sla_monitoring_dashboard",
                priority="LOW",
                ar="إنشاء لوحة تحكم لمراقبة مؤشرات الأداء في الوقت الفعلي",
                en="Create dashboard for real-time SLA performance monitoring"
            )
        ]
    },
    "chronic_absence_rate": {
        "name_ar": "الغياب المزمن",
        "name_en": "Chronic Absence Rate",
        "description_ar": "نسبة الأطفال الذين يتغيبون أكثر من 10% من أيام العمل",
        "description_en": "Percentage of children absent more than 10% of school days",
        "formula_ar": "(الأطفال المزمني الغياب ÷ إجمالي الأطفال) × 100",
        "formula_en": "(Chronically absent children ÷ Total children) × 100",
        "threshold": KPIThreshold(green_min=5, amber_min=5.01, amber_max=10, red_max=10, lower_is_better=True),
        "explanation": KPIExplanation(
            ar="""يُحدد هذا المؤشر الأطفال الذين يعانون من غياب متكرر:
• يُعتبر الغياب مزمناً عند تجاوز 10% من أيام الدراسة
• قد يكون بسبب مشاكل صحية، اجتماعية، أو تعليمية
• يؤثر سلباً على التعلم والتطور الاجتماعي
• يتطلب متابعة خاصة ودعم من الأهل والحضانة
الهدف: أقل من 5% لضمان انتظام تعليمي جيد.""",
            en="""This indicator identifies children with recurrent absences:
• Absence is considered chronic when exceeding 10% of school days
• May be due to health, social, or educational problems
• Negatively affects learning and social development
• Requires special follow-up and support from parents and kindergarten
Goal: Less than 5% for good educational regularity."""
        ),
        "manager_note": KPIManagerNote(
            ar="""📊 غياب منخفض جداً! هذا يعني انتظام تعليمي ممتاز.
👨‍👩‍👧‍👦 راقب الحالات الفردية وتعاون مع الأهل لحل المشاكل.
🎯 الهدف: أقل من 5% لضمان نمو الأطفال المتوازن.
💡 نصيحة: تواصل مستمر مع الأهل وتقديم دعم إضافي عند الحاجة.""",
            en="""📊 Very low absence! This means excellent educational regularity.
👨‍👩‍👧‍👦 Monitor individual cases and collaborate with parents to solve problems.
🎯 Goal: Less than 5% to ensure balanced child development.
💡 Tip: Continuous communication with parents and provide additional support when needed."""
        ),
        "action_items": [
            KPIActionItem(
                action="individual_absence_tracking",
                priority="HIGH",
                ar="تطوير نظام تتبع فردي للغياب مع إشعارات مبكرة للأهل",
                en="Develop individual absence tracking system with early notifications to parents"
            ),
            KPIActionItem(
                action="parent_support_program",
                priority="HIGH",
                ar="إنشاء برنامج دعم لأولياء الأمور لمساعدة أطفالهم على الانتظام",
                en="Create parent support program to help their children maintain regularity"
            ),
            KPIActionItem(
                action="health_screening_program",
                priority="MEDIUM",
                ar="تنفيذ فحوصات صحية دورية للكشف المبكر عن المشاكل الصحية",
                en="Implement periodic health screenings for early detection of health problems"
            ),
            KPIActionItem(
                action="flexible_attendance_policy",
                priority="MEDIUM",
                ar="تطوير سياسة حضور مرنة للأطفال ذوي الاحتياجات الخاصة",
                en="Develop flexible attendance policy for children with special needs"
            ),
            KPIActionItem(
                action="motivational_programs",
                priority="MEDIUM",
                ar="إطلاق برامج تحفيزية للأطفال المنتظمين وحضورهم",
                en="Launch motivational programs for regular children and their attendance"
            ),
            KPIActionItem(
                action="counseling_services",
                priority="LOW",
                ar="توفير خدمات استشارية للأطفال والأهل في حالات الغياب المزمن",
                en="Provide counseling services for children and parents in chronic absence cases"
            )
        ]
    },
    "capacity_utilization_rate": {
        "name_ar": "نسبة استغلال الطاقة",
        "name_en": "Capacity Utilization Rate",
        "description_ar": "نسبة استغلال الطاقة الاستيعابية",
        "description_en": "Percentage utilization of capacity",
        "formula_ar": "(الأطفال المسجلين ÷ الطاقة الاستيعابية) × 100",
        "formula_en": "(Enrolled children ÷ Capacity) × 100",
        "threshold": KPIThreshold(green_min=90, amber_min=80, amber_max=100, red_max=100),
        "explanation": KPIExplanation(
            ar="""يُظهر هذا المؤشر كفاءة استخدام مرافق الحضانة:
• يقارن عدد الأطفال المسجلين بالطاقة الاستيعابية القصوى
• يساعد في التخطيط للنمو والتوسع المستقبلي
• يؤثر على الإيرادات والاستدامة المالية
• يضمن توفير مساحة كافية لكل طفل
الهدف: 90% لتحقيق التوازن بين الاستغلال والراحة.""",
            en="""This indicator shows efficiency of kindergarten facility usage:
• Compares enrolled children number to maximum capacity
• Helps plan future growth and expansion
• Affects revenues and financial sustainability
• Ensures sufficient space for each child
Goal: 90% to balance utilization and comfort."""
        ),
        "manager_note": KPIManagerNote(
            ar="""📈 استغلال ممتاز للطاقة! هذا يعني كفاءة في استخدام المرافق.
🏫 راقب التوزيع الطبقي وتأكد من عدم الاكتظاظ.
🎯 الهدف: 90% لضمان راحة الأطفال وجودة التعليم.
💰 نصيحة: خطط للتوسع عند الاقتراب من الحد الأقصى.""",
            en="""📈 Excellent capacity utilization! This means efficient facility usage.
🏫 Monitor classroom distribution and ensure no overcrowding.
🎯 Goal: 90% to ensure child comfort and education quality.
💰 Tip: Plan expansion when approaching maximum capacity."""
        ),
        "action_items": [
            KPIActionItem(
                action="capacity_assessment_study",
                priority="HIGH",
                ar="إجراء دراسة شاملة لتقييم الطاقة الاستيعابية الحالية والمستقبلية",
                en="Conduct comprehensive study to assess current and future capacity"
            ),
            KPIActionItem(
                action="enrollment_forecasting",
                priority="MEDIUM",
                ar="تطوير نظام توقع التسجيلات بناءً على الاتجاهات والاحتياجات المحلية",
                en="Develop enrollment forecasting system based on trends and local needs"
            ),
            KPIActionItem(
                action="facility_expansion_plan",
                priority="MEDIUM",
                ar="إعداد خطة توسع مرافق مع جدولة زمنية وميزانية محددة",
                en="Prepare facility expansion plan with specific timeline and budget"
            ),
            KPIActionItem(
                action="classroom_optimization",
                priority="MEDIUM",
                ar="تحسين توزيع الأطفال في الفصول لتحقيق التوازن الأمثل",
                en="Optimize children distribution in classrooms for optimal balance"
            ),
            KPIActionItem(
                action="waiting_list_management",
                priority="LOW",
                ar="إدارة قائمة الانتظار بكفاءة وإبلاغ الأهل بالتطورات",
                en="Manage waiting list efficiently and inform parents of developments"
            ),
            KPIActionItem(
                action="alternative_solutions",
                priority="LOW",
                ar="دراسة حلول بديلة مثل الفترات المتعددة أو البرامج المرنة",
                en="Study alternative solutions like multiple shifts or flexible programs"
            )
        ]
    },
    "training_completion_rate": {
        "name_ar": "اكتمال التدريب",
        "name_en": "Training Completion Rate",
        "description_ar": "نسبة الموظفين المكتملين للتدريب الإلزامي",
        "description_en": "Percentage of staff completing mandatory training",
        "formula_ar": "(الموظفين المكتملين للتدريب ÷ إجمالي الموظفين) × 100",
        "formula_en": "(Staff completed training ÷ Total staff) × 100",
        "threshold": KPIThreshold(green_min=90, amber_min=75, amber_max=89.99),
        "explanation": KPIExplanation(
            ar="""يُقيم هذا المؤشر التزام الموظفين بالتطوير المهني:
• يشمل التدريبات الإلزامية في السلامة، الرعاية، والتعليم
• يعكس مستوى الالتزام بالمعايير المهنية
• يؤثر على جودة الرعاية والتعليم المقدم
• يساعد في تطوير المهارات ومواكبة أفضل الممارسات
الهدف: 90% لضمان فريق عمل مؤهل ومحترف.""",
            en="""This indicator evaluates staff commitment to professional development:
• Includes mandatory training in safety, care, and education
• Reflects commitment level to professional standards
• Affects quality of care and education provided
• Helps develop skills and follow best practices
Goal: 90% to ensure qualified and professional team."""
        ),
        "manager_note": KPIManagerNote(
            ar="""🎓 تدريب ممتاز! هذا يعني فريق عمل مؤهل وملتزم.
📚 راقب التدريبات المطلوبة وتأكد من إكمالها في الوقت المحدد.
🎯 الهدف: 90%+ لضمان أعلى مستويات الجودة.
📖 نصيحة: اجعل التدريب جزءاً من ثقافة الحضانة وكافئ المتميزين.""",
            en="""🎓 Excellent training! This means a qualified and committed team.
📚 Monitor required trainings and ensure completion on time.
🎯 Goal: 90%+ to ensure highest quality levels.
📖 Tip: Make training part of kindergarten culture and reward excellence."""
        ),
        "action_items": [
            KPIActionItem(
                action="training_needs_assessment",
                priority="HIGH",
                ar="إجراء تقييم شامل لاحتياجات التدريب لجميع الموظفين",
                en="Conduct comprehensive training needs assessment for all staff"
            ),
            KPIActionItem(
                action="annual_training_plan",
                priority="HIGH",
                ar="إعداد خطة تدريب سنوية شاملة مع جدولة زمنية واضحة",
                en="Prepare comprehensive annual training plan with clear timeline"
            ),
            KPIActionItem(
                action="training_tracking_system",
                priority="MEDIUM",
                ar="تطوير نظام إلكتروني لتتبع إكمال التدريبات والشهادات",
                en="Develop electronic system to track training completion and certifications"
            ),
            KPIActionItem(
                action="incentive_program",
                priority="MEDIUM",
                ar="إنشاء برنامج حوافز للموظفين المتميزين في إكمال التدريبات",
                en="Create incentive program for staff excelling in training completion"
            ),
            KPIActionItem(
                action="flexible_training_options",
                priority="MEDIUM",
                ar="توفير خيارات تدريب مرنة (عبر الإنترنت، حضوري، مختلط)",
                en="Provide flexible training options (online, in-person, hybrid)"
            ),
            KPIActionItem(
                action="certification_renewal_tracking",
                priority="LOW",
                ar="تتبع تجديد الشهادات والتراخيص المطلوبة للموظفين",
                en="Track renewal of required certifications and licenses for staff"
            )
        ]
    },
    "report_submission_rate": {
        "name_ar": "إرسال التقارير",
        "name_en": "Report Submission Rate",
        "description_ar": "نسبة التقارير اليومية المرسلة",
        "description_en": "Percentage of daily reports submitted",
        "formula_ar": "(التقارير المرسلة ÷ التقارير المتوقعة) × 100",
        "formula_en": "(Reports submitted ÷ Reports expected) × 100",
        "threshold": KPIThreshold(green_min=95, amber_min=85, amber_max=94.99),
        "explanation": KPIExplanation(
            ar="""يُقيم هذا المؤشر انتظام التواصل مع أولياء الأمور:
• يشمل التقارير اليومية عن أنشطة وحالة الطفل
• يعكس مستوى الشفافية والتواصل مع الأهل
• يساعد في بناء الثقة ومتابعة تطور الطفل
• يوفر معلومات مهمة عن يوم الطفل في الحضانة
الهدف: 95% لضمان تواصل يومي منتظم مع الأهل.""",
            en="""This indicator evaluates regularity of communication with parents:
• Includes daily reports about child's activities and condition
• Reflects transparency level and communication with parents
• Helps build trust and monitor child development
• Provides important information about child's day at kindergarten
Goal: 95% to ensure regular daily communication with parents."""
        ),
        "manager_note": KPIManagerNote(
            ar="""📝 تقارير ممتازة! هذا يعني تواصل ممتاز مع أولياء الأمور.
📱 راقب التقارير اليومية وتأكد من دقتها وشموليتها.
🎯 الهدف: 95%+ لضمان رضا الأهل وثقتهم.
💬 نصيحة: اجعل التقارير مفيدة ومخصصة لكل طفل.""",
            en="""📝 Excellent reports! This means outstanding communication with parents.
📱 Monitor daily reports and ensure their accuracy and comprehensiveness.
🎯 Goal: 95%+ to ensure parent satisfaction and trust.
💬 Tip: Make reports useful and personalized for each child."""
        ),
        "action_items": [
            KPIActionItem(
                action="reporting_process_optimization",
                priority="HIGH",
                ar="تبسيط وتحسين عملية إعداد وإرسال التقارير اليومية",
                en="Streamline and improve daily report preparation and sending process"
            ),
            KPIActionItem(
                action="digital_reporting_system",
                priority="HIGH",
                ar="تطوير نظام إلكتروني للتقارير مع قوالب جاهزة وصور",
                en="Develop digital reporting system with ready templates and photos"
            ),
            KPIActionItem(
                action="staff_reporting_training",
                priority="MEDIUM",
                ar="تدريب الموظفين على كتابة تقارير مفيدة وجذابة",
                en="Train staff to write useful and engaging reports"
            ),
            KPIActionItem(
                action="parent_feedback_collection",
                priority="MEDIUM",
                ar="جمع ملاحظات أولياء الأمور حول التقارير وتحسينها",
                en="Collect parent feedback about reports and improve them"
            ),
            KPIActionItem(
                action="automated_reminders",
                priority="MEDIUM",
                ar="إعداد نظام تذكيرات تلقائية للموظفين بإرسال التقارير",
                en="Set up automated reminder system for staff to send reports"
            ),
            KPIActionItem(
                action="multimedia_reports",
                priority="LOW",
                ar="إضافة صور وفيديوهات للتقارير لجعلها أكثر جاذبية",
                en="Add photos and videos to reports to make them more engaging"
            )
        ]
    }
}


class AttendanceRateResponse(BaseModel):
    kindergarten_id: Optional[int] = None
    period_start: date
    period_end: date
    attendance_rate: Optional[float] = None


class GovernanceScoreResponse(BaseModel):
    kindergarten_id: Optional[int] = None
    period_start: date
    period_end: date
    governance_score: float
    governance_band: str


class EnhancedKPICard(BaseModel):
    """Enhanced KPI card with comprehensive data"""
    kpi_key: str
    name_ar: str
    name_en: str
    value: float
    unit: str = "%"
    status: str  # "green", "amber", "red"
    trend: str  # "up", "down", "stable"
    trend_value: float  # percentage change
    threshold: KPIThreshold
    explanation: KPIExplanation
    manager_note: KPIManagerNote
    action_items: List[KPIActionItem]
    last_updated: datetime
    period_days: int


class EnhancedKPIDashboardResponse(BaseModel):
    """Enhanced dashboard response with all KPI data"""
    kindergarten_id: Optional[int] = None
    kindergarten_name: Optional[str] = None
    period_start: date
    period_end: date
    overall_gcei: EnhancedKPICard
    attendance_rate: EnhancedKPICard
    excused_absence_rate: Optional[EnhancedKPICard] = None
    ratio_compliance: EnhancedKPICard
    incident_rate: EnhancedKPICard
    serious_incident_rate: EnhancedKPICard
    incident_followup_sla: EnhancedKPICard
    chronic_absence_rate: EnhancedKPICard
    capacity_utilization_rate: EnhancedKPICard
    training_completion_rate: EnhancedKPICard
    report_submission_rate: EnhancedKPICard
    alerts: List[AlertsSummary]
    last_updated: datetime
    data_freshness: str  # "fresh", "stale", "outdated"


class MonthlySnapshotResponse(BaseModel):
    message: str
    snapshots_created: int
    kindergarten_id: int
    month: date


class FilterOption(BaseModel):
    id: str | int
    name: str


class KpiFiltersResponse(BaseModel):
    kindergartens: List[FilterOption]
    governorates: List[FilterOption]
    cities: List[FilterOption] = []
    areas: List[FilterOption] = []
    dimension_types: List[FilterOption] = []


class KPIService:
    """Service for computing and managing KPIs"""

    @staticmethod
    def create_enhanced_kpi_card(
        kpi_key: str,
        value: float,
        unit: str = "%",
        last_updated: datetime = None,
        period_days: int = 30,
        has_data: bool = True,
        no_data_reason: Optional[str] = None,
        data_coverage: Optional[float] = None,
        numerator: Optional[float] = None,
        denominator: Optional[float] = None,
        previous_value: Optional[float] = None,
    ) -> EnhancedKPICard:
        """Create an enhanced KPI card with all metadata"""
        if last_updated is None:
            last_updated = datetime.now(_JORDAN_TZ)

        definition = KPI_DEFINITIONS.get(kpi_key, {})
        if not definition:
            # Fallback for unknown KPIs
            return EnhancedKPICard(
                kpi_key=kpi_key,
                name_ar=kpi_key,
                name_en=kpi_key,
                value=value,
                unit=unit,
                status="amber",
                trend="stable",
                trend_value=0.0,
                threshold=KPIThreshold(green_min=0, amber_min=0, amber_max=100),
                explanation=KPIExplanation(ar="غير محدد", en="Not defined"),
                manager_note=KPIManagerNote(ar="", en=""),
                action_items=[],
                last_updated=last_updated,
                period_days=period_days,
                has_data=has_data,
                no_data_reason=no_data_reason,
            )

        # Use centralized standards for band and confidence
        std = STANDARDS.get(kpi_key)
        denom_int = int(denominator) if denominator is not None else 0
        confidence = ConfidenceLevel.INSUFFICIENT
        if std:
            confidence = compute_confidence(
                denom_int,
                std.min_denominator,
                std.min_denominator_high,
                has_data,
            )
        coverage = data_coverage if data_coverage is not None else (100.0 if has_data else 0.0)
        band = assign_band(kpi_key, value, has_data, confidence, coverage)

        # Legacy threshold object for backward-compat with existing dashboard cards
        threshold = definition["threshold"]

        # Trend from previous period
        if previous_value is not None:
            trend, trend_value = KPIService._trend_from_values(value, previous_value)
        else:
            trend = "flat"
            trend_value = 0.0

        return EnhancedKPICard(
            kpi_key=kpi_key,
            name_ar=definition["name_ar"],
            name_en=definition["name_en"],
            value=value,
            unit=unit,
            status=band.value,
            trend=trend,
            trend_value=trend_value,
            threshold=threshold,
            explanation=definition["explanation"],
            manager_note=definition["manager_note"],
            action_items=definition["action_items"],
            last_updated=last_updated,
            period_days=period_days,
            has_data=has_data,
            no_data_reason=no_data_reason,
            data_coverage=data_coverage,
        )

    @staticmethod
    def _get_active_child_ids(db: Session, kindergarten_id: int) -> List[int]:
        """Return distinct active child IDs for a kindergarten."""
        rows = db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).distinct().all()
        return [row[0] for row in rows]

    @staticmethod
    def _count_working_days(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> int:
        """Count kindergarten working days in a period using calendar/policy rules."""
        return len(KPIService._list_working_days(db, kindergarten_id, period_start, period_end))

    @staticmethod
    def _list_working_days(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> List[date]:
        if period_start > period_end:
            return []
        # NOTE: working days always respect the Jordan school week (Sun–Thu) and
        # explicit OperatingCalendar entries — including under tests. There is no
        # TESTING short-circuit; tests that need specific days open must seed
        # OperatingCalendar rows so their working-day math matches production.
        calendar_rows = db.query(
            models.OperatingCalendar.date,
            models.OperatingCalendar.is_open,
        ).filter(
            models.OperatingCalendar.kindergarten_id == kindergarten_id,
            models.OperatingCalendar.date >= period_start,
            models.OperatingCalendar.date <= period_end,
        ).all()
        explicit_map = {row[0]: bool(row[1]) for row in calendar_rows}

        # Classification is shared with the bulk path so the two cannot drift.
        return KPIService._working_days_from_overrides(explicit_map, period_start, period_end)

    @staticmethod
    def _get_overlapping_active_enrollments(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> List[Tuple[int, date, date]]:
        """
        Return tuples of (child_id, effective_start, effective_end) for active enrollments
        overlapping the requested period.
        """
        rows = db.query(
            models.EnrollmentApplication.child_id,
            models.EnrollmentApplication.enrollment_start_date,
            models.EnrollmentApplication.enrollment_end_date,
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).all()

        result: List[Tuple[int, date, date]] = []
        for child_id, enrollment_start, enrollment_end in rows:
            start = enrollment_start or period_start
            end = enrollment_end or period_end
            effective_start = max(period_start, start)
            effective_end = min(period_end, end)
            if effective_start <= effective_end:
                result.append((int(child_id), effective_start, effective_end))
        return result

    @staticmethod
    def _count_expected_child_days(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Tuple[int, Dict[int, int], List[date]]:
        """
        Count expected child-days respecting working days and enrollment date ranges.
        Returns (total_expected_child_days, expected_days_per_child, working_days_list).

        The attendance-RATE path no longer calls this — it uses
        `_attendance_components_by_child`, which builds the denominator from the same
        per-child day-set as its numerator so the two cannot disagree. This function
        remains the denominator for the incident-rate and report-rate paths. The two
        builders produce identical expected counts for the normal single-segment case
        (pinned by test_scalar_and_bulk_agree_on_awkward_data and the KPI regressions);
        keep them in step if either is edited.
        """
        working_days = KPIService._list_working_days(db, kindergarten_id, period_start, period_end)
        if not working_days:
            return 0, {}, []

        enrollments = KPIService._get_overlapping_active_enrollments(
            db, kindergarten_id, period_start, period_end
        )
        if not enrollments:
            return 0, {}, working_days

        ordinals = [d.toordinal() for d in working_days]
        expected_by_child: Dict[int, int] = {}
        total_expected = 0

        for child_id, effective_start, effective_end in enrollments:
            left = bisect_left(ordinals, effective_start.toordinal())
            right = bisect_right(ordinals, effective_end.toordinal())
            expected_days = max(0, right - left)
            if expected_days <= 0:
                continue
            expected_by_child[child_id] = expected_by_child.get(child_id, 0) + expected_days
            total_expected += expected_days

        return total_expected, expected_by_child, working_days

    @staticmethod
    def _attended_child_days_by_child(
        db: Session,
        child_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, int]:
        """
        PHYSICAL attendance only: PRESENT + LATE.
        Excused absences are NOT counted as physical attendance per policy.
        Use _excused_child_days_by_child for excused counts.
        """
        if not child_ids:
            return {}
        rows = db.query(
            models.AttendanceLog.child_id,
            func.count(models.AttendanceLog.id).label("attended_count"),
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ]),
        ).group_by(models.AttendanceLog.child_id).all()
        return {int(row[0]): int(row[1] or 0) for row in rows}

    @staticmethod
    def _excused_child_days_by_child(
        db: Session,
        child_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, int]:
        """Count excused absence days per child (separate from physical attendance)."""
        if not child_ids:
            return {}
        rows = db.query(
            models.AttendanceLog.child_id,
            func.count(models.AttendanceLog.id).label("excused_count"),
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.EXCUSED,
        ).group_by(models.AttendanceLog.child_id).all()
        return {int(row[0]): int(row[1] or 0) for row in rows}

    @staticmethod
    def _late_child_days_by_child(
        db: Session,
        child_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, int]:
        """Count late arrival days per child."""
        if not child_ids:
            return {}
        rows = db.query(
            models.AttendanceLog.child_id,
            func.count(models.AttendanceLog.id).label("late_count"),
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.LATE,
        ).group_by(models.AttendanceLog.child_id).all()
        return {int(row[0]): int(row[1] or 0) for row in rows}

    @staticmethod
    def _count_attended_child_days(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
        active_child_ids: Optional[List[int]] = None,
    ) -> int:
        """
        Count physically attended child-days (PRESENT + LATE only) for active children.
        Excused absences are NOT counted as physical attendance.
        """
        if active_child_ids is None:
            active_child_ids = KPIService._get_active_child_ids(db, kindergarten_id)
        if not active_child_ids:
            return 0

        attended_map = KPIService._attended_child_days_by_child(
            db, active_child_ids, period_start, period_end
        )
        return int(sum(attended_map.values()))

    @staticmethod
    def _attendance_components_by_child(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Tuple[Dict[int, int], Dict[int, int], List[date]]:
        """Canonical per-child attendance: (expected_by_child, attended_by_child, working_days).

        Both counts are taken over the SAME per-child day-set — the kindergarten's
        working days (Sun–Thu plus OperatingCalendar overrides) intersected with the
        child's effective enrollment range. The attended set is a subset of the expected
        set, so ``attended <= expected`` for every child and any rate built from these
        cannot exceed 100%.

        This is the one definition every attendance-rate consumer shares. The bug it
        replaces counted the numerator over the raw window — every PRESENT/LATE log
        regardless of working day or enrollment range — against a denominator that
        respected both, so a child present outside their enrollment, or on a closed day,
        pushed the rate past 100% (measured at 333%).

        Physical attendance only (PRESENT + LATE); EXCUSED is not attendance. This is
        NOT the incident-exposure numerator: incident rates count every physical
        attendance day as exposure (see ``_count_attended_child_days``), because an
        incident can happen on any day a child is present.
        """
        working_days = KPIService._list_working_days(
            db, kindergarten_id, period_start, period_end
        )
        if not working_days:
            return {}, {}, []
        enrollments = KPIService._get_overlapping_active_enrollments(
            db, kindergarten_id, period_start, period_end
        )
        if not enrollments:
            return {}, {}, working_days

        expected_set_by_child = KPIService._expected_dayset_by_child(working_days, enrollments)
        expected_by_child = {cid: len(days) for cid, days in expected_set_by_child.items()}
        child_ids = list(expected_by_child.keys())

        attended_by_child: Dict[int, int] = {}
        if child_ids:
            rows = db.query(
                models.AttendanceLog.child_id,
                models.AttendanceLog.date,
            ).filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([
                    models.AttendanceStatus.PRESENT,
                    models.AttendanceStatus.LATE,
                ]),
            ).all()
            for cid, day in rows:
                expected_days = expected_set_by_child.get(int(cid))
                if expected_days and day.toordinal() in expected_days:
                    attended_by_child[int(cid)] = attended_by_child.get(int(cid), 0) + 1

        return expected_by_child, attended_by_child, working_days

    @staticmethod
    def _expected_dayset_by_child(
        working_days: List[date],
        enrollments: List[Tuple[int, date, date]],
    ) -> Dict[int, set]:
        """child_id -> set of expected-day ordinals (working days within its enrollment).

        A *set*, not a count, so that overlapping enrollment segments for one child
        cannot double-count a shared day, and so the attended numerator can be tested
        for membership against exactly the days that were expected. Shared by the scalar
        and bulk paths so the two cannot drift.
        """
        working_ords = [d.toordinal() for d in working_days]  # sorted ascending
        expected_set_by_child: Dict[int, set] = {}
        for child_id, effective_start, effective_end in enrollments:
            lo = bisect_left(working_ords, effective_start.toordinal())
            hi = bisect_right(working_ords, effective_end.toordinal())
            if hi > lo:
                expected_set_by_child.setdefault(int(child_id), set()).update(working_ords[lo:hi])
        return {cid: days for cid, days in expected_set_by_child.items() if days}

    @staticmethod
    def _compute_previous_period(period_start: date, period_end: date) -> tuple:
        """Return (prev_start, prev_end) of the same length immediately before period_start."""
        period_len = (period_end - period_start).days + 1
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=period_len - 1)
        return prev_start, prev_end

    @staticmethod
    def _trend_from_values(current: float, previous: float) -> tuple:
        """Return (direction, change) tuple. direction: 'up'|'down'|'flat'."""
        change = round(current - previous, 2)
        if abs(change) < 0.01:
            return "flat", 0.0
        return ("up" if change > 0 else "down"), change

    @staticmethod
    def compute_attendance_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> Optional[float]:
        """
        Physical attendance rate % = (PRESENT + LATE child-days / expected child-days) × 100.
        Excused absences are NOT included — use compute_excused_absence_rate separately.

        Numerator and denominator are taken over the same expected day-set
        (``_attendance_components_by_child``), so the result is bounded to [0, 100].

        Returns None when there are zero expected attendance days (no scheduled
        attendance opportunity), distinguishing "no data" from a genuine 0% rate.
        Returns 0.0 when expected days > 0 but no attendance was recorded.
        """
        expected_by_child, attended_by_child, _ = KPIService._attendance_components_by_child(
            db, kindergarten_id, period_start, period_end
        )
        expected_days = sum(expected_by_child.values())
        if expected_days == 0:
            return None  # No scheduled attendance opportunity

        attended_days = sum(attended_by_child.values())
        rate = (attended_days / expected_days) * 100
        return round(rate, 2)

    @staticmethod
    def compute_attendance_rates_bulk(
        db: Session,
        kindergarten_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, Optional[float]]:
        """`compute_attendance_rate` for many kindergartens in a fixed 3 queries.

        Same definition, same number — `test_bulk_attendance_rate_matches_per_kg`
        pins them together. This exists because the per-kindergarten form costs 4
        queries each, so a listing endpoint calling it in a loop is an N+1 (CLAUDE.md
        forbids); without it, callers like kg-overview grow their own inline formula
        and drift from the authoritative one.

        Returns {kindergarten_id: rate or None}; a kindergarten with no expected
        child-days maps to None (unavailable), distinguishing "0%" from "no data".
        """
        components = KPIService.compute_attendance_components_bulk(
            db, kindergarten_ids, period_start, period_end
        )
        return {
            kg_id: (round((attended / expected) * 100, 2) if expected else None)
            for kg_id, (attended, expected) in components.items()
        }

    @staticmethod
    def compute_attendance_components_bulk(
        db: Session,
        kindergarten_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, Tuple[int, int]]:
        """{kindergarten_id: (attended_child_days, expected_child_days)}.

        The parts, not the percentage, because a rate over a *set* of kindergartens is
        sum(attended)/sum(expected) — averaging the per-kindergarten percentages would
        weight a 3-child kindergarten the same as a 300-child one.
        """
        if not kindergarten_ids:
            return {}

        # 1. Calendar overrides for every kindergarten at once.
        calendar_rows = db.query(
            models.OperatingCalendar.kindergarten_id,
            models.OperatingCalendar.date,
            models.OperatingCalendar.is_open,
        ).filter(
            models.OperatingCalendar.kindergarten_id.in_(kindergarten_ids),
            models.OperatingCalendar.date >= period_start,
            models.OperatingCalendar.date <= period_end,
        ).all()
        explicit_by_kg: Dict[int, Dict[date, bool]] = {}
        for kg_id, day, is_open in calendar_rows:
            explicit_by_kg.setdefault(int(kg_id), {})[day] = bool(is_open)

        # 2. Active enrollments overlapping the window, for every kindergarten.
        enrollment_rows = db.query(
            models.EnrollmentApplication.kindergarten_id,
            models.EnrollmentApplication.child_id,
            models.EnrollmentApplication.enrollment_start_date,
            models.EnrollmentApplication.enrollment_end_date,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).all()

        enrollments_by_kg: Dict[int, List[Tuple[int, date, date]]] = {}
        for kg_id, child_id, enr_start, enr_end in enrollment_rows:
            start = enr_start or period_start
            end = enr_end or period_end
            effective_start = max(period_start, start)
            effective_end = min(period_end, end)
            if effective_start <= effective_end:
                enrollments_by_kg.setdefault(int(kg_id), []).append(
                    (int(child_id), effective_start, effective_end)
                )

        # Expected day-SET per child (union of working days within its enrollment),
        # via the same helper the scalar path uses so the two cannot drift. Sets, not
        # counts, because the attended numerator is tested for membership against
        # exactly these days — that intersection is what keeps the rate <= 100%.
        expected_by_kg: Dict[int, int] = {int(kg_id): 0 for kg_id in kindergarten_ids}
        expected_set_by_child: Dict[int, set] = {}
        child_to_kg: Dict[int, int] = {}
        for kg_id in kindergarten_ids:
            working_days = KPIService._working_days_from_overrides(
                explicit_by_kg.get(int(kg_id), {}), period_start, period_end
            )
            if not working_days:
                continue
            kg_sets = KPIService._expected_dayset_by_child(
                working_days, enrollments_by_kg.get(int(kg_id), [])
            )
            # Keying the per-child set and its kg by child_id alone assumes a child has
            # at most one active enrollment. That is enforced by the DB unique index
            # uq_enrollment_child_active (child_id, is_active), so a child cannot be
            # active in two kindergartens at once. If that invariant were ever relaxed,
            # this would attribute the child's attendance to only the last kg seen and
            # the bulk result would diverge from the per-kg scalar; key by
            # (kg_id, child_id) here if that day comes.
            for child_id, days in kg_sets.items():
                expected_set_by_child[child_id] = days
                child_to_kg[child_id] = int(kg_id)
                expected_by_kg[int(kg_id)] += len(days)

        # 3. Attended (PRESENT + LATE) child-days for every child at once, counted only
        #    on days that were expected — the whole reason this is not the raw window count.
        all_child_ids = list(expected_set_by_child.keys())
        attended_by_kg: Dict[int, int] = {int(kg_id): 0 for kg_id in kindergarten_ids}
        if all_child_ids:
            rows = db.query(
                models.AttendanceLog.child_id,
                models.AttendanceLog.date,
            ).filter(
                models.AttendanceLog.child_id.in_(all_child_ids),
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([
                    models.AttendanceStatus.PRESENT,
                    models.AttendanceStatus.LATE,
                ]),
            ).all()
            for child_id, day in rows:
                expected_days = expected_set_by_child.get(int(child_id))
                if expected_days and day.toordinal() in expected_days:
                    attended_by_kg[child_to_kg[int(child_id)]] += 1

        return {
            int(kg_id): (attended_by_kg[int(kg_id)], expected_by_kg[int(kg_id)])
            for kg_id in kindergarten_ids
        }

    @staticmethod
    def _working_days_from_overrides(
        explicit_map: Dict[date, bool],
        period_start: date,
        period_end: date,
    ) -> List[date]:
        """The day-classification half of `_list_working_days`, without the query.

        Split out so the bulk path can fetch every kindergarten's OperatingCalendar in
        one query and still classify days identically — the Jordan school week (Sun–Thu)
        with explicit OperatingCalendar entries overriding it.
        """
        if period_start > period_end:
            return []
        working_days: List[date] = []
        cursor = period_start
        while cursor <= period_end:
            if cursor in explicit_map:
                is_open = explicit_map[cursor]
            else:
                # Jordan school week is Sun–Thu; Friday (4) and Saturday (5) are closed.
                is_open = cursor.weekday() not in (4, 5)
            if is_open:
                working_days.append(cursor)
            cursor += timedelta(days=1)
        return working_days

    @staticmethod
    def compute_excused_absence_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> float:
        """
        Excused absence rate % = EXCUSED child-days / expected child-days × 100.
        Separate from physical attendance rate.
        """
        expected_days, expected_by_child, _ = KPIService._count_expected_child_days(
            db, kindergarten_id, period_start, period_end
        )
        if expected_days == 0:
            return 0.0
        active_child_ids = list(expected_by_child.keys())
        excused_map = KPIService._excused_child_days_by_child(
            db, active_child_ids, period_start, period_end
        )
        excused_total = int(sum(excused_map.values()))
        return round((excused_total / expected_days) * 100, 2)

    @staticmethod
    def compute_incident_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Incident rate per 1,000 attended child-days.
        Expressed per 1,000 (not per 100) to match kpi_standards.py thresholds
        and avoid misleadingly small decimal values for rare events.
        """
        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        _, expected_by_child, _ = KPIService._count_expected_child_days(
            db, kindergarten_id, period_start, period_end
        )
        active_child_ids = list(expected_by_child.keys())
        attended_days = KPIService._count_attended_child_days(
            db, kindergarten_id, period_start, period_end, active_child_ids
        )
        if attended_days == 0:
            return 0.0

        return round((incident_count / attended_days) * 1000, 3)

    @staticmethod
    def compute_serious_incident_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Serious incident rate (HIGH/CRITICAL severity) per 1,000 attended child-days.
        Expressed per 1,000 to match kpi_standards.py thresholds.
        """
        serious_incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.severity_level.in_([
                models.SeverityLevel.HIGH,
                models.SeverityLevel.CRITICAL
            ])
        ).scalar() or 0

        _, expected_by_child, _ = KPIService._count_expected_child_days(
            db, kindergarten_id, period_start, period_end
        )
        active_child_ids = list(expected_by_child.keys())
        attended_days = KPIService._count_attended_child_days(
            db, kindergarten_id, period_start, period_end, active_child_ids
        )
        if attended_days == 0:
            return 0.0

        return round((serious_incident_count / attended_days) * 1000, 3)

    @staticmethod
    def compute_ratio_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Staff-child ratio compliance % = (Compliant minutes / operating minutes) x 100
        """
        # Sum compliant and operating minutes
        result = db.query(
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes)
        ).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end
        ).first()

        compliant_minutes = result[0] or 0
        operating_minutes = result[1] or 0

        if operating_minutes <= 0:
            compliant_minutes, operating_minutes = KPIService._estimate_ratio_compliance_from_logs(
                db, kindergarten_id, period_start, period_end
            )
            if operating_minutes <= 0:
                return 0.0

        rate = (compliant_minutes / operating_minutes) * 100
        return round(rate, 2)

    @staticmethod
    def _estimate_ratio_compliance_from_logs(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Tuple[int, int]:
        """
        Fallback estimator when ratio cache is unavailable.
        Uses staff presence logs + child attendance presence over working days.
        """
        working_days = KPIService._list_working_days(db, kindergarten_id, period_start, period_end)
        if not working_days:
            return 0, 0

        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()
        minutes_per_day = 480
        if kg and kg.operating_hours_start and kg.operating_hours_end:
            try:
                start_time = datetime.strptime(kg.operating_hours_start, "%H:%M").time()
                end_time = datetime.strptime(kg.operating_hours_end, "%H:%M").time()
                start_minutes = start_time.hour * 60 + start_time.minute
                end_minutes = end_time.hour * 60 + end_time.minute
                parsed_minutes = end_minutes - start_minutes
                if parsed_minutes > 0:
                    minutes_per_day = parsed_minutes
            except ValueError:
                pass

        staff_rows = db.query(
            models.StaffPresenceLog.date,
            func.count(func.distinct(models.StaffPresenceLog.staff_id)).label("staff_count"),
        ).filter(
            models.StaffPresenceLog.kindergarten_id == kindergarten_id,
            models.StaffPresenceLog.date >= period_start,
            models.StaffPresenceLog.date <= period_end,
        ).group_by(models.StaffPresenceLog.date).all()
        staff_by_day = {row[0]: int(row[1] or 0) for row in staff_rows}

        child_rows = db.query(
            models.AttendanceLog.date,
            func.count(func.distinct(models.AttendanceLog.child_id)).label("child_count"),
        ).join(
            models.Class, models.Class.id == models.AttendanceLog.class_id
        ).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
                models.AttendanceStatus.EXCUSED,
            ]),
        ).group_by(models.AttendanceLog.date).all()
        children_by_day = {row[0]: int(row[1] or 0) for row in child_rows}

        compliant_minutes = 0
        operating_minutes = 0
        for day in working_days:
            operating_minutes += minutes_per_day
            children_count = children_by_day.get(day, 0)
            if children_count <= 0:
                continue
            staff_count = staff_by_day.get(day, 0)
            required_staff = max(1, ceil(children_count / 10))
            if staff_count >= required_staff:
                compliant_minutes += minutes_per_day
            elif staff_count > 0:
                compliant_minutes += int(minutes_per_day * (staff_count / required_staff))

        return compliant_minutes, operating_minutes

    @staticmethod
    def compute_incident_followup_sla_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Incident follow-up within SLA % = (Closed within SLA / requiring follow-up) x 100
        """
        # Count incidents requiring follow-up
        total_followup_required = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True
        ).scalar() or 0

        if total_followup_required == 0:
            return 0.0  # no incidents to follow up; caller checks quality.has_data

        # Count incidents closed within SLA
        closed_within_sla = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.isnot(None),
            models.Incident.closed_at <= models.Incident.followup_sla_deadline
        ).scalar() or 0

        rate = (closed_within_sla / total_followup_required) * 100
        return round(rate, 2)

    @staticmethod
    def compute_chronic_absence_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
        threshold_percent: float = 10.0
    ) -> float:
        """
        Chronic absence % = (Children with absence >= threshold / active children) x 100
        Default threshold: 10% of expected days
        """
        # Absence per child is (expected - attended)/expected, so the numerator must be
        # attended-among-expected or a child present outside their enrollment produces a
        # negative absence and silently escapes the chronic count. Same canonical
        # components as the attendance rate.
        expected_by_child, attended_by_child, _ = KPIService._attendance_components_by_child(
            db, kindergarten_id, period_start, period_end
        )
        if not expected_by_child:
            return 0.0

        active_child_ids = list(expected_by_child.keys())

        chronic_absence_count = 0
        for child_id in active_child_ids:
            expected_days = int(expected_by_child.get(child_id, 0))
            if expected_days <= 0:
                continue
            attended_days = int(attended_by_child.get(child_id, 0))
            absence_rate = ((expected_days - attended_days) / expected_days) * 100
            if absence_rate >= threshold_percent:
                chronic_absence_count += 1

        denominator = len(active_child_ids)
        if denominator == 0:
            return 0.0
        rate = (chronic_absence_count / denominator) * 100
        return round(rate, 2)

    @staticmethod
    def create_kpi_snapshot(
        db: Session,
        kindergarten_id: Optional[int],
        kpi_name: str,
        kpi_value: float,
        period_start: date,
        period_end: date,
        is_monthly: bool = False
    ) -> models.KPISnapshot:
        """Create KPI snapshot (immutable if monthly)"""
        snapshot = models.KPISnapshot(
            kindergarten_id=kindergarten_id,
            kpi_name=kpi_name,
            kpi_value=kpi_value,
            period_start=period_start,
            period_end=period_end,
            is_locked=is_monthly
        )

        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        return snapshot

    @staticmethod
    def populate_ratio_compliance_for_date(
        db: Session,
        kindergarten_id: int,
        date: date
    ) -> None:
        """
        Populate ratio compliance data for a specific date.
        This should be called daily or when attendance data changes.
        """
        # Skip weekends (assuming kindergarten doesn't operate on weekends)
        if date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return

        # Check if already exists
        existing = db.query(models.RatioCompliance).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date == date
        ).first()

        if existing:
            return  # Already populated

        # Get operating hours for the kindergarten
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if not kg or not kg.operating_hours_start or not kg.operating_hours_end:
            return  # Cannot calculate without operating hours

        # Parse time strings to datetime.time objects
        from datetime import datetime, time
        try:
            start_time = datetime.strptime(kg.operating_hours_start, '%H:%M').time()
            end_time = datetime.strptime(kg.operating_hours_end, '%H:%M').time()
        except ValueError:
            return  # Invalid time format

        # Calculate operating minutes
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        operating_minutes = end_minutes - start_minutes

        if operating_minutes <= 0:
            return

        # Get staff count (simplified - count active supervisors)
        staff_count = db.query(func.count(models.User.id)).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE
        ).scalar() or 0

        # Get child count (enrolled and active)
        child_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Calculate compliant minutes (simplified logic)
        # In a real system, this would track actual staffing throughout the day
        if staff_count > 0 and child_count > 0:
            # Assume 1:10 ratio is required (adjust based on regulations)
            required_staff = max(1, child_count // 10)
            if staff_count >= required_staff:
                compliant_minutes = operating_minutes
            else:
                # Partial compliance based on available staff
                compliance_ratio = staff_count / required_staff
                compliant_minutes = int(operating_minutes * compliance_ratio)
        else:
            compliant_minutes = 0

        # Create record
        record = models.RatioCompliance(
            kindergarten_id=kindergarten_id,
            date=date,
            operating_minutes=operating_minutes,
            compliant_minutes=compliant_minutes,
            staff_count_avg=float(staff_count),
            child_count_avg=float(child_count)
        )

        db.add(record)
        db.commit()

    @staticmethod
    def populate_ratio_compliance_for_period(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> None:
        """
        Populate ratio compliance data for a date range.
        """
        current_date = start_date
        while current_date <= end_date:
            KPIService.populate_ratio_compliance_for_date(db, kindergarten_id, current_date)
            current_date += timedelta(days=1)

    @staticmethod
    def compute_child_experience_index(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
        return round(float(bundle["cei_score"]), 2)

    @staticmethod
    def compute_parent_satisfaction_score(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> float:
        """
        Parent satisfaction derived from survey NPS scores.
        Converts NPS (-100..100) to 0..100 scale: (nps + 100) / 2.
        Returns 0.0 if no survey responses are available for the period.
        """
        score, _, _, _ = KPIService.compute_parent_satisfaction_details(
            db, kindergarten_id, period_start, period_end
        )
        return score

    @staticmethod
    def compute_governance_score(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> Tuple[float, str]:
        bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
        return round(float(bundle["governance_score"]), 2), str(bundle["governance_band"])

    @staticmethod
    def save_governance_score(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> models.GovernanceScore:
        """Compute and save governance score"""
        bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
        gqi = float(bundle["gqi_score"])
        cei = float(bundle["cei_score"])
        final_score = float(bundle["governance_score"])
        band = str(bundle["governance_band"])

        governance_score = models.GovernanceScore(
            kindergarten_id=kindergarten_id,
            period_start=period_start,
            period_end=period_end,
            governance_quality_index=gqi,
            child_experience_index=cei,
            final_governance_score=final_score,
            band=band
        )

        db.add(governance_score)
        db.commit()
        db.refresh(governance_score)

        return governance_score

    @staticmethod
    def generate_monthly_snapshots(db: Session, kindergarten_id: int,
                                  month: date) -> List[models.KPISnapshot]:
        """
        Generate immutable monthly KPI snapshots for a kindergarten
        """
        # Calculate period
        period_start = month.replace(day=1)
        if month.month == 12:
            period_end = date(month.year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(month.year, month.month + 1, 1) - timedelta(days=1)

        snapshots = []

        # Attendance rate
        attendance_rate = KPIService.compute_attendance_rate(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "attendance_rate", attendance_rate,
                period_start, period_end, is_monthly=True
            )
        )

        # Incident rate
        incident_rate = KPIService.compute_incident_rate(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "incident_rate", incident_rate,
                period_start, period_end, is_monthly=True
            )
        )

        # Ratio compliance
        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )
        snapshots.append(
            KPIService.create_kpi_snapshot(
                db, kindergarten_id, "ratio_compliance", ratio_compliance,
                period_start, period_end, is_monthly=True
            )
        )

        return snapshots
    
    @staticmethod
    def get_kpi_target(
        db: Session,
        kpi_name: str,
        kindergarten_id: Optional[int] = None,
        target_date: Optional[date] = None,
    ) -> Optional[models.KPITarget]:
        """
        Retrieves the most relevant KPI target for a given KPI name and kindergarten_id
        effective on the target_date. Prioritizes kindergarten-specific targets.
        """
        if target_date is None:
            target_date = _today_jordan()
        query = db.query(KPITarget).filter(
            KPITarget.kpi_name == kpi_name,
            KPITarget.effective_date <= target_date
        ).order_by(
            KPITarget.effective_date.desc()
        )

        # Prioritize kindergarten-specific targets
        if kindergarten_id:
            kg_target = query.filter(KPITarget.kindergarten_id == kindergarten_id).first()
            if kg_target:
                return kg_target
        
        # Fallback to network-wide targets
        network_target = query.filter(KPITarget.kindergarten_id == None).first()
        return network_target

    @staticmethod
    def compute_training_completion_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculates the percentage of mandatory staff training modules completed.
        """
        # Get all active staff in the kindergarten
        staff_users = db.query(models.User).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR])
        ).all()
        
        if not staff_users:
            return 0.0
        
        total_mandatory_modules = db.query(func.count(TrainingModule.id)).filter(
            TrainingModule.is_mandatory == True
        ).scalar() or 0

        if total_mandatory_modules == 0:
            return 0.0
        
        total_expected_completions = len(staff_users) * total_mandatory_modules
        
        if total_expected_completions == 0:
            return 0.0
            
        # Cumulative distinct (staff, mandatory-module) pairs completed as of period_end.
        # Only mandatory modules count — non-mandatory completions must not inflate
        # the numerator against a denominator that only counts mandatory modules.
        _completed_sq = (
            db.query(
                StaffTrainingCompletion.user_id,
                StaffTrainingCompletion.training_module_id,
            )
            .join(TrainingModule,
                  TrainingModule.id == StaffTrainingCompletion.training_module_id)
            .filter(
                StaffTrainingCompletion.kindergarten_id == kindergarten_id,
                StaffTrainingCompletion.user_id.in_([u.id for u in staff_users]),
                StaffTrainingCompletion.status == TrainingStatus.COMPLETED,
                StaffTrainingCompletion.completion_date <= period_end,
                TrainingModule.is_mandatory == True,
            )
            .distinct()
            .subquery()
        )
        actual_completions = db.query(func.count()).select_from(_completed_sq).scalar() or 0

        rate = (actual_completions / total_expected_completions) * 100
        return round(rate, 2)

    @staticmethod
    def compute_report_submission_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculate report submission rate as:
        submitted reports / expected reports * 100
        where expected reports respect active enrollment ranges and working days.
        """
        expected_reports, expected_by_child, _ = KPIService._count_expected_child_days(
            db, kindergarten_id, period_start, period_end
        )
        active_child_ids = list(expected_by_child.keys())
        if not active_child_ids:
            return 0.0
        if expected_reports == 0:
            return 0.0

        submitted_statuses = [
            models.DailyReportStatus.SUBMITTED,
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
            models.DailyReportStatus.REJECTED,
            models.DailyReportStatus.RETURNED,
        ]
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.kindergarten_id == kindergarten_id,
            models.DailyReport.child_id.in_(active_child_ids),
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_(submitted_statuses),
        ).scalar() or 0

        rate = min((submitted_reports / expected_reports) * 100, 100.0)
        return round(rate, 2)

    @staticmethod
    def compute_governance_quality_index(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
        return round(float(bundle["gqi_score"]), 2)

    @staticmethod
    def compute_capacity_utilization_rate(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculates the capacity utilization rate for a kindergarten.
        """
        total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).scalar() or 0

        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        if total_capacity == 0:
            return 0.0

        return round((active_enrollments / total_capacity) * 100, 2)

    @staticmethod
    def compute_new_enrollments(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> int:
        """Counts new enrollments created within the period."""
        return db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.created_at >= period_start,
            models.EnrollmentApplication.created_at <= period_end
        ).scalar() or 0

    @staticmethod
    def compute_checklist_compliance(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Checklist compliance % = completed required checklists / required checklists.
        Uses persisted daily_checklists records for open operating days only.
        """
        working_days = KPIService._list_working_days(db, kindergarten_id, period_start, period_end)
        if not working_days:
            return 0.0

        required_checklist_types = ("opening", "safety", "closing")
        required_count = len(working_days) * len(required_checklist_types)
        if required_count <= 0:
            return 0.0

        rows = db.query(func.count(models.DailyChecklist.id)).filter(
            models.DailyChecklist.kindergarten_id == kindergarten_id,
            models.DailyChecklist.checklist_date >= period_start,
            models.DailyChecklist.checklist_date <= period_end,
            models.DailyChecklist.checklist_type.in_(required_checklist_types),
            models.DailyChecklist.status == models.DailyChecklistStatus.COMPLETED,
        ).scalar() or 0

        return round(min((rows / required_count) * 100, 100.0), 2)


    @staticmethod
    def compute_regulatory_status(
        db: Session,
        kindergarten_id: int
    ) -> float:
        """
        Regulatory status KPI.
        Current implementation evaluates license validity.
        Inspection tracking is not yet modeled and should be displayed as partial coverage.
        """
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()
        if not kg or not kg.license_valid_until:
            return 0.0

        today = _today_jordan()
        if kg.license_valid_until < today:
            return 0.0
        if kg.license_valid_until <= today + timedelta(days=30):
            return 60.0
        return 100.0


    @staticmethod
    def compute_training_coverage(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date # This is likely not used for 'coverage' over a period, but for eligibility
    ) -> float:
        """
        Training coverage % - staff training completion rate.
        Now uses compute_training_completion_rate
        """
        return KPIService.compute_training_completion_rate(db, kindergarten_id, period_start, period_end)

    @staticmethod
    def compute_parent_satisfaction_details(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Tuple[float, float, int, int]:
        """
        Returns:
        - satisfaction score on 0..100 scale
        - response rate %
        - responses count
        - eligible parents count
        """
        survey_rows = db.query(
            models.SurveyResponse.nps_score
        ).join(
            models.Survey, models.Survey.id == models.SurveyResponse.survey_id
        ).filter(
            models.Survey.kindergarten_id == kindergarten_id,
            models.Survey.start_date <= period_end,
            models.Survey.end_date >= period_start,
            models.SurveyResponse.nps_score.isnot(None),
        ).all()
        nps_scores = [int(row[0]) for row in survey_rows if row[0] is not None]
        responses_count = len(nps_scores)

        eligible_parents = db.query(
            func.count(func.distinct(models.ParentProfile.user_id))
        ).join(
            models.Child, models.Child.parent_id == models.ParentProfile.id
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).scalar() or 0

        if responses_count == 0:
            return 0.0, 0.0, 0, int(eligible_parents)

        promoters = sum(1 for score in nps_scores if score >= 9)
        detractors = sum(1 for score in nps_scores if score <= 6)
        nps = ((promoters / responses_count) * 100) - ((detractors / responses_count) * 100)
        score_0_100 = round((nps + 100) / 2, 2)
        response_rate = round((responses_count / eligible_parents) * 100, 2) if eligible_parents else 0.0
        return score_0_100, response_rate, responses_count, int(eligible_parents)

    @staticmethod
    def compute_kpi_bundle(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Compute a full KPI bundle for one kindergarten and period with data-quality metadata.
        """
        # Canonical attendance components: expected and attended over the SAME expected
        # day-set (working days ∩ enrollment range), so attendance_rate and chronic
        # absence below are bounded. attended_by_child here is attended-among-expected.
        expected_by_child, attended_by_child, working_days = KPIService._attendance_components_by_child(
            db, kindergarten_id, period_start, period_end
        )
        expected_child_days = int(sum(expected_by_child.values()))
        child_ids = list(expected_by_child.keys())
        attended_child_days = int(sum(attended_by_child.values()))
        # Incident EXPOSURE is every physical-attendance day (PRESENT + LATE), not only
        # the expected ones — an incident can happen on any day a child is present. Kept
        # separate from the rate numerator on purpose (see _attendance_components_by_child).
        attended_exposure_days = KPIService._count_attended_child_days(
            db, kindergarten_id, period_start, period_end, child_ids
        )
        # Excused absence: separate count
        excused_by_child = KPIService._excused_child_days_by_child(
            db, child_ids, period_start, period_end
        )
        excused_child_days = int(sum(excused_by_child.values()))

        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
        ).scalar() or 0
        serious_incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.severity_level.in_([
                models.SeverityLevel.HIGH,
                models.SeverityLevel.CRITICAL,
            ]),
        ).scalar() or 0
        followup_required = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True,
        ).scalar() or 0
        followup_closed_within_sla = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.isnot(None),
            models.Incident.closed_at <= models.Incident.followup_sla_deadline,
        ).scalar() or 0

        ratio_result = db.query(
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes),
        ).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end,
        ).first()
        ratio_compliant_minutes = int(ratio_result[0] or 0)
        ratio_operating_minutes = int(ratio_result[1] or 0)
        if ratio_operating_minutes <= 0:
            ratio_compliant_minutes, ratio_operating_minutes = KPIService._estimate_ratio_compliance_from_logs(
                db, kindergarten_id, period_start, period_end
            )
        ratio_rate = round((ratio_compliant_minutes / ratio_operating_minutes) * 100, 2) if ratio_operating_minutes > 0 else 0.0

        required_checklist_types = ("opening", "safety", "closing")
        checklist_required = len(working_days) * len(required_checklist_types)
        checklist_completed = db.query(func.count(models.DailyChecklist.id)).filter(
            models.DailyChecklist.kindergarten_id == kindergarten_id,
            models.DailyChecklist.checklist_date >= period_start,
            models.DailyChecklist.checklist_date <= period_end,
            models.DailyChecklist.checklist_type.in_(required_checklist_types),
            models.DailyChecklist.status == models.DailyChecklistStatus.COMPLETED,
        ).scalar() or 0
        checklist_any = db.query(func.count(models.DailyChecklist.id)).filter(
            models.DailyChecklist.kindergarten_id == kindergarten_id,
            models.DailyChecklist.checklist_date >= period_start,
            models.DailyChecklist.checklist_date <= period_end,
            models.DailyChecklist.checklist_type.in_(required_checklist_types),
        ).scalar() or 0
        checklist_rate = round(min((checklist_completed / checklist_required) * 100, 100.0), 2) if checklist_required > 0 else 0.0

        staff_ids = [
            row[0]
            for row in db.query(models.User.id).filter(
                models.User.kindergarten_id == kindergarten_id,
                models.User.status == models.UserStatus.ACTIVE,
                models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            ).all()
        ]
        mandatory_modules = db.query(func.count(TrainingModule.id)).filter(
            TrainingModule.is_mandatory == True
        ).scalar() or 0
        training_expected = len(staff_ids) * int(mandatory_modules)
        training_completed = 0
        if training_expected > 0:
            _t_sq = (
                db.query(
                    StaffTrainingCompletion.user_id,
                    StaffTrainingCompletion.training_module_id,
                )
                .join(TrainingModule,
                      TrainingModule.id == StaffTrainingCompletion.training_module_id)
                .filter(
                    StaffTrainingCompletion.kindergarten_id == kindergarten_id,
                    StaffTrainingCompletion.user_id.in_(staff_ids),
                    StaffTrainingCompletion.status == TrainingStatus.COMPLETED,
                    StaffTrainingCompletion.completion_date <= period_end,
                    TrainingModule.is_mandatory == True,
                )
                .distinct()
                .subquery()
            )
            training_completed = db.query(func.count()).select_from(_t_sq).scalar() or 0
        training_rate = round((training_completed / training_expected) * 100, 2) if training_expected > 0 else 0.0

        submitted_statuses = [
            models.DailyReportStatus.SUBMITTED,
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
            models.DailyReportStatus.REJECTED,
            models.DailyReportStatus.RETURNED,
        ]
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.kindergarten_id == kindergarten_id,
            models.DailyReport.child_id.in_(child_ids if child_ids else [-1]),
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_(submitted_statuses),
        ).scalar() or 0
        report_rate = round(min((submitted_reports / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0

        parent_satisfaction, parent_response_rate, survey_responses, eligible_parents = KPIService.compute_parent_satisfaction_details(
            db, kindergarten_id, period_start, period_end
        )

        regulatory_status = KPIService.compute_regulatory_status(db, kindergarten_id)
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()
        has_license_data = bool(kg and kg.license_valid_until)

        chronic_absence_count = 0
        chronic_denominator = 0
        has_attendance_data = False
        for child_id in child_ids:
            expected_days = int(expected_by_child.get(child_id, 0))
            if expected_days <= 0:
                continue
            chronic_denominator += 1
            # Physical attendance only (PRESENT + LATE) for chronic absence calculation
            physically_attended = int(attended_by_child.get(child_id, 0))
            # Include excused as "not physically present" for chronic absence purposes
            # Chronic absence measures total absence regardless of excuse
            total_absent = expected_days - physically_attended - int(excused_by_child.get(child_id, 0))
            total_absent = max(0, total_absent)
            total_unexcused_and_excused = expected_days - physically_attended
            if physically_attended > 0 or int(excused_by_child.get(child_id, 0)) > 0:
                has_attendance_data = True
            absence_rate = (total_unexcused_and_excused / expected_days) * 100
            if absence_rate >= 10.0:
                chronic_absence_count += 1
        if chronic_denominator > 0 and has_attendance_data:
            chronic_absence_rate = round((chronic_absence_count / chronic_denominator) * 100, 2)
        else:
            chronic_absence_rate = 0.0

        attendance_rate = round((attended_child_days / expected_child_days) * 100, 2) if expected_child_days > 0 else 0.0
        excused_absence_rate = round((excused_child_days / expected_child_days) * 100, 2) if expected_child_days > 0 else 0.0
        # Incident rates expressed per 1,000 child-days to match kpi_standards.py thresholds.
        # per-100 values were always < threshold (2.0/1000) → permanently GREEN — now fixed.
        # Denominator is exposure (all physical-attendance days), not the rate numerator.
        incident_rate = round((incident_count / attended_exposure_days) * 1000, 3) if attended_exposure_days > 0 else 0.0
        serious_incident_rate = round((serious_incident_count / attended_exposure_days) * 1000, 3) if attended_exposure_days > 0 else 0.0
        # Legacy per-100 aliases kept for any consumers that haven't migrated yet
        incident_rate_per_100 = round((incident_count / attended_exposure_days) * 100, 2) if attended_exposure_days > 0 else 0.0
        serious_incident_rate_per_100 = round((serious_incident_count / attended_exposure_days) * 100, 2) if attended_exposure_days > 0 else 0.0
        incident_followup_sla = round((followup_closed_within_sla / followup_required) * 100, 2) if followup_required > 0 else 0.0

        gqi_components = [
            ("ratio_compliance", ratio_rate, 0.30, ratio_operating_minutes > 0),
            ("checklist_compliance", checklist_rate, 0.20, checklist_any > 0 and checklist_required > 0),
            ("regulatory_status", regulatory_status, 0.20, has_license_data),
            ("training_completion_rate", training_rate, 0.15, training_expected > 0),
            ("incident_followup_sla", incident_followup_sla, 0.15, followup_required > 0),
        ]
        gqi_weight_sum = sum(weight for _, _, weight, has_data in gqi_components if has_data)
        if gqi_weight_sum > 0:
            gqi_score = sum(value * weight for _, value, weight, has_data in gqi_components if has_data) / gqi_weight_sum
        else:
            gqi_score = 0.0

        cei_components = [
            ("attendance_rate", attendance_rate, 0.35, expected_child_days > 0),
            ("chronic_absence", 100 - chronic_absence_rate, 0.25, chronic_denominator > 0 and has_attendance_data),
            # serious_incident_rate is per-1,000 child-days; divide by 10 to restore
            # per-100 equivalent so the ceiling of 100 remains correctly calibrated.
            ("serious_incident_rate", 100 - min(serious_incident_rate / 10, 100), 0.20, attended_exposure_days > 0),
            ("parent_satisfaction", parent_satisfaction, 0.20, survey_responses > 0),
        ]
        cei_weight_sum = sum(weight for _, _, weight, has_data in cei_components if has_data)
        if cei_weight_sum > 0:
            cei_score = sum(value * weight for _, value, weight, has_data in cei_components if has_data) / cei_weight_sum
        else:
            cei_score = 0.0

        final_components = [
            ("gqi", gqi_score, 0.60, gqi_weight_sum > 0),
            ("cei", cei_score, 0.40, cei_weight_sum > 0),
        ]
        final_weight_sum = sum(weight for _, _, weight, has_data in final_components if has_data)
        if final_weight_sum > 0:
            governance_score = sum(value * weight for _, value, weight, has_data in final_components if has_data) / final_weight_sum
        else:
            governance_score = 0.0

        if governance_score >= 80:
            governance_band = "GREEN"
        elif governance_score >= 60:
            governance_band = "AMBER"
        else:
            governance_band = "RED"

        total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True,
        ).scalar() or 0
        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).scalar() or 0
        capacity_utilization_rate = round((active_enrollments / total_capacity) * 100, 2) if total_capacity > 0 else 0.0

        new_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.created_at >= period_start,
            models.EnrollmentApplication.created_at <= period_end,
        ).scalar() or 0

        # --- hard override rules (applied in priority order; all triggered rules recorded) ---
        open_critical_incidents = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            models.Incident.severity_level == models.SeverityLevel.CRITICAL,
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.is_(None),
            models.Incident.deleted_at.is_(None),
        ).scalar() or 0

        override_rules_triggered = []

        # Hard override rules — applied in deterministic priority order.
        # INSUFFICIENT_DATA_COVERAGE is set first; subsequent rate-based rules
        # (RATIO_BELOW_MINIMUM, OVERCAPACITY, UNRESOLVED_CRITICAL_INCIDENT) must not
        # downgrade INSUFFICIENT to RED — the raw values are unreliable when data is
        # missing. Only legal compliance violations (LICENSE_*) supersede INSUFFICIENT.

        # 1. Insufficient data coverage — < 60% of GQI weight dimensions have data.
        #    This is INSUFFICIENT, not RED — the system cannot rate what it cannot measure.
        insufficient_data = gqi_weight_sum < 0.60
        if insufficient_data:
            governance_band = "INSUFFICIENT"
            override_rules_triggered.append("INSUFFICIENT_DATA_COVERAGE")

        # 2. License status — legal compliance supersedes data coverage state.
        if kg is None or kg.license_valid_until is None:
            governance_band = "RED"
            override_rules_triggered.append("LICENSE_MISSING")
        elif kg.license_valid_until < _today_jordan():
            governance_band = "RED"
            override_rules_triggered.append("LICENSE_EXPIRED")

        # 3. Overcapacity — a hard physical safety fact, supersedes INSUFFICIENT.
        #    A room with more children than licensed capacity is dangerous regardless
        #    of KPI data quality.
        if active_enrollments > total_capacity and total_capacity > 0:
            governance_band = "RED"
            override_rules_triggered.append("OVERCAPACITY")

        # 4–5: Rate-based rules only apply when data coverage is sufficient.
        #      When data is insufficient these metrics are unreliable, so they are
        #      recorded for observability but must not override the INSUFFICIENT band.
        if not insufficient_data:
            # 4. Staff-to-child ratio below regulatory minimum
            if ratio_rate < 60.0 and ratio_operating_minutes > 0:
                governance_band = "RED"
                override_rules_triggered.append("RATIO_BELOW_MINIMUM")

            # 5. Unresolved critical incident — floor to AMBER regardless of current band
            if open_critical_incidents > 0:
                if governance_band == "GREEN":
                    governance_band = "AMBER"
                override_rules_triggered.append("UNRESOLVED_CRITICAL_INCIDENT")
        else:
            # Record triggered codes for observability even when data is insufficient
            if ratio_rate < 60.0 and ratio_operating_minutes > 0:
                override_rules_triggered.append("RATIO_BELOW_MINIMUM")
            if open_critical_incidents > 0:
                override_rules_triggered.append("UNRESOLVED_CRITICAL_INCIDENT")

        return {
            "attendance_rate": attendance_rate,
            "excused_absence_rate": excused_absence_rate,
            "incident_rate": incident_rate,
            "incident_rate_per_100": incident_rate_per_100,
            "serious_incident_rate": serious_incident_rate,
            "serious_incident_rate_per_100": serious_incident_rate_per_100,
            "incident_followup_sla": incident_followup_sla,
            "ratio_compliance": ratio_rate,
            "training_completion_rate": training_rate,
            "report_submission_rate": report_rate,
            "chronic_absence_rate": chronic_absence_rate,
            "checklist_compliance": checklist_rate,
            "regulatory_status": regulatory_status,
            "parent_satisfaction": parent_satisfaction,
            "parent_response_rate": parent_response_rate,
            "gqi_score": round(gqi_score, 2),
            "cei_score": round(cei_score, 2),
            "governance_score": round(governance_score, 2),
            "governance_band": governance_band,
            "capacity_utilization_rate": capacity_utilization_rate,
            "active_enrollments": int(active_enrollments),
            "new_enrollments": int(new_enrollments),
            "override_rules_triggered": override_rules_triggered,
            # numerators and denominators for transparency
            "numerators": {
                "attendance_rate": attended_child_days,
                "excused_absence_rate": excused_child_days,
                "incident_rate": incident_count,
                "serious_incident_rate": serious_incident_count,
                "incident_followup_sla": followup_closed_within_sla,
                "ratio_compliance": ratio_compliant_minutes,
                "training_completion_rate": training_completed,
                "report_submission_rate": submitted_reports,
                "chronic_absence_rate": chronic_absence_count,
                "checklist_compliance": checklist_completed,
                "capacity_utilization_rate": int(active_enrollments),
            },
            "denominators": {
                "attendance_rate": expected_child_days,
                "excused_absence_rate": expected_child_days,
                "incident_rate": attended_exposure_days,
                "serious_incident_rate": attended_exposure_days,
                "incident_followup_sla": followup_required,
                "ratio_compliance": ratio_operating_minutes,
                "training_completion_rate": training_expected,
                "report_submission_rate": expected_child_days,
                "chronic_absence_rate": chronic_denominator,
                "checklist_compliance": checklist_required,
                "capacity_utilization_rate": int(total_capacity),
            },
            "quality": {
                "attendance_rate": {
                    "has_data": expected_child_days > 0,
                    "coverage_pct": round(min((attended_child_days / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0,
                    "reason": "Missing active enrollment periods or operating calendar data" if expected_child_days == 0 else None,
                },
                "incident_rate": {
                    "has_data": attended_child_days > 0,
                    "coverage_pct": 100.0 if attended_child_days > 0 else 0.0,
                    "reason": "No attended child-days in selected period" if attended_child_days == 0 else None,
                },
                "serious_incident_rate": {
                    "has_data": attended_child_days > 0,
                    "coverage_pct": 100.0 if attended_child_days > 0 else 0.0,
                    "reason": "No attended child-days in selected period" if attended_child_days == 0 else None,
                },
                "incident_followup_sla": {
                    "has_data": followup_required > 0,
                    "coverage_pct": 100.0 if followup_required > 0 else 0.0,
                    "reason": "No follow-up-required incidents in selected period" if followup_required == 0 else None,
                },
                "ratio_compliance": {
                    "has_data": ratio_operating_minutes > 0,
                    "coverage_pct": round((ratio_operating_minutes / (len(working_days) * 60 * 8)) * 100, 2) if working_days else 0.0,
                    "reason": "No ratio compliance rows or staff/attendance logs for operating days" if ratio_operating_minutes == 0 else None,
                },
                "training_completion_rate": {
                    "has_data": training_expected > 0,
                    "coverage_pct": round((training_completed / training_expected) * 100, 2) if training_expected > 0 else 0.0,
                    "reason": "No active staff or mandatory training modules configured" if training_expected == 0 else None,
                },
                "report_submission_rate": {
                    "has_data": expected_child_days > 0,
                    "coverage_pct": round(min((submitted_reports / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0,
                    "reason": "No expected child-days for report submission denominator" if expected_child_days == 0 else None,
                },
                "chronic_absence_rate": {
                    "has_data": chronic_denominator > 0 and has_attendance_data,
                    "coverage_pct": 100.0 if chronic_denominator > 0 else 0.0,
                    "reason": "Missing attendance data for children in period" if chronic_denominator > 0 and not has_attendance_data else ("No children with expected attendance days in period" if chronic_denominator == 0 else None),
                },
                "checklist_compliance": {
                    "has_data": checklist_any > 0 and checklist_required > 0,
                    "coverage_pct": round((checklist_any / checklist_required) * 100, 2) if checklist_required > 0 else 0.0,
                    "reason": "No daily checklist records in selected period" if checklist_any == 0 else None,
                },
                "regulatory_status": {
                    "has_data": has_license_data,
                    "coverage_pct": 100.0 if has_license_data else 0.0,
                    "reason": "License validity not recorded for this kindergarten" if not has_license_data else None,
                },
                "parent_satisfaction": {
                    "has_data": survey_responses > 0,
                    "coverage_pct": parent_response_rate,
                    "reason": "No survey responses in selected period" if survey_responses == 0 else None,
                },
                "gqi_score": {
                    "has_data": gqi_weight_sum > 0,
                    "coverage_pct": round(gqi_weight_sum * 100, 2) if gqi_weight_sum > 0 else 0.0,
                    "reason": "Insufficient governance inputs (ratio/checklist/regulatory/training/SLA) in selected period" if gqi_weight_sum == 0 else None,
                },
                "cei_score": {
                    "has_data": cei_weight_sum > 0,
                    "coverage_pct": round(cei_weight_sum * 100, 2) if cei_weight_sum > 0 else 0.0,
                    "reason": "Insufficient child experience inputs (attendance/chronic absence/incidents/surveys) in selected period" if cei_weight_sum == 0 else None,
                },
                "governance_score": {
                    "has_data": final_weight_sum > 0,
                    "coverage_pct": round(final_weight_sum * 100, 2) if final_weight_sum > 0 else 0.0,
                    "reason": "Insufficient GQI/CEI inputs to compute governance score" if final_weight_sum == 0 else None,
                },
                "capacity_utilization_rate": {
                    "has_data": total_capacity > 0,
                    "coverage_pct": 100.0 if total_capacity > 0 else 0.0,
                    "reason": "No active class capacity configured for this kindergarten" if total_capacity == 0 else None,
                },
            },
        }
    
@router.post("/kpi/populate-ratio-compliance")
def populate_ratio_compliance_data(
    kindergarten_id: Optional[int] = None,
    days_back: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Populate ratio compliance data for historical dates"""
    validators.validate_manager_role(current_user)

    if current_user.role == models.UserRole.MANAGER and kindergarten_id is None:
        kindergarten_id = current_user.kindergarten_id
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID required")

    # Populate data for the last N days
    end_date = _today_jordan()
    start_date = end_date - timedelta(days=days_back)

    KPIService.populate_ratio_compliance_for_period(db, kindergarten_id, start_date, end_date)

    return {"message": f"Ratio compliance data populated for {days_back} days"}


@router.post("/kpi/admin/backfill-governance")
def backfill_governance_kpis(
    period_start: date = Query(..., description="Start date (inclusive)"),
    period_end: date = Query(..., description="End date (inclusive)"),
    kindergarten_ids: Optional[List[int]] = Query(None, description="Optional kindergarten ids; defaults to all active"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin-only backfill for governance KPIs and ratio-compliance cache.
    Idempotent behavior: existing governance score rows for the same KG+period are updated in place.
    """
    if period_start > period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_start must be on or before period_end")

    kg_query = db.query(models.Kindergarten.id).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if kindergarten_ids:
        kg_query = kg_query.filter(models.Kindergarten.id.in_(list(dict.fromkeys(kindergarten_ids))))
    target_kg_ids = [row[0] for row in kg_query.all()]
    if not target_kg_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active kindergartens found for backfill")

    updated = 0
    created = 0
    for kg_id in target_kg_ids:
        KPIService.populate_ratio_compliance_for_period(db, kg_id, period_start, period_end)
        bundle = KPIService.compute_kpi_bundle(db, kg_id, period_start, period_end)

        existing = db.query(models.GovernanceScore).filter(
            models.GovernanceScore.kindergarten_id == kg_id,
            models.GovernanceScore.period_start == period_start,
            models.GovernanceScore.period_end == period_end,
        ).first()
        if existing:
            existing.governance_quality_index = float(bundle["gqi_score"])
            existing.child_experience_index = float(bundle["cei_score"])
            existing.final_governance_score = float(bundle["governance_score"])
            existing.band = str(bundle["governance_band"])
            updated += 1
        else:
            db.add(
                models.GovernanceScore(
                    kindergarten_id=kg_id,
                    period_start=period_start,
                    period_end=period_end,
                    governance_quality_index=float(bundle["gqi_score"]),
                    child_experience_index=float(bundle["cei_score"]),
                    final_governance_score=float(bundle["governance_score"]),
                    band=str(bundle["governance_band"]),
                )
            )
            created += 1
    db.commit()

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergartens_processed": len(target_kg_ids),
        "created_rows": created,
        "updated_rows": updated,
    }


@router.post("/admin/kpi/backfill-governance")
def backfill_admin_governance_kpis(
    period_start: date = Query(..., description="Start date (inclusive)"),
    period_end: date = Query(..., description="End date (inclusive)"),
    kindergarten_ids: Optional[List[int]] = Query(None, description="Optional kindergarten ids; defaults to all active"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Canonical admin namespace for governance KPI backfill."""
    return backfill_governance_kpis(
        period_start=period_start,
        period_end=period_end,
        kindergarten_ids=kindergarten_ids,
        current_user=current_user,
        db=db,
    )


@router.get("/kpi/student-distribution")
def get_student_distribution(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get student distribution by level for dashboard chart"""
    validators.validate_manager_role(current_user)

    kg_id = current_user.kindergarten_id

    # Count enrollments by level/class
    # Simplified: group by class name or level
    results = db.query(
        models.Class.name_ar,
        func.count(models.EnrollmentApplication.id)
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.class_id == models.Class.id
    ).filter(
        models.Class.kindergarten_id == kg_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).group_by(models.Class.name_ar).all()

    if not results:
        # Fallback data
        return {
            "labels": ["KG1", "KG2", "حضانة"],
            "values": [0, 0, 0]
        }

    labels = [row[0] for row in results]
    values = [row[1] for row in results]

    return {
        "labels": labels,
        "values": values
    }

@router.get("/kpi/summary", response_model=KPISummaryResponse)
def get_kpi_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summarized KPI metrics for a given period (default: current month)"""
    validators.validate_manager_role(current_user)
    
    # Default to current month if not provided
    if not start_date or not end_date:
        today = _today_jordan()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
            
    kg_id = current_user.kindergarten_id
    
    # Compute metrics
    # Note: Using static methods from KPIService class
    att_rate = KPIService.compute_attendance_rate(db, kg_id, start_date, end_date)
    inc_rate = KPIService.compute_incident_rate(db, kg_id, start_date, end_date)
    ser_inc_rate = KPIService.compute_serious_incident_rate(db, kg_id, start_date, end_date)
    ratio_comp = KPIService.compute_ratio_compliance(db, kg_id, start_date, end_date)
    gqi = KPIService.compute_governance_quality_index(db, kg_id, start_date, end_date)
    return KPISummaryResponse(
        period_start=start_date,
        period_end=end_date,
        attendance_rate=att_rate,
        incident_rate=inc_rate,
        serious_incident_rate=ser_inc_rate,
        ratio_compliance=ratio_comp,
        gqi_score=gqi
    )

@router.get("/kpi/attendance-rate", response_model=AttendanceRateResponse)
def get_attendance_rate(
    kindergarten_id: Optional[int] = Query(None, description="Optional. Kindergarten ID. Managers see their own, Admins can specify any."),
    start_date: Optional[date] = Query(None, description="Start date for the period (YYYY-MM-DD). Defaults to start of current month."),
    end_date: Optional[date] = Query(None, description="End date for the period (YYYY-MM-DD). Defaults to end of current month."),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the attendance rate for a specified kindergarten and period.
    Admins can query any kindergarten. Managers can only query their own.
    """
    # Default to current month if dates not provided
    if not start_date or not end_date:
        today = _today_jordan()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # RBAC check
    if current_user.role == models.UserRole.MANAGER:
        if kindergarten_id is not None and kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(
                status_code=403, detail="Managers can only view KPIs for their assigned kindergarten."
            )
        target_kindergarten_id = current_user.kindergarten_id
    elif current_user.role == models.UserRole.ADMIN:
        if kindergarten_id is None:
            raise HTTPException(status_code=400, detail="Admin must specify a kindergarten_id.")
        target_kindergarten_id = kindergarten_id
    else:
        raise HTTPException(status_code=403, detail="Access denied. Admin or Manager role required.")

    if target_kindergarten_id is None:
        raise HTTPException(status_code=400, detail="Kindergarten ID is required.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == target_kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    attendance_rate = KPIService.compute_attendance_rate(db, target_kindergarten_id, start_date, end_date)

    return AttendanceRateResponse(
        kindergarten_id=target_kindergarten_id,
        period_start=start_date,
        period_end=end_date,
        attendance_rate=attendance_rate
    )

@router.get("/kpi/governance-score", response_model=GovernanceScoreResponse)
def get_governance_score(
    kindergarten_id: Optional[int] = Query(None, description="Optional. Kindergarten ID. Managers see their own, Admins can specify any."),
    start_date: Optional[date] = Query(None, description="Start date for the period (YYYY-MM-DD). Defaults to start of current month."),
    end_date: Optional[date] = Query(None, description="End date for the period (YYYY-MM-DD). Defaults to end of current month."),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the governance score and band for a specified kindergarten and period.
    Admins can query any kindergarten. Managers can only query their own.
    """
    # Default to current month if dates not provided
    if not start_date or not end_date:
        today = _today_jordan()
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # RBAC check
    if current_user.role == models.UserRole.MANAGER:
        if kindergarten_id is not None and kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(
                status_code=403, detail="Managers can only view KPIs for their assigned kindergarten."
            )
        target_kindergarten_id = current_user.kindergarten_id
    elif current_user.role == models.UserRole.ADMIN:
        if kindergarten_id is None:
            raise HTTPException(status_code=400, detail="Admin must specify a kindergarten_id.")
        target_kindergarten_id = kindergarten_id
    else:
        raise HTTPException(status_code=403, detail="Access denied. Admin or Manager role required.")

    if target_kindergarten_id is None:
        raise HTTPException(status_code=400, detail="Kindergarten ID is required.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == target_kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    governance_score, governance_band = KPIService.compute_governance_score(db, target_kindergarten_id, start_date, end_date)

    return GovernanceScoreResponse(
        kindergarten_id=target_kindergarten_id,
        period_start=start_date,
        period_end=end_date,
        governance_score=governance_score,
        governance_band=governance_band
    )

@router.post("/kpi/monthly-snapshots", response_model=MonthlySnapshotResponse)
def generate_monthly_snapshots(
    month: str = Query(..., description="Month in YYYY-MM format"),
    kindergarten_id: int = Query(..., description="Kindergarten ID"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Generate monthly KPI snapshots for a specific kindergarten and month.
    Requires admin role.
    """
    # Validate month format
    try:
        snapshot_month = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM.")

    # Ensure kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found.")

    # Generate snapshots
    snapshots = KPIService.generate_monthly_snapshots(db, kindergarten_id, snapshot_month)

    return MonthlySnapshotResponse(
        message=f"Generated {len(snapshots)} monthly KPI snapshots for kindergarten {kindergarten_id} for {month}.",
        snapshots_created=len(snapshots),
        kindergarten_id=kindergarten_id,
        month=snapshot_month
    )

@router.get("/kpi/dashboard-data", response_model=KPIDashboardResponse)
def get_kpi_dashboard_data(
    kindergarten_ids: Optional[List[int]] = Query(
        None, description="Kindergarten IDs to include (admin only)"
    ),
    governorate: Optional[str] = Query(
        None, description="Jordanian governorate filter (admin only)"
    ),
    city: Optional[str] = Query(
        None, description="City filter (admin only)"
    ),
    area: Optional[str] = Query(
        None, description="Area filter (admin only)"
    ),
    dimension_type: Optional[str] = Query(
        None, description="Analytics dimension type (NETWORK/GOVERNORATE/CITY/AREA/KINDERGARTEN)"
    ),
    dimension_id: Optional[str] = Query(
        None, description="Dimension value matching dimension_type"
    ),
    period_start: Optional[date] = Query(
        None, description="Start date for the KPI period (inclusive)"
    ),
    period_end: Optional[date] = Query(
        None, description="End date for the KPI period (inclusive)"
    ),
    granularity: str = Query(
        "weekly", pattern="^(daily|weekly|monthly)$", description="Trend granularity"
    ),
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get KPI dashboard data for admins and managers.
    """
    return get_consolidated_kpi_dashboard_data(
        kindergarten_ids=kindergarten_ids,
        governorate=governorate,
        city=city,
        area=area,
        dimension_type=dimension_type,
        dimension_id=dimension_id,
        period_start=period_start,
        period_end=period_end,
        granularity=granularity,
        locale=locale,
        current_user=current_user,
        db=db
    )


def get_consolidated_kpi_dashboard_data(
    kindergarten_ids: Optional[List[int]] = Query(
        None, description="Kindergarten IDs to include (admin only)"
    ),
    governorate: Optional[str] = Query(
        None, description="Jordanian governorate filter (admin only)"
    ),
    city: Optional[str] = Query(
        None, description="City filter (admin only)"
    ),
    area: Optional[str] = Query(
        None, description="Area filter (admin only)"
    ),
    dimension_type: Optional[str] = Query(
        None, description="Analytics dimension type (NETWORK/GOVERNORATE/CITY/AREA/KINDERGARTEN)"
    ),
    dimension_id: Optional[str] = Query(
        None, description="Dimension value matching dimension_type"
    ),
    period_start: Optional[date] = Query(
        None, description="Start date for the KPI period (inclusive)"
    ),
    period_end: Optional[date] = Query(
        None, description="End date for the KPI period (inclusive)"
    ),
    granularity: str = Query(
        "weekly", pattern="^(daily|weekly|monthly)$", description="Trend granularity"
    ),
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Consolidated KPI dashboard payload.
    Admins may filter by multiple dimensions; managers only see their own kindergarten.
    """
    granularity = granularity.lower()
    if granularity not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid granularity")

    if not period_start or not period_end:
        today = _today_jordan()
        period_start = today.replace(day=1)
        period_end = (
            date(today.year + 1, 1, 1) - timedelta(days=1)
            if today.month == 12
            else date(today.year, today.month + 1, 1) - timedelta(days=1)
        )

    if period_start > period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_start must be on or before period_end")

    if granularity == "daily" and (period_end - period_start).days > 92:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily granularity supports up to 93 days per request for performance.",
        )

    normalized_governorate: Optional[str] = None
    if governorate:
        try:
            normalized_governorate = validators.validate_jordan_governorate(governorate)
        except validators.ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    normalized_dimension_type: Optional[str] = None
    if dimension_type:
        normalized_dimension_type = dimension_type.upper()
        if normalized_dimension_type not in KPI_SUPPORTED_DIMENSION_TYPES:
            valid = ", ".join(KPI_SUPPORTED_DIMENSION_TYPES)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid dimension_type. Allowed: {valid}",
            )

    # Generate cache key after normalized values
    cache_key_parts = [
        f"user_{current_user.id}",
        f"role_{current_user.role.value}",
        f"kg_{sorted(kindergarten_ids or [])}",
        f"gov_{normalized_governorate or ''}",
        f"start_{period_start}",
        f"end_{period_end}",
        f"gran_{granularity}",
        f"loc_{locale}"
    ]
    if city:
        cache_key_parts.append(f"city_{city}")
    if area:
        cache_key_parts.append(f"area_{area}")
    if normalized_dimension_type:
        cache_key_parts.append(f"dim_type_{normalized_dimension_type}")
    if dimension_id:
        cache_key_parts.append(f"dim_id_{dimension_id}")
    cache_key = f"kpi_dashboard:{':'.join(cache_key_parts)}"
    
    # Try cache first
    cached_data = dashboard_cache.get(cache_key)
    if cached_data:
        return cached_data

    target_kindergarten_ids: List[int] = []
    selected_governorate: Optional[str] = normalized_governorate
    selected_city: Optional[str] = city
    selected_area: Optional[str] = area

    if current_user.role == models.UserRole.ADMIN:
        query = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )

        if kindergarten_ids:
            query = query.filter(models.Kindergarten.id.in_(list(dict.fromkeys(kindergarten_ids))))

        if normalized_dimension_type:
            if normalized_dimension_type == models.AnalyticsDimensionType.NETWORK.value:
                pass
            elif normalized_dimension_type == models.AnalyticsDimensionType.GOVERNORATE.value:
                if not dimension_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_id is required for GOVERNORATE")
                try:
                    normalized_dim_gov = validators.validate_jordan_governorate(dimension_id)
                except validators.ValidationError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                selected_governorate = normalized_dim_gov
                governorate_values = {normalized_dim_gov}
                if normalized_dim_gov in settings.JORDAN_GOVERNORATES:
                    idx = settings.JORDAN_GOVERNORATES.index(normalized_dim_gov)
                    governorate_values.add(settings.JORDAN_GOVERNORATES_ENGLISH[idx])
                query = query.filter(models.Kindergarten.governorate.in_(list(governorate_values)))
            elif normalized_dimension_type == models.AnalyticsDimensionType.DISTRICT.value:
                if not dimension_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_id is required for DISTRICT")
                selected_city = dimension_id
                query = query.filter(models.Kindergarten.district == dimension_id)
            elif normalized_dimension_type == models.AnalyticsDimensionType.AREA.value:
                if not dimension_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_id is required for AREA")
                selected_area = dimension_id
                query = query.filter(models.Kindergarten.area == dimension_id)
            elif normalized_dimension_type == models.AnalyticsDimensionType.KINDERGARTEN.value:
                if not dimension_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_id is required for KINDERGARTEN")
                try:
                    kg_id = int(dimension_id)
                except ValueError:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_id for KINDERGARTEN must be numeric")
                query = query.filter(models.Kindergarten.id == kg_id)

        if selected_governorate:
            governorate_values = {selected_governorate}
            if selected_governorate in settings.JORDAN_GOVERNORATES:
                idx = settings.JORDAN_GOVERNORATES.index(selected_governorate)
                governorate_values.add(settings.JORDAN_GOVERNORATES_ENGLISH[idx])
            query = query.filter(models.Kindergarten.governorate.in_(list(governorate_values)))
        if selected_city:
            query = query.filter(models.Kindergarten.district == selected_city)
        if selected_area:
            query = query.filter(models.Kindergarten.area == selected_area)

        target_kindergarten_ids = [row[0] for row in query.all()]
    elif current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manager is not assigned to a kindergarten")
        if kindergarten_ids and (len(kindergarten_ids) != 1 or kindergarten_ids[0] != current_user.kindergarten_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager can only access their assigned kindergarten")

        manager_kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == current_user.kindergarten_id
        ).first()
        if not manager_kg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager kindergarten not found")

        if normalized_governorate:
            governorate_values = {normalized_governorate}
            if normalized_governorate in settings.JORDAN_GOVERNORATES:
                idx = settings.JORDAN_GOVERNORATES.index(normalized_governorate)
                governorate_values.add(settings.JORDAN_GOVERNORATES_ENGLISH[idx])
            if manager_kg.governorate not in governorate_values:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager's kindergarten is not in the specified governorate")
        if city and manager_kg.district != city:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager's kindergarten is not in the specified city")
        if area and manager_kg.area != area:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager's kindergarten is not in the specified area")
        if normalized_dimension_type:
            if normalized_dimension_type == models.AnalyticsDimensionType.KINDERGARTEN.value and dimension_id:
                if str(current_user.kindergarten_id) != str(dimension_id):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager can only access own kindergarten dimension")
            elif normalized_dimension_type in {
                models.AnalyticsDimensionType.GOVERNORATE.value,
                models.AnalyticsDimensionType.DISTRICT.value,
                models.AnalyticsDimensionType.AREA.value,
            } and dimension_id:
                dim_value = dimension_id
                if normalized_dimension_type == models.AnalyticsDimensionType.GOVERNORATE.value:
                    try:
                        dim_value = validators.validate_jordan_governorate(dimension_id)
                    except validators.ValidationError as exc:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                    governorate_values = {dim_value}
                    if dim_value in settings.JORDAN_GOVERNORATES:
                        idx = settings.JORDAN_GOVERNORATES.index(dim_value)
                        governorate_values.add(settings.JORDAN_GOVERNORATES_ENGLISH[idx])
                    if manager_kg.governorate not in governorate_values:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager cannot access out-of-scope dimension")
                elif normalized_dimension_type == models.AnalyticsDimensionType.DISTRICT.value and manager_kg.district != dim_value:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager cannot access out-of-scope dimension")
                elif normalized_dimension_type == models.AnalyticsDimensionType.AREA.value and manager_kg.area != dim_value:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager cannot access out-of-scope dimension")

        selected_governorate = manager_kg.governorate
        selected_city = manager_kg.district
        selected_area = manager_kg.area
        target_kindergarten_ids = [current_user.kindergarten_id]
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view KPI dashboard")

    kindergarten_records = (
        db.query(models.Kindergarten)
        .filter(
            models.Kindergarten.id.in_(target_kindergarten_ids),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        )
        .all()
    )
    target_kindergarten_ids = [kg.id for kg in kindergarten_records]

    if not target_kindergarten_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No kindergartens found for the applied filters")

    translator = setup_translator(locale)
    _ = translator

    kindergarten_count = len(target_kindergarten_ids)
    single_kindergarten_id = target_kindergarten_ids[0] if kindergarten_count == 1 else None

    def _build_base_bundles_bulk() -> Dict[int, Dict[str, Any]]:
        """
        Compute KPI bundles for ALL target KGs using ~20 bulk GROUP-BY queries
        instead of N × compute_kpi_bundle() calls (was 218 × 18 = 3,924 queries).
        """
        today = _today_jordan()
        required_checklist_types = ("opening", "safety", "closing")

        # ── Working days per KG ───────────────────────────────────────────────
        if settings.TESTING:
            shared_working_days = [
                period_start + timedelta(days=i)
                for i in range((period_end - period_start).days + 1)
            ]
            working_days_by_kg: Dict[int, List[date]] = {
                kg_id: shared_working_days for kg_id in target_kindergarten_ids
            }
        else:
            cal_rows = db.query(
                models.OperatingCalendar.kindergarten_id,
                models.OperatingCalendar.date,
                models.OperatingCalendar.is_open,
            ).filter(
                models.OperatingCalendar.kindergarten_id.in_(target_kindergarten_ids),
                models.OperatingCalendar.date >= period_start,
                models.OperatingCalendar.date <= period_end,
            ).all()
            cal_explicit: Dict[int, Dict[date, bool]] = {}
            for _kg, _d, _open in cal_rows:
                cal_explicit.setdefault(int(_kg), {})[_d] = bool(_open)
            working_days_by_kg = {}
            for kg_id in target_kindergarten_ids:
                explicit = cal_explicit.get(kg_id, {})
                days: List[date] = []
                cursor = period_start
                while cursor <= period_end:
                    if explicit.get(cursor, cursor.weekday() not in (4, 5)):
                        days.append(cursor)
                    cursor += timedelta(days=1)
                working_days_by_kg[kg_id] = days

        # ── Enrollments: expected child-days per KG (Python bisect) ──────────
        enroll_rows = db.query(
            models.EnrollmentApplication.kindergarten_id,
            models.EnrollmentApplication.child_id,
            models.EnrollmentApplication.enrollment_start_date,
            models.EnrollmentApplication.enrollment_end_date,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).all()

        # Per-child expected day-SET (working days ∩ enrollment range), via the same
        # helper the scalar and bulk rate paths use. The attended numerator below is
        # tested for membership against exactly these days, which is what keeps the rate
        # <= 100% — the old inline count took every PRESENT/LATE log in the window.
        enroll_ranges_by_kg: Dict[int, List[Tuple[int, date, date]]] = {kg_id: [] for kg_id in target_kindergarten_ids}
        for _kg, _child, _es, _ee in enroll_rows:
            eff_start = max(period_start, _es or period_start)
            eff_end = min(period_end, _ee or period_end)
            if eff_start <= eff_end:
                enroll_ranges_by_kg[int(_kg)].append((int(_child), eff_start, eff_end))

        expected_set_by_child: Dict[int, set] = {}
        child_to_kg: Dict[int, int] = {}
        expected_by_child_by_kg: Dict[int, Dict[int, int]] = {kg_id: {} for kg_id in target_kindergarten_ids}
        for kg_id in target_kindergarten_ids:
            kg_sets = KPIService._expected_dayset_by_child(
                working_days_by_kg.get(kg_id, []), enroll_ranges_by_kg.get(kg_id, [])
            )
            # Per-child keying assumes one active enrollment per child (DB index
            # uq_enrollment_child_active); see compute_attendance_components_bulk.
            for cid, days in kg_sets.items():
                expected_set_by_child[cid] = days
                child_to_kg[cid] = kg_id
                expected_by_child_by_kg[kg_id][cid] = len(days)

        child_ids_by_kg: Dict[int, List[int]] = {kg_id: list(v.keys()) for kg_id, v in expected_by_child_by_kg.items()}
        expected_child_days_by_kg: Dict[int, int] = {kg_id: sum(v.values()) for kg_id, v in expected_by_child_by_kg.items()}

        # ── Attended child-days per child (single bulk query) ─────────────────
        # att_by_child: attended-among-expected (rate/absence numerator, bounded).
        # exposure_by_child: every physical-attendance day (incident exposure).
        all_child_ids = list(expected_set_by_child.keys())
        att_by_child: Dict[int, int] = {}
        exposure_by_child: Dict[int, int] = {}
        if all_child_ids:
            for cid, day in db.query(
                models.AttendanceLog.child_id,
                models.AttendanceLog.date,
            ).filter(
                models.AttendanceLog.child_id.in_(all_child_ids),
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([
                    models.AttendanceStatus.PRESENT,
                    models.AttendanceStatus.LATE,
                ]),
            ).all():
                cid = int(cid)
                exposure_by_child[cid] = exposure_by_child.get(cid, 0) + 1
                days = expected_set_by_child.get(cid)
                if days and day.toordinal() in days:
                    att_by_child[cid] = att_by_child.get(cid, 0) + 1

        # ── Incidents: 4 GROUP-BY queries ─────────────────────────────────────
        def _inc_query(extra_filters=()):
            q = db.query(
                models.Incident.kindergarten_id,
                func.count(models.Incident.id),
            ).filter(
                models.Incident.kindergarten_id.in_(target_kindergarten_ids),
                func.date(models.Incident.occurred_at) >= period_start,
                func.date(models.Incident.occurred_at) <= period_end,
                *extra_filters,
            ).group_by(models.Incident.kindergarten_id)
            return {int(r[0]): int(r[1]) for r in q.all()}

        inc_total_by_kg = _inc_query()
        inc_serious_by_kg = _inc_query([models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL])])
        inc_followup_by_kg = _inc_query([models.Incident.followup_required_flag == True])
        inc_sla_by_kg = _inc_query([
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.isnot(None),
            models.Incident.closed_at <= models.Incident.followup_sla_deadline,
        ])

        # ── Ratio compliance ──────────────────────────────────────────────────
        ratio_by_kg: Dict[int, Tuple[int, int]] = {}
        for r in db.query(
            models.RatioCompliance.kindergarten_id,
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes),
        ).filter(
            models.RatioCompliance.kindergarten_id.in_(target_kindergarten_ids),
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end,
        ).group_by(models.RatioCompliance.kindergarten_id).all():
            ratio_by_kg[int(r[0])] = (int(r[1] or 0), int(r[2] or 0))

        # ── Checklists ────────────────────────────────────────────────────────
        checklist_comp_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.DailyChecklist.kindergarten_id,
            func.count(models.DailyChecklist.id),
        ).filter(
            models.DailyChecklist.kindergarten_id.in_(target_kindergarten_ids),
            models.DailyChecklist.checklist_date >= period_start,
            models.DailyChecklist.checklist_date <= period_end,
            models.DailyChecklist.checklist_type.in_(required_checklist_types),
            models.DailyChecklist.status == models.DailyChecklistStatus.COMPLETED,
        ).group_by(models.DailyChecklist.kindergarten_id).all():
            checklist_comp_by_kg[int(r[0])] = int(r[1])

        checklist_any_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.DailyChecklist.kindergarten_id,
            func.count(models.DailyChecklist.id),
        ).filter(
            models.DailyChecklist.kindergarten_id.in_(target_kindergarten_ids),
            models.DailyChecklist.checklist_date >= period_start,
            models.DailyChecklist.checklist_date <= period_end,
            models.DailyChecklist.checklist_type.in_(required_checklist_types),
        ).group_by(models.DailyChecklist.kindergarten_id).all():
            checklist_any_by_kg[int(r[0])] = int(r[1])

        # ── Staff counts per KG ───────────────────────────────────────────────
        staff_count_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.User.kindergarten_id,
            func.count(models.User.id),
        ).filter(
            models.User.kindergarten_id.in_(target_kindergarten_ids),
            models.User.status == models.UserStatus.ACTIVE,
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
        ).group_by(models.User.kindergarten_id).all():
            staff_count_by_kg[int(r[0])] = int(r[1])

        # ── Training ──────────────────────────────────────────────────────────
        mandatory_modules_count: int = db.query(func.count(TrainingModule.id)).filter(
            TrainingModule.is_mandatory == True
        ).scalar() or 0

        # Cumulative distinct (kg, user, mandatory-module) triples completed as of period_end.
        # Only mandatory modules count — same constraint as the denominator.
        _tc_sq = (
            db.query(
                StaffTrainingCompletion.kindergarten_id.label("kg_id"),
                StaffTrainingCompletion.user_id,
                StaffTrainingCompletion.training_module_id,
            )
            .join(TrainingModule,
                  TrainingModule.id == StaffTrainingCompletion.training_module_id)
            .filter(
                StaffTrainingCompletion.kindergarten_id.in_(target_kindergarten_ids),
                StaffTrainingCompletion.status == TrainingStatus.COMPLETED,
                StaffTrainingCompletion.completion_date <= period_end,
                TrainingModule.is_mandatory == True,
            )
            .distinct()
            .subquery()
        )
        training_comp_by_kg: Dict[int, int] = {
            int(r[0]): int(r[1])
            for r in db.query(_tc_sq.c.kg_id, func.count()).group_by(_tc_sq.c.kg_id).all()
        }

        # ── Daily reports ─────────────────────────────────────────────────────
        submitted_statuses_list = [
            models.DailyReportStatus.SUBMITTED,
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
            models.DailyReportStatus.REJECTED,
            models.DailyReportStatus.RETURNED,
        ]
        reports_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.DailyReport.kindergarten_id,
            func.count(models.DailyReport.id),
        ).filter(
            models.DailyReport.kindergarten_id.in_(target_kindergarten_ids),
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_(submitted_statuses_list),
        ).group_by(models.DailyReport.kindergarten_id).all():
            reports_by_kg[int(r[0])] = int(r[1])

        # ── Capacity and enrollment counts ────────────────────────────────────
        cap_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.Class.kindergarten_id,
            func.sum(models.Class.capacity_total),
        ).filter(
            models.Class.kindergarten_id.in_(target_kindergarten_ids),
            models.Class.is_active == True,
        ).group_by(models.Class.kindergarten_id).all():
            cap_by_kg[int(r[0])] = int(r[1] or 0)

        active_enroll_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id),
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all():
            active_enroll_by_kg[int(r[0])] = int(r[1])

        new_enroll_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id),
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.created_at >= period_start,
            models.EnrollmentApplication.created_at <= period_end,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all():
            new_enroll_by_kg[int(r[0])] = int(r[1])

        # ── Parent satisfaction: bulk NPS scores + eligible parent counts ─────
        nps_by_kg: Dict[int, List[int]] = {}
        for r in db.query(
            models.Survey.kindergarten_id,
            models.SurveyResponse.nps_score,
        ).join(
            models.Survey, models.Survey.id == models.SurveyResponse.survey_id
        ).filter(
            models.Survey.kindergarten_id.in_(target_kindergarten_ids),
            models.Survey.start_date <= period_end,
            models.Survey.end_date >= period_start,
            models.SurveyResponse.nps_score.isnot(None),
        ).all():
            nps_by_kg.setdefault(int(r[0]), []).append(int(r[1]))

        eligible_parents_by_kg: Dict[int, int] = {}
        for r in db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(func.distinct(models.ParentProfile.user_id)),
        ).select_from(models.ParentProfile).join(
            models.Child, models.Child.parent_id == models.ParentProfile.id
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).group_by(models.EnrollmentApplication.kindergarten_id).all():
            eligible_parents_by_kg[int(r[0])] = int(r[1])

        # ── Assemble one bundle per KG (no DB calls below this line) ─────────
        result: Dict[int, Dict[str, Any]] = {}
        for kg_id in target_kindergarten_ids:
            kg = next((k for k in kindergarten_records if k.id == kg_id), None)
            working_days = working_days_by_kg.get(kg_id, [])
            expected_child_days = expected_child_days_by_kg.get(kg_id, 0)
            expected_by_child = expected_by_child_by_kg.get(kg_id, {})
            child_ids = child_ids_by_kg.get(kg_id, [])

            attended_child_days = sum(att_by_child.get(cid, 0) for cid in child_ids)
            att_by_child_kg = {cid: att_by_child.get(cid, 0) for cid in child_ids}
            # Exposure (all physical-attendance days) for incident rates — see the
            # att_by_child / exposure_by_child split above.
            attended_exposure_days = sum(exposure_by_child.get(cid, 0) for cid in child_ids)

            incident_count = inc_total_by_kg.get(kg_id, 0)
            serious_incident_count = inc_serious_by_kg.get(kg_id, 0)
            followup_required = inc_followup_by_kg.get(kg_id, 0)
            followup_closed_within_sla = inc_sla_by_kg.get(kg_id, 0)

            ratio_compliant, ratio_operating = ratio_by_kg.get(kg_id, (0, 0))
            if ratio_operating <= 0:
                ratio_compliant, ratio_operating = KPIService._estimate_ratio_compliance_from_logs(
                    db, kg_id, period_start, period_end
                )
            ratio_rate = round((ratio_compliant / ratio_operating) * 100, 2) if ratio_operating > 0 else 0.0

            checklist_required_count = len(working_days) * len(required_checklist_types)
            checklist_completed_count = checklist_comp_by_kg.get(kg_id, 0)
            checklist_any_count = checklist_any_by_kg.get(kg_id, 0)
            checklist_rate = round(min((checklist_completed_count / checklist_required_count) * 100, 100.0), 2) if checklist_required_count > 0 else 0.0

            staff_count = staff_count_by_kg.get(kg_id, 0)
            training_expected = staff_count * int(mandatory_modules_count)
            training_completed_count = training_comp_by_kg.get(kg_id, 0) if training_expected > 0 else 0
            training_rate = round((training_completed_count / training_expected) * 100, 2) if training_expected > 0 else 0.0

            submitted_reports_count = reports_by_kg.get(kg_id, 0)
            report_rate = round(min((submitted_reports_count / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0

            # Regulatory status from already-fetched KG record (no extra DB query)
            has_license_data = bool(kg and kg.license_valid_until)
            if not kg or not kg.license_valid_until:
                regulatory_status = 0.0
            elif kg.license_valid_until < today:
                regulatory_status = 0.0
            elif kg.license_valid_until <= today + timedelta(days=30):
                regulatory_status = 60.0
            else:
                regulatory_status = 100.0

            # Parent satisfaction from pre-fetched NPS data
            nps_scores = nps_by_kg.get(kg_id, [])
            survey_responses = len(nps_scores)
            eligible_parents = eligible_parents_by_kg.get(kg_id, 0)
            if survey_responses == 0:
                parent_satisfaction, parent_response_rate = 0.0, 0.0
            else:
                promoters = sum(1 for s in nps_scores if s >= 9)
                detractors = sum(1 for s in nps_scores if s <= 6)
                nps = ((promoters / survey_responses) * 100) - ((detractors / survey_responses) * 100)
                parent_satisfaction = round((nps + 100) / 2, 2)
                parent_response_rate = round((survey_responses / eligible_parents) * 100, 2) if eligible_parents > 0 else 0.0

            # Chronic absence rate
            chronic_absence_count = 0
            chronic_denominator = 0
            has_attendance_data = False
            for child_id in child_ids:
                exp_days = int(expected_by_child.get(child_id, 0))
                if exp_days <= 0:
                    continue
                chronic_denominator += 1
                att_days = int(att_by_child_kg.get(child_id, 0))
                if att_days > 0:
                    has_attendance_data = True
                if ((exp_days - att_days) / exp_days) * 100 >= 10.0:
                    chronic_absence_count += 1
            chronic_absence_rate = round((chronic_absence_count / chronic_denominator) * 100, 2) if (chronic_denominator > 0 and has_attendance_data) else 0.0

            attendance_rate = round((attended_child_days / expected_child_days) * 100, 2) if expected_child_days > 0 else 0.0
            incident_rate = round((incident_count / attended_exposure_days) * 1000, 3) if attended_exposure_days > 0 else 0.0
            serious_incident_rate_val = round((serious_incident_count / attended_exposure_days) * 1000, 3) if attended_exposure_days > 0 else 0.0
            incident_followup_sla = round((followup_closed_within_sla / followup_required) * 100, 2) if followup_required > 0 else 0.0

            gqi_components = [
                ("ratio_compliance", ratio_rate, 0.30, ratio_operating > 0),
                ("checklist_compliance", checklist_rate, 0.20, checklist_any_count > 0 and checklist_required_count > 0),
                ("regulatory_status", regulatory_status, 0.20, has_license_data),
                ("training_completion_rate", training_rate, 0.15, training_expected > 0),
                ("incident_followup_sla", incident_followup_sla, 0.15, followup_required > 0),
            ]
            gqi_weight_sum = sum(w for _, _, w, hd in gqi_components if hd)
            gqi_score = sum(v * w for _, v, w, hd in gqi_components if hd) / gqi_weight_sum if gqi_weight_sum > 0 else 0.0

            cei_components = [
                ("attendance_rate", attendance_rate, 0.35, expected_child_days > 0),
                ("chronic_absence", 100 - chronic_absence_rate, 0.25, chronic_denominator > 0 and has_attendance_data),
                # serious_incident_rate_val is per-1,000 child-days; divide by 10 for per-100 equivalent.
                ("serious_incident_rate", 100 - min(serious_incident_rate_val / 10, 100), 0.20, attended_exposure_days > 0),
                ("parent_satisfaction", parent_satisfaction, 0.20, survey_responses > 0),
            ]
            cei_weight_sum = sum(w for _, _, w, hd in cei_components if hd)
            cei_score = sum(v * w for _, v, w, hd in cei_components if hd) / cei_weight_sum if cei_weight_sum > 0 else 0.0

            final_components = [
                ("gqi", gqi_score, 0.60, gqi_weight_sum > 0),
                ("cei", cei_score, 0.40, cei_weight_sum > 0),
            ]
            final_weight_sum = sum(w for _, _, w, hd in final_components if hd)
            governance_score = sum(v * w for _, v, w, hd in final_components if hd) / final_weight_sum if final_weight_sum > 0 else 0.0

            if governance_score >= 80:
                governance_band = "GREEN"
            elif governance_score >= 60:
                governance_band = "AMBER"
            else:
                governance_band = "RED"
            if kg and kg.license_valid_until and kg.license_valid_until < today:
                governance_band = "RED"

            total_capacity = cap_by_kg.get(kg_id, 0)
            active_enrollments_count = active_enroll_by_kg.get(kg_id, 0)
            capacity_utilization = round((active_enrollments_count / total_capacity) * 100, 2) if total_capacity > 0 else 0.0
            new_enrollments_count = new_enroll_by_kg.get(kg_id, 0)

            result[kg_id] = {
                "attendance_rate": attendance_rate,
                "incident_rate": incident_rate,
                "serious_incident_rate": serious_incident_rate_val,
                "incident_followup_sla": incident_followup_sla,
                "ratio_compliance": ratio_rate,
                "training_completion_rate": training_rate,
                "report_submission_rate": report_rate,
                "chronic_absence_rate": chronic_absence_rate,
                "checklist_compliance": checklist_rate,
                "regulatory_status": regulatory_status,
                "parent_satisfaction": parent_satisfaction,
                "parent_response_rate": parent_response_rate,
                "gqi_score": round(gqi_score, 2),
                "cei_score": round(cei_score, 2),
                "governance_score": round(governance_score, 2),
                "governance_band": governance_band,
                "capacity_utilization_rate": capacity_utilization,
                "active_enrollments": active_enrollments_count,
                "new_enrollments": new_enrollments_count,
                "quality": {
                    "attendance_rate": {
                        "has_data": expected_child_days > 0,
                        "coverage_pct": round(min((attended_child_days / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0,
                        "reason": "Missing active enrollment periods or operating calendar data" if expected_child_days == 0 else None,
                    },
                    "incident_rate": {
                        "has_data": attended_exposure_days > 0,
                        "coverage_pct": 100.0 if attended_exposure_days > 0 else 0.0,
                        "reason": "No attended child-days in selected period" if attended_exposure_days == 0 else None,
                    },
                    "serious_incident_rate": {
                        "has_data": attended_exposure_days > 0,
                        "coverage_pct": 100.0 if attended_exposure_days > 0 else 0.0,
                        "reason": "No attended child-days in selected period" if attended_exposure_days == 0 else None,
                    },
                    "incident_followup_sla": {
                        "has_data": followup_required > 0,
                        "coverage_pct": 100.0 if followup_required > 0 else 0.0,
                        "reason": "No follow-up-required incidents in selected period" if followup_required == 0 else None,
                    },
                    "ratio_compliance": {
                        "has_data": ratio_operating > 0,
                        "coverage_pct": round((ratio_operating / (len(working_days) * 60 * 8)) * 100, 2) if working_days else 0.0,
                        "reason": "No ratio compliance rows or staff/attendance logs for operating days" if ratio_operating == 0 else None,
                    },
                    "training_completion_rate": {
                        "has_data": training_expected > 0,
                        "coverage_pct": round((training_completed_count / training_expected) * 100, 2) if training_expected > 0 else 0.0,
                        "reason": "No active staff or mandatory training modules configured" if training_expected == 0 else None,
                    },
                    "report_submission_rate": {
                        "has_data": expected_child_days > 0,
                        "coverage_pct": round(min((submitted_reports_count / expected_child_days) * 100, 100.0), 2) if expected_child_days > 0 else 0.0,
                        "reason": "No expected child-days for report submission denominator" if expected_child_days == 0 else None,
                    },
                    "chronic_absence_rate": {
                        "has_data": chronic_denominator > 0 and has_attendance_data,
                        "coverage_pct": 100.0 if chronic_denominator > 0 else 0.0,
                        "reason": "Missing attendance data for children in period" if chronic_denominator > 0 and not has_attendance_data else ("No children with expected attendance days in period" if chronic_denominator == 0 else None),
                    },
                    "checklist_compliance": {
                        "has_data": checklist_any_count > 0 and checklist_required_count > 0,
                        "coverage_pct": round((checklist_any_count / checklist_required_count) * 100, 2) if checklist_required_count > 0 else 0.0,
                        "reason": "No daily checklist records in selected period" if checklist_any_count == 0 else None,
                    },
                    "regulatory_status": {
                        "has_data": has_license_data,
                        "coverage_pct": 100.0 if has_license_data else 0.0,
                        "reason": "License validity not recorded for this kindergarten" if not has_license_data else None,
                    },
                    "parent_satisfaction": {
                        "has_data": survey_responses > 0,
                        "coverage_pct": parent_response_rate,
                        "reason": "No survey responses in selected period" if survey_responses == 0 else None,
                    },
                    "gqi_score": {
                        "has_data": gqi_weight_sum > 0,
                        "coverage_pct": round(gqi_weight_sum * 100, 2) if gqi_weight_sum > 0 else 0.0,
                        "reason": "Insufficient governance inputs in selected period" if gqi_weight_sum == 0 else None,
                    },
                    "cei_score": {
                        "has_data": cei_weight_sum > 0,
                        "coverage_pct": round(cei_weight_sum * 100, 2) if cei_weight_sum > 0 else 0.0,
                        "reason": "Insufficient child experience inputs in selected period" if cei_weight_sum == 0 else None,
                    },
                    "governance_score": {
                        "has_data": final_weight_sum > 0,
                        "coverage_pct": round(final_weight_sum * 100, 2) if final_weight_sum > 0 else 0.0,
                        "reason": "Insufficient GQI/CEI inputs to compute governance score" if final_weight_sum == 0 else None,
                    },
                    "capacity_utilization_rate": {
                        "has_data": total_capacity > 0,
                        "coverage_pct": 100.0 if total_capacity > 0 else 0.0,
                        "reason": "No active class capacity configured for this kindergarten" if total_capacity == 0 else None,
                    },
                },
            }
        return result

    base_bundle_by_kg = _build_base_bundles_bulk()

    totals = {
        "gce_score": 0.0,
        "attendance_rate": 0.0,
        "incident_rate": 0.0,
        "serious_incident_rate": 0.0,
        "ratio_compliance": 0.0,
        "training_completion_rate": 0.0,
        "report_submission_rate": 0.0,
        "capacity_utilization_rate": 0.0,
        "chronic_absence_rate": 0.0,
        "incident_followup_sla": 0.0,
        "new_enrollments": 0,
    }
    # Summed numerators and denominators across all bundles for confidence calculation
    agg_nums: Dict[str, float] = {}
    agg_dens: Dict[str, float] = {}

    for bundle in base_bundle_by_kg.values():
        totals["gce_score"] += float(bundle["governance_score"])
        totals["attendance_rate"] += float(bundle["attendance_rate"])
        totals["incident_rate"] += float(bundle["incident_rate"])
        totals["serious_incident_rate"] += float(bundle["serious_incident_rate"])
        totals["ratio_compliance"] += float(bundle["ratio_compliance"])
        totals["training_completion_rate"] += float(bundle["training_completion_rate"])
        totals["report_submission_rate"] += float(bundle["report_submission_rate"])
        totals["capacity_utilization_rate"] += float(bundle["capacity_utilization_rate"])
        totals["chronic_absence_rate"] += float(bundle["chronic_absence_rate"])
        totals["incident_followup_sla"] += float(bundle["incident_followup_sla"])
        totals["new_enrollments"] += int(bundle["new_enrollments"])
        for k, v in bundle.get("numerators", {}).items():
            agg_nums[k] = agg_nums.get(k, 0.0) + float(v or 0)
        for k, v in bundle.get("denominators", {}).items():
            agg_dens[k] = agg_dens.get(k, 0.0) + float(v or 0)

    total_active_enrollments = (
        sum(int(bundle["active_enrollments"]) for bundle in base_bundle_by_kg.values())
    )

    def _determine_band(value: float, target: Optional[models.KPITarget], lower_is_better: bool) -> str:
        resolved = float(value)
        if target:
            limit = target.target_value
            if lower_is_better:
                if resolved <= limit:
                    return "GREEN"
                if resolved <= limit * 1.1:
                    return "AMBER"
                return "RED"
            if resolved >= limit:
                return "GREEN"
            if resolved >= limit * 0.8:
                return "AMBER"
            return "RED"
        if lower_is_better:
            if resolved <= 1.0:
                return "GREEN"
            if resolved <= 2.0:
                return "AMBER"
            return "RED"
        if resolved >= 80.0:
            return "GREEN"
        if resolved >= 60.0:
            return "AMBER"
        return "RED"

    LOWER_IS_BETTER = {
        "incident_rate",
        "serious_incident_rate",
        "chronic_absence_rate",
    }

    def _aggregate_quality(metric_key: str) -> Dict[str, Any]:
        metric_quality = [
            bundle["quality"].get(metric_key, {})
            for bundle in base_bundle_by_kg.values()
        ]
        if not metric_quality:
            return {"has_data": False, "coverage_pct": 0.0, "reason": "No kindergartens in scope"}

        coverage_values = [
            float(item.get("coverage_pct", 0.0) or 0.0)
            for item in metric_quality
        ]
        has_data_values = [bool(item.get("has_data")) for item in metric_quality]
        if any(has_data_values):
            return {
                "has_data": True,
                "coverage_pct": round(sum(coverage_values) / len(coverage_values), 2),
                "reason": None,
            }
        reason = next((item.get("reason") for item in metric_quality if item.get("reason")), "No data")
        return {"has_data": False, "coverage_pct": 0.0, "reason": reason}

    def _create_card(
        value: float,
        kpi_name: str,
        unit: Optional[str],
        is_percentage: bool,
        quality_key: Optional[str] = None,
    ) -> KPICardData:
        target = KPIService.get_kpi_target(db, kpi_name, single_kindergarten_id, period_end)
        lower_is_better = kpi_name in LOWER_IS_BETTER
        band_str = _determine_band(value, target, lower_is_better)
        alert = "threshold_breached" if band_str == "RED" else None
        quality_info = _aggregate_quality(quality_key or kpi_name)
        has_data = bool(quality_info["has_data"])

        # Populate enriched fields from kpi_standards
        std = STANDARDS.get(kpi_name)
        denom = int(agg_dens.get(kpi_name, 0))
        numer = agg_nums.get(kpi_name)
        confidence_level = compute_confidence(
            denom, std.min_denominator if std else 10,
            std.min_denominator_high if std else 30, has_data,
        )
        band_color = BandColor(band_str.lower()) if band_str.lower() in [b.value for b in BandColor] else BandColor.GRAY
        meaning_ar = get_band_meaning(kpi_name, band_color, "ar")
        meaning_en = get_band_meaning(kpi_name, band_color, "en")
        decision_ar = get_band_action(kpi_name, band_color, "ar")
        decision_en = get_band_action(kpi_name, band_color, "en")

        return KPICardData(
            value=round(value, 2),
            unit="%" if is_percentage else unit,
            band=band_str,
            alert=alert,
            has_data=has_data,
            data_coverage=float(quality_info["coverage_pct"]),
            no_data_reason=quality_info["reason"] if not has_data else None,
            numerator=round(numer, 2) if numer is not None else None,
            denominator=round(denom, 2) if denom > 0 else None,
            confidence=confidence_level.value,
            threshold_source=get_threshold_source_dict(kpi_name) or None,
            meaning_ar=meaning_ar or None,
            meaning_en=meaning_en or None,
            decision_guidance_ar=decision_ar or None,
            decision_guidance_en=decision_en or None,
        )

    def _next_period_start(dt: date) -> date:
        if granularity == "daily":
            return dt + timedelta(days=1)
        if granularity == "weekly":
            return dt + timedelta(weeks=1)
        if dt.month == 12:
            return date(dt.year + 1, 1, 1)
        return date(dt.year, dt.month + 1, 1)

    def _build_trend(
        metric_key: str,
        aggregate: str = "average",
    ) -> List[TrendDataPoint]:
        bundle_window_cache: Dict[Tuple[int, date, date], Dict[str, Any]] = {}

        def _window_bundle(kg_id: int, start: date, end: date) -> Dict[str, Any]:
            cache_key = (kg_id, start, end)
            if cache_key not in bundle_window_cache:
                bundle_window_cache[cache_key] = KPIService.compute_kpi_bundle(db, kg_id, start, end)
            return bundle_window_cache[cache_key]

        points: List[TrendDataPoint] = []
        current = period_start
        while current <= period_end:
            next_start = _next_period_start(current)
            window_end = min(period_end, next_start - timedelta(days=1))
            if window_end < current:
                window_end = current
            total_value = 0.0
            for kg_id in target_kindergarten_ids:
                window_bundle = _window_bundle(kg_id, current, window_end)
                total_value += float(window_bundle.get(metric_key, 0.0))
            if aggregate == "average" and kindergarten_count:
                value = round(total_value / kindergarten_count, 2)
            else:
                value = round(total_value, 2)
            points.append(TrendDataPoint(date=current, value=value))
            current = next_start
        return points

    def _bulk_build_all_trends() -> Tuple[
        List[TrendDataPoint], List[TrendDataPoint],
        List[TrendDataPoint], List[TrendDataPoint],
    ]:
        """
        Build all 4 trend series with 5 bulk SQL queries instead of calling
        compute_kpi_bundle() once per KG per window (was ~4,360 calls → 30 s timeout).
        Attendance, incidents, and enrollments are fetched for the full period at once
        then bucketed per window in Python. Governance reuses base_bundle_by_kg averages.
        """
        windows: List[Tuple[date, date]] = []
        cur = period_start
        while cur <= period_end:
            nxt = _next_period_start(cur)
            w_end = min(period_end, nxt - timedelta(days=1))
            if w_end < cur:
                w_end = cur
            windows.append((cur, w_end))
            cur = nxt

        if not windows:
            empty: List[TrendDataPoint] = []
            return empty, empty, empty, empty

        # 1. Count of active enrolled children across all target KGs
        n_enrolled: int = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).scalar() or 0

        # 2. Attended child-days grouped by date (subquery join avoids large IN clause)
        enrolled_child_sq = (
            db.query(models.EnrollmentApplication.child_id)
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            .subquery()
        )
        att_rows = db.query(
            models.AttendanceLog.date,
            func.count(models.AttendanceLog.id),
        ).join(
            enrolled_child_sq,
            models.AttendanceLog.child_id == enrolled_child_sq.c.child_id,
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
                # EXCUSED is NOT physical attendance — excluded per policy
            ]),
        ).group_by(models.AttendanceLog.date).all()
        att_by_date: Dict[date, int] = {r[0]: int(r[1]) for r in att_rows}

        # 3. Incident count grouped by date
        inc_rows = db.query(
            func.date(models.Incident.occurred_at).label("d"),
            func.count(models.Incident.id),
        ).filter(
            models.Incident.kindergarten_id.in_(target_kindergarten_ids),
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
        ).group_by(func.date(models.Incident.occurred_at)).all()
        inc_by_date: Dict[str, int] = {str(r[0]): int(r[1]) for r in inc_rows}

        # 4. New enrollment count grouped by date
        enroll_rows = db.query(
            func.date(models.EnrollmentApplication.created_at).label("d"),
            func.count(models.EnrollmentApplication.id),
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
            func.date(models.EnrollmentApplication.created_at) >= period_start,
            func.date(models.EnrollmentApplication.created_at) <= period_end,
        ).group_by(func.date(models.EnrollmentApplication.created_at)).all()
        enroll_by_date: Dict[str, int] = {str(r[0]): int(r[1]) for r in enroll_rows}

        # 5. Governance: reuse full-period average already computed in base_bundle_by_kg
        avg_gov = round(
            sum(float(b.get("governance_score", 0.0)) for b in base_bundle_by_kg.values())
            / max(kindergarten_count, 1),
            2,
        )

        att_points: List[TrendDataPoint] = []
        inc_points: List[TrendDataPoint] = []
        enroll_points: List[TrendDataPoint] = []
        gov_points: List[TrendDataPoint] = []

        for w_start, w_end in windows:
            # Jordan school week: Fri(4) + Sat(5) are closed
            w_working = sum(
                1
                for offset in range((w_end - w_start).days + 1)
                if (w_start + timedelta(days=offset)).weekday() not in (4, 5)
            )
            expected_approx = n_enrolled * w_working

            w_att = 0
            w_inc = 0
            w_enroll = 0
            d = w_start
            while d <= w_end:
                w_att += att_by_date.get(d, 0)
                w_inc += inc_by_date.get(str(d), 0)
                w_enroll += enroll_by_date.get(str(d), 0)
                d += timedelta(days=1)

            att_rate = round((w_att / expected_approx) * 100, 2) if expected_approx > 0 else 0.0
            inc_rate = round((w_inc / max(w_att, 1)) * 100, 2)

            att_points.append(TrendDataPoint(date=w_start, value=att_rate))
            inc_points.append(TrendDataPoint(date=w_start, value=inc_rate))
            enroll_points.append(TrendDataPoint(date=w_start, value=float(w_enroll)))
            gov_points.append(TrendDataPoint(date=w_start, value=avg_gov))

        return att_points, inc_points, enroll_points, gov_points

    # Build student distribution by birth year (calendar year)
    # Age constraints: MIN_CHILD_AGE_DAYS (1 day) to MAX_CHILD_AGE_MONTHS (4 years 8 months)
    today_date = _today_jordan()
    bounds = get_child_age_bounds(today_date)

    # Calculate valid birth date range
    max_birth_date = bounds.max_date  # Youngest allowed
    min_birth_date = bounds.min_date  # Oldest allowed

    student_distribution_queries = db.query(
        func.strftime('%Y', models.Child.date_of_birth).label('birth_year'),
        func.count(models.Child.id).label('count'),
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.Child.id,
    ).filter(
        models.EnrollmentApplication.kindergarten_id.in_(target_kindergarten_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.Child.date_of_birth >= min_birth_date,
        models.Child.date_of_birth <= max_birth_date,
    ).group_by(
        func.strftime('%Y', models.Child.date_of_birth)
    ).order_by(
        func.strftime('%Y', models.Child.date_of_birth).desc()
    )
    student_distribution_results = student_distribution_queries.all()
    if not student_distribution_results:
        # Fallback with empty years
        current_year = today_date.year
        student_distribution_items = [
            StudentDistributionItem(label=f"{translator('مواليد')} {year}", value=0)
            for year in range(current_year, current_year - 5, -1)
        ]
    else:
        student_distribution_items = [
            StudentDistributionItem(label=f"{translator('مواليد')} {birth_year}", value=count)
            for birth_year, count in student_distribution_results
        ]

    def _build_governance_rankings(limit: int = 5) -> Tuple[List[TopBottomPerformer], List[TopBottomPerformer]]:
        enriched = []
        for kg in kindergarten_records:
            score = float(base_bundle_by_kg.get(kg.id, {}).get("governance_score", 0.0))
            enriched.append(
                {
                    "kg": kg,
                    "score": round(score, 2),
                }
            )
        sorted_desc = sorted(
            enriched,
            key=lambda item: (-item["score"], item["kg"].id),
        )
        sorted_asc = sorted(
            enriched,
            key=lambda item: (item["score"], item["kg"].id),
        )

        def _unique(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            seen_ids = set()
            deduped: List[Dict[str, Any]] = []
            for entry in items:
                kg_id = entry["kg"].id
                if kg_id in seen_ids:
                    continue
                seen_ids.add(kg_id)
                deduped.append(entry)
            return deduped

        def build_list(items: List[Dict[str, Any]]) -> List[TopBottomPerformer]:
            performers = []
            for rank_idx, entry in enumerate(_unique(items)[:limit], start=1):
                kg = entry["kg"]
                name = kg.name_ar if locale == "ar" else (kg.name_en or kg.name_ar)
                performers.append(
                    TopBottomPerformer(
                        id=kg.id,
                        name=name,
                        value=entry["score"],
                        rank=rank_idx,
                        governorate=kg.governorate,
                    )
                )
            return performers

        return build_list(sorted_desc), build_list(sorted_asc)

    top_performers, low_performers = _build_governance_rankings()

    selected_governorate_value = selected_governorate
    if not selected_governorate_value and single_kindergarten_id:
        fallback_kg = next(
            (kg for kg in kindergarten_records if kg.id == single_kindergarten_id),
            None,
        )
        if fallback_kg and fallback_kg.governorate:
            selected_governorate_value = fallback_kg.governorate
    alerts: List[AlertsSummary] = []
    today = _today_jordan()
    for kg in kindergarten_records:
        if kg.license_valid_until:
            if kg.license_valid_until < today:
                alerts.append(
                    AlertsSummary(
                        type="REGULATORY",
                        message=f"{kg.name_ar or translator('Kindergarten')} {translator('license expired on')} {kg.license_valid_until}",
                        priority="high",
                        entity_id=kg.id,
                    )
                )
            elif kg.license_valid_until <= today + timedelta(days=30):
                alerts.append(
                    AlertsSummary(
                        type="REGULATORY",
                        message=f"{kg.name_ar or translator('Kindergarten')} {translator('license expires on')} {kg.license_valid_until}",
                        priority="medium",
                        entity_id=kg.id,
                    )
                )

    avg_incident_rate = round(totals["incident_rate"] / kindergarten_count, 2)
    if avg_incident_rate > 5.0:
        alerts.append(
            AlertsSummary(
                type="KPI",
                message=f"{translator('Average incident rate')} {avg_incident_rate}/1K {translator('exceeds threshold')}",
                priority="medium",
            )
        )

    attendance_trend, incidents_trend, enrollment_trend, gcei_trend = _bulk_build_all_trends()

    selected_city_value = selected_city
    selected_area_value = selected_area
    if single_kindergarten_id:
        fallback_kg = next((kg for kg in kindergarten_records if kg.id == single_kindergarten_id), None)
        if fallback_kg:
            if not selected_governorate_value and fallback_kg.governorate:
                selected_governorate_value = fallback_kg.governorate
            if not selected_city_value and fallback_kg.district:
                selected_city_value = fallback_kg.district
            if not selected_area_value and fallback_kg.area:
                selected_area_value = fallback_kg.area

    response = KPIDashboardResponse(
        period_start=period_start,
        period_end=period_end,
        kindergarten_id=single_kindergarten_id,
        governorate=selected_governorate_value,
        district=selected_city_value,
        area=selected_area_value,
        dimension_type=normalized_dimension_type,
        dimension_id=dimension_id,
        overall_gcei=_create_card(
            round(totals["gce_score"] / kindergarten_count, 2),
            "governance_score",
            "%",
            True,
            "governance_score",
        ),
        attendance_rate=_create_card(
            round(totals["attendance_rate"] / kindergarten_count, 2),
            "attendance_rate",
            "%",
            True,
            "attendance_rate",
        ),
        ratio_compliance=_create_card(
            round(totals["ratio_compliance"] / kindergarten_count, 2),
            "ratio_compliance",
            "%",
            True,
            "ratio_compliance",
        ),
        training_completion_rate=_create_card(
            round(totals["training_completion_rate"] / kindergarten_count, 2),
            "training_completion_rate",
            "%",
            True,
            "training_completion_rate",
        ),
        report_submission_rate=_create_card(
            round(totals["report_submission_rate"] / kindergarten_count, 2),
            "report_submission_rate",
            "%",
            True,
            "report_submission_rate",
        ),
        incident_rate=_create_card(
            avg_incident_rate,
            "incident_rate",
            translator("per 1,000 child-days"),
            False,
            "incident_rate",
        ),
        serious_incident_rate=_create_card(
            round(totals["serious_incident_rate"] / kindergarten_count, 2),
            "serious_incident_rate",
            translator("per 1,000 child-days"),
            False,
            "serious_incident_rate",
        ),
        incident_followup_sla=_create_card(
            round(totals["incident_followup_sla"] / kindergarten_count, 2),
            "incident_followup_sla",
            "%",
            True,
            "incident_followup_sla",
        ),
        chronic_absence_rate=_create_card(
            round(totals["chronic_absence_rate"] / kindergarten_count, 2),
            "chronic_absence_rate",
            "%",
            True,
            "chronic_absence_rate",
        ),
        capacity_utilization_rate=_create_card(
            round(totals["capacity_utilization_rate"] / kindergarten_count, 2),
            "capacity_utilization_rate",
            "%",
            True,
            "capacity_utilization_rate",
        ),
        active_enrollments=KPICardData(value=total_active_enrollments, unit=translator("children"), has_data=True, data_coverage=100.0),
        new_enrollments=KPICardData(value=totals["new_enrollments"], unit=translator("children"), has_data=True, data_coverage=100.0),
        student_distribution=student_distribution_items,
        top_performers_by_gcei=top_performers,
        low_performers_by_gcei=low_performers,
        attendance_trend=attendance_trend,
        incidents_trend=incidents_trend,
        enrollment_trend=enrollment_trend,
        gcei_trend=gcei_trend,
        alerts=alerts,
    )
    
    # Cache the response for 4 hours
    dashboard_cache.set(cache_key, response.model_dump(mode="json"), ttl_seconds=14400)
    
    return response


@router.get("/kpi/filters", response_model=KpiFiltersResponse)
def get_kpi_filters(
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_or_manager)
):
    """
    Get filter options for KPI dashboard.
    Returns unique kindergartens and governorates with localization support.
    For managers, only returns their assigned kindergarten.
    """
    # Get unique kindergartens
    kindergartens_query = db.query(
        models.Kindergarten.id,
        models.Kindergarten.name_ar,
        models.Kindergarten.name_en
    ).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).distinct()

    # For managers, only show their assigned kindergarten
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id:
            kindergartens_query = kindergartens_query.filter(
                models.Kindergarten.id == current_user.kindergarten_id
            )
        else:
            # Manager without assigned kindergarten sees nothing
            kindergartens_query = kindergartens_query.filter(models.Kindergarten.id == -1)

    kindergartens = []
    for kg in kindergartens_query:
        name = kg.name_ar if locale == "ar" else (kg.name_en or kg.name_ar)
        kindergartens.append(FilterOption(id=kg.id, name=name))

    # Get governorates from canonical source
    from services.jordan_locations import get_all_governorates
    governorates = []
    for i, g in enumerate(get_all_governorates()):
        name = g["name_ar"] if locale == "ar" else g["name_en"]
        governorates.append(FilterOption(id=g["key"], name=name))

    active_scope_query = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id:
            active_scope_query = active_scope_query.filter(
                models.Kindergarten.id == current_user.kindergarten_id
            )
        else:
            active_scope_query = active_scope_query.filter(models.Kindergarten.id == -1)

    scoped_kindergartens = active_scope_query.all()
    unique_cities = sorted({kg.district for kg in scoped_kindergartens if kg.district})
    unique_areas = sorted({kg.area for kg in scoped_kindergartens if kg.area})
    cities = [FilterOption(id=i + 1, name=city_name) for i, city_name in enumerate(unique_cities)]
    areas = [FilterOption(id=i + 1, name=area_name) for i, area_name in enumerate(unique_areas)]

    dimension_types = [
        FilterOption(id=1, name=models.AnalyticsDimensionType.NETWORK.value),
        FilterOption(id=2, name=models.AnalyticsDimensionType.GOVERNORATE.value),
        FilterOption(id=3, name=models.AnalyticsDimensionType.DISTRICT.value),
        FilterOption(id=4, name=models.AnalyticsDimensionType.AREA.value),
        FilterOption(id=5, name=models.AnalyticsDimensionType.KINDERGARTEN.value),
    ]

    return KpiFiltersResponse(
        kindergartens=kindergartens,
        governorates=governorates,
        cities=cities,
        areas=areas,
        dimension_types=dimension_types,
    )


@router.get("/kpi/manager/dashboard", response_model=KPIDashboardResponse)
def get_manager_kpi_dashboard(
    period_start: Optional[date] = Query(None, description="Start date for KPI calculation (defaults to 30 days ago)"),
    period_end: Optional[date] = Query(None, description="End date for KPI calculation (defaults to today)"),
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_or_manager)
):
    """
    Manager KPI dashboard (strictly scoped to manager's assigned kindergarten).
    Delegates to consolidated dashboard endpoint for consistent formulas and quality metadata.
    """
    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=30)

    if not current_user.kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager must be assigned to a kindergarten"
        )

    requested_days = (period_end - period_start).days
    granularity = "daily" if requested_days <= 92 else "weekly"

    return get_consolidated_kpi_dashboard_data(
        kindergarten_ids=[current_user.kindergarten_id],
        governorate=None,
        city=None,
        area=None,
        dimension_type=models.AnalyticsDimensionType.KINDERGARTEN.value,
        dimension_id=str(current_user.kindergarten_id),
        period_start=period_start,
        period_end=period_end,
        granularity=granularity,
        locale=locale,
        current_user=current_user,
        db=db,
    )


@router.get("/manager/dashboard/enhanced", response_model=EnhancedKPIDashboardResponse)
def get_enhanced_manager_kpi_dashboard(
    period_start: Optional[date] = Query(None, description="Start date for KPI calculation (defaults to 30 days ago)"),
    period_end: Optional[date] = Query(None, description="End date for KPI calculation (defaults to today)"),
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_or_manager)
):
    """
    Get enhanced KPI dashboard data for a specific kindergarten (Manager access).
    Includes comprehensive KPI definitions, explanations, thresholds, and action items.
    """
    translator = setup_translator(locale)
    
    # Set default date range if not provided (last 30 days)
    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=30)

    if not current_user.kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager must be assigned to a kindergarten"
        )

    # Force filtering to manager's kindergarten only
    single_kindergarten_id = current_user.kindergarten_id

    # Get kindergarten info
    kg = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == single_kindergarten_id
    ).first()

    if not kg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kindergarten not found"
        )

    period_days = (period_end - period_start).days + 1
    last_updated = datetime.now(_JORDAN_TZ)

    # Compute all KPIs in one pass via bundle (authoritative path)
    bundle = KPIService.compute_kpi_bundle(db, single_kindergarten_id, period_start, period_end)
    prev_start, prev_end = KPIService._compute_previous_period(period_start, period_end)
    prev_bundle = KPIService.compute_kpi_bundle(db, single_kindergarten_id, prev_start, prev_end)

    nums = bundle.get("numerators", {})
    dens = bundle.get("denominators", {})
    p_nums = prev_bundle.get("numerators", {})
    p_dens = prev_bundle.get("denominators", {})

    def _prev_rate(key: str) -> Optional[float]:
        pd = p_dens.get(key)
        pn = p_nums.get(key)
        if pd and pd > 0 and pn is not None:
            return round(pn / pd * 100, 2)
        return prev_bundle.get(key)

    gce_score = bundle.get("governance_score", 0.0)
    attendance_rate = bundle.get("attendance_rate", 0.0)
    ratio_compliance = bundle.get("ratio_compliance", 0.0)
    incident_rate = bundle.get("incident_rate", 0.0)
    serious_incident_rate = bundle.get("serious_incident_rate", 0.0)
    incident_followup_sla = bundle.get("incident_followup_sla", 0.0)
    chronic_absence_rate = bundle.get("chronic_absence_rate", 0.0)
    capacity_utilization_rate = bundle.get("capacity_utilization_rate", 0.0)
    training_completion_rate = bundle.get("training_completion_rate", 0.0)
    report_submission_rate = bundle.get("report_submission_rate", 0.0)

    # Create enhanced KPI cards — numerator/denominator/previous_value all wired up
    overall_gcei_card = KPIService.create_enhanced_kpi_card(
        "overall_gcei", gce_score, "%", last_updated, period_days,
        previous_value=prev_bundle.get("governance_score"),
    )

    attendance_rate_card = KPIService.create_enhanced_kpi_card(
        "attendance_rate", attendance_rate, "%", last_updated, period_days,
        numerator=nums.get("attendance_rate"), denominator=dens.get("attendance_rate"),
        has_data=bundle.get("quality", {}).get("attendance_rate", {}).get("has_data", True),
        data_coverage=bundle.get("quality", {}).get("attendance_rate", {}).get("coverage_pct"),
        previous_value=_prev_rate("attendance_rate"),
    )

    ratio_compliance_card = KPIService.create_enhanced_kpi_card(
        "ratio_compliance", ratio_compliance, "%", last_updated, period_days,
        numerator=nums.get("ratio_compliance"), denominator=dens.get("ratio_compliance"),
        has_data=bundle.get("quality", {}).get("ratio_compliance", {}).get("has_data", True),
        previous_value=_prev_rate("ratio_compliance"),
    )

    incident_rate_card = KPIService.create_enhanced_kpi_card(
        "incident_rate", incident_rate, translator("per 1,000 child-days"), last_updated, period_days,
        numerator=nums.get("incident_rate"), denominator=dens.get("incident_rate"),
        has_data=bundle.get("quality", {}).get("incident_rate", {}).get("has_data", True),
        previous_value=_prev_rate("incident_rate"),
    )

    serious_incident_rate_card = KPIService.create_enhanced_kpi_card(
        "serious_incident_rate", serious_incident_rate, translator("per 1,000 child-days"), last_updated, period_days,
        numerator=nums.get("serious_incident_rate"), denominator=dens.get("serious_incident_rate"),
        has_data=bundle.get("quality", {}).get("incident_rate", {}).get("has_data", True),
        previous_value=_prev_rate("serious_incident_rate"),
    )

    incident_followup_sla_card = KPIService.create_enhanced_kpi_card(
        "incident_followup_sla", incident_followup_sla, "%", last_updated, period_days,
        numerator=nums.get("incident_followup_sla"), denominator=dens.get("incident_followup_sla"),
        has_data=dens.get("incident_followup_sla", 0) > 0,
        previous_value=_prev_rate("incident_followup_sla"),
    )

    chronic_absence_rate_card = KPIService.create_enhanced_kpi_card(
        "chronic_absence_rate", chronic_absence_rate, "%", last_updated, period_days,
        numerator=nums.get("chronic_absence_rate"), denominator=dens.get("chronic_absence_rate"),
        has_data=dens.get("chronic_absence_rate", 0) > 0,
        previous_value=_prev_rate("chronic_absence_rate"),
    )

    capacity_utilization_rate_card = KPIService.create_enhanced_kpi_card(
        "capacity_utilization_rate", capacity_utilization_rate, "%", last_updated, period_days,
        numerator=nums.get("capacity_utilization_rate"), denominator=dens.get("capacity_utilization_rate"),
        has_data=dens.get("capacity_utilization_rate", 0) > 0,
        previous_value=_prev_rate("capacity_utilization_rate"),
    )

    training_completion_rate_card = KPIService.create_enhanced_kpi_card(
        "training_completion_rate", training_completion_rate, "%", last_updated, period_days,
        numerator=nums.get("training_completion_rate"), denominator=dens.get("training_completion_rate"),
        has_data=dens.get("training_completion_rate", 0) > 0,
        previous_value=_prev_rate("training_completion_rate"),
    )

    report_submission_rate_card = KPIService.create_enhanced_kpi_card(
        "report_submission_rate", report_submission_rate, "%", last_updated, period_days,
        numerator=nums.get("report_submission_rate"), denominator=dens.get("report_submission_rate"),
        has_data=dens.get("report_submission_rate", 0) > 0,
        previous_value=_prev_rate("report_submission_rate"),
    )

    excused_absence_rate_card = KPIService.create_enhanced_kpi_card(
        "excused_absence_rate", bundle.get("excused_absence_rate", 0.0), "%", last_updated, period_days,
        numerator=nums.get("excused_absence_rate"), denominator=dens.get("excused_absence_rate"),
        has_data=dens.get("excused_absence_rate", 0) > 0,
        previous_value=_prev_rate("excused_absence_rate"),
    )

    # Build alerts
    alerts = []
    today = _today_jordan()
    if kg.license_valid_until:
        if kg.license_valid_until < today:
            alerts.append(
                AlertsSummary(
                    type="REGULATORY",
                    message=f"{kg.name_ar or 'الحضانة'} رخصتها منتهية الصلاحية منذ {kg.license_valid_until}",
                    priority="high",
                    entity_id=kg.id,
                )
            )
        elif kg.license_valid_until <= today + timedelta(days=30):
            alerts.append(
                AlertsSummary(
                    type="REGULATORY",
                    message=f"{kg.name_ar or 'الحضانة'} رخصتها تنتهي في {kg.license_valid_until}",
                    priority="medium",
                    entity_id=kg.id,
                )
            )

    # Check KPI thresholds for alerts
    if incident_rate > 5.0:
        alerts.append(
            AlertsSummary(
                type="KPI",
                message=f"معدل الحوادث {incident_rate}% يتجاوز الحد المسموح",
                priority="medium",
            )
        )

    if chronic_absence_rate > 10.0:
        alerts.append(
            AlertsSummary(
                type="KPI",
                message=f"معدل الغياب المزمن {chronic_absence_rate}% مرتفع جداً",
                priority="high",
            )
        )

    # Determine data freshness
    data_freshness = "fresh"  # Can be enhanced with actual timestamp checks

    return EnhancedKPIDashboardResponse(
        kindergarten_id=single_kindergarten_id,
        kindergarten_name=kg.name_ar or kg.name_en,
        period_start=period_start,
        period_end=period_end,
        overall_gcei=overall_gcei_card,
        attendance_rate=attendance_rate_card,
        ratio_compliance=ratio_compliance_card,
        incident_rate=incident_rate_card,
        serious_incident_rate=serious_incident_rate_card,
        incident_followup_sla=incident_followup_sla_card,
        chronic_absence_rate=chronic_absence_rate_card,
        capacity_utilization_rate=capacity_utilization_rate_card,
        training_completion_rate=training_completion_rate_card,
        report_submission_rate=report_submission_rate_card,
        excused_absence_rate=excused_absence_rate_card,
        alerts=alerts,
        last_updated=last_updated,
        data_freshness=data_freshness
    )


@router.get("/manager/kpi", response_model=EnhancedKPIDashboardResponse)
def get_manager_kpi_alias(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_or_manager)
):
    """Alias for /manager/dashboard/enhanced — identical schema and auth."""
    return get_enhanced_manager_kpi_dashboard(period_start, period_end, locale, db, current_user)


@router.get("/kpi/bundle/{kindergarten_id}")
def get_kpi_bundle(
    kindergarten_id: int,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return the full structured KPI bundle for a single kindergarten, enriched with
    band, confidence, numerator, denominator, formula, meaning, and decision guidance
    for every KPI. This is the primary per-kindergarten KPI API for dashboards and
    external integrations.

    Managers see only their own kindergarten. Admins may specify any.
    """
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kindergarten_id:
            raise HTTPException(status_code=403, detail="You may only view your own kindergarten's KPIs.")
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        raise HTTPException(status_code=403, detail="Access denied")

    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=29)

    bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
    prev_start, prev_end = KPIService._compute_previous_period(period_start, period_end)
    prev_bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, prev_start, prev_end)

    nums = bundle.get("numerators", {})
    dens = bundle.get("denominators", {})
    quality = bundle.get("quality", {})

    def _enrich(key: str, value: float, unit: str = "%") -> dict:
        std = STANDARDS.get(key)
        denom = dens.get(key, 0)
        numer = nums.get(key)
        has_data = quality.get(key, {}).get("has_data", denom > 0 if denom else value > 0)
        cov = quality.get(key, {}).get("coverage_pct", 100.0 if has_data else 0.0)
        prev_val = prev_bundle.get(key)
        trend_dir, trend_chg = KPIService._trend_from_values(value, prev_val) if prev_val is not None else ("flat", 0.0)
        band = assign_band(key, value, has_data, compute_confidence(denom, std.min_denominator if std else 10, std.min_denominator_high if std else 30, has_data), cov)
        confidence = compute_confidence(denom, std.min_denominator if std else 10, std.min_denominator_high if std else 30, has_data)
        return {
            "value": value,
            "unit": unit,
            "numerator": numer,
            "denominator": denom if denom else None,
            "formula": std.formula_en if std else None,
            "formula_ar": std.formula_ar if std else None,
            "band": band.value,
            "confidence": confidence.value,
            "trend": trend_dir,
            "trend_change": trend_chg,
            "previous_value": prev_val,
            "meaning_en": get_band_meaning(key, band, "en"),
            "meaning_ar": get_band_meaning(key, band, "ar"),
            "decision_guidance_en": get_band_action(key, band, "en"),
            "decision_guidance_ar": get_band_action(key, band, "ar"),
            "threshold_source": get_threshold_source_dict(key),
            "has_data": has_data,
            "data_coverage_pct": cov,
            "data_quality_reason": quality.get(key, {}).get("reason"),
        }

    kpis = {
        "attendance_rate": _enrich("attendance_rate", bundle.get("attendance_rate", 0.0)),
        "excused_absence_rate": _enrich("excused_absence_rate", bundle.get("excused_absence_rate", 0.0)),
        "chronic_absence_rate": _enrich("chronic_absence_rate", bundle.get("chronic_absence_rate", 0.0)),
        "incident_rate": _enrich("incident_rate", bundle.get("incident_rate", 0.0), "per 1,000 child-days"),
        "incident_rate_per_100": _enrich("incident_rate", bundle.get("incident_rate_per_100", 0.0), "per 100 child-days"),
        "serious_incident_rate": _enrich("serious_incident_rate", bundle.get("serious_incident_rate", 0.0), "per 1,000 child-days"),
        "serious_incident_rate_per_100": _enrich("serious_incident_rate", bundle.get("serious_incident_rate_per_100", 0.0), "per 100 child-days"),
        "incident_followup_sla": _enrich("incident_followup_sla", bundle.get("incident_followup_sla", 0.0)),
        "ratio_compliance": _enrich("ratio_compliance", bundle.get("ratio_compliance", 0.0)),
        "training_completion_rate": _enrich("training_completion_rate", bundle.get("training_completion_rate", 0.0)),
        "report_submission_rate": _enrich("report_submission_rate", bundle.get("report_submission_rate", 0.0)),
        "checklist_compliance": _enrich("checklist_compliance", bundle.get("checklist_compliance", 0.0)),
        "capacity_utilization_rate": _enrich("capacity_utilization_rate", bundle.get("capacity_utilization_rate", 0.0)),
        "gqi_score": _enrich("gqi_score", bundle.get("gqi_score", 0.0)),
        "cei_score": _enrich("cei_score", bundle.get("cei_score", 0.0)),
        "overall_gcei": _enrich("overall_gcei", bundle.get("governance_score", 0.0)),
    }

    return {
        "kindergarten_id": kindergarten_id,
        "kindergarten_name_ar": kg.name_ar,
        "kindergarten_name_en": kg.name_en,
        "governorate": kg.governorate,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "previous_period_start": prev_start.isoformat(),
        "previous_period_end": prev_end.isoformat(),
        "overall_band": bundle.get("governance_band", "GRAY"),
        "override_rules_triggered": bundle.get("override_rules_triggered", []),
        "kpis": kpis,
    }


@router.get("/kpi/standards")
def get_kpi_standards(
    current_user: models.User = Depends(require_admin_or_manager),
):
    """
    Return the full KPI standards registry: formulas, numerators, denominators,
    thresholds with source metadata, min denominator rules, and hard override rules.
    """
    return {
        "standards": list_all_standards(),
        "hard_override_rules": list_hard_override_rules(),
        "min_coverage_for_rating_pct": MIN_COVERAGE_FOR_RATING,
    }


@router.get("/kpi/definitions")
def get_kpi_definitions(
    locale: str = Query("ar", description="Language locale ('ar' or 'en')"),
    current_user: models.User = Depends(require_admin_or_manager),
):
    """Return KPI definitions — names, formulas, and explanations — in the requested locale."""
    result = []
    for key, defn in KPI_DEFINITIONS.items():
        std = STANDARDS.get(key)
        entry = {
            "kpi_key": key,
            "name": defn["name_ar"] if locale == "ar" else defn["name_en"],
            "name_ar": defn["name_ar"],
            "name_en": defn["name_en"],
            "description": defn.get("description_ar" if locale == "ar" else "description_en", ""),
            "formula": defn.get("formula_ar" if locale == "ar" else "formula_en", ""),
        }
        if std:
            entry["unit"] = std.unit
            entry["category"] = std.category
            entry["direction"] = std.threshold.direction.value
            entry["threshold_source"] = get_threshold_source_dict(key)
        result.append(entry)
    return {"definitions": result, "count": len(result)}


@router.get("/kpi/thresholds")
def get_kpi_thresholds(
    current_user: models.User = Depends(require_admin_or_manager),
):
    """Return all KPI thresholds with source metadata and hard override rules."""
    thresholds = []
    for key, std in STANDARDS.items():
        t = std.threshold
        thresholds.append({
            "kpi_key": key,
            "name_en": std.name_en,
            "name_ar": std.name_ar,
            "unit": std.unit,
            "direction": t.direction.value,
            "green": {"min": t.green[0], "max": t.green[1], "label_en": t.green_label_en, "label_ar": t.green_label_ar},
            "amber": {"min": t.amber[0], "max": t.amber[1], "label_en": t.amber_label_en, "label_ar": t.amber_label_ar},
            "red": {"min": t.red[0], "max": t.red[1], "label_en": t.red_label_en, "label_ar": t.red_label_ar},
            "source": get_threshold_source_dict(key),
            "min_denominator": std.min_denominator,
            "min_denominator_high": std.min_denominator_high,
        })
    return {"thresholds": thresholds, "hard_override_rules": list_hard_override_rules()}


@router.get("/kpi/levels/country")
def get_kpi_country_level(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Country-wide KPI aggregation (Admin only)."""
    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=29)

    kindergartens = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).all()

    if not kindergartens:
        return {"level": "country", "country": "Jordan", "kindergarten_count": 0, "kpis": {}}

    all_bundles = []
    for kg in kindergartens:
        try:
            bundle = KPIService.compute_kpi_bundle(db, kg.id, period_start, period_end)
            all_bundles.append(bundle)
        except Exception:
            continue

    count = len(all_bundles)
    if count == 0:
        return {"level": "country", "country": "Jordan", "kindergarten_count": 0, "kpis": {}}

    def _avg(key: str) -> float:
        vals = [b.get(key, 0.0) or 0.0 for b in all_bundles]
        return round(sum(vals) / count, 2)

    green_count = sum(1 for b in all_bundles if b.get("governance_band") == "GREEN")
    amber_count = sum(1 for b in all_bundles if b.get("governance_band") == "AMBER")
    red_count = sum(1 for b in all_bundles if b.get("governance_band") == "RED")

    return {
        "level": "country",
        "country": "Jordan",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_count": count,
        "band_distribution": {"green": green_count, "amber": amber_count, "red": red_count},
        "kpis": {
            "attendance_rate": _avg("attendance_rate"),
            "excused_absence_rate": _avg("excused_absence_rate"),
            "chronic_absence_rate": _avg("chronic_absence_rate"),
            "incident_rate": _avg("incident_rate"),
            "serious_incident_rate": _avg("serious_incident_rate"),
            "incident_followup_sla": _avg("incident_followup_sla"),
            "ratio_compliance": _avg("ratio_compliance"),
            "training_completion_rate": _avg("training_completion_rate"),
            "report_submission_rate": _avg("report_submission_rate"),
            "checklist_compliance": _avg("checklist_compliance"),
            "capacity_utilization_rate": _avg("capacity_utilization_rate"),
            "gqi_score": _avg("gqi_score"),
            "cei_score": _avg("cei_score"),
            "governance_score": _avg("governance_score"),
        },
    }


@router.get("/kpi/levels/governorates")
def get_kpi_governorate_level(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """KPI aggregation per governorate (Admin only)."""
    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=29)

    kindergartens = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).all()

    governorate_bundles: Dict[str, List[Dict[str, Any]]] = {}
    for kg in kindergartens:
        gov = kg.governorate or "Unknown"
        try:
            bundle = KPIService.compute_kpi_bundle(db, kg.id, period_start, period_end)
            governorate_bundles.setdefault(gov, []).append(bundle)
        except Exception:
            continue

    result = []
    kpi_keys = [
        "attendance_rate", "excused_absence_rate", "chronic_absence_rate",
        "incident_rate", "serious_incident_rate",
        "incident_followup_sla", "ratio_compliance", "training_completion_rate",
        "report_submission_rate", "checklist_compliance", "capacity_utilization_rate",
        "gqi_score", "cei_score", "governance_score",
    ]
    for gov, bundles in sorted(governorate_bundles.items()):
        n = len(bundles)
        kpis = {
            k: round(sum(b.get(k, 0.0) or 0.0 for b in bundles) / n, 2)
            for k in kpi_keys
        }
        band_dist = {
            "green": sum(1 for b in bundles if b.get("governance_band") == "GREEN"),
            "amber": sum(1 for b in bundles if b.get("governance_band") == "AMBER"),
            "red": sum(1 for b in bundles if b.get("governance_band") == "RED"),
        }
        result.append({
            "governorate": gov,
            "kindergarten_count": n,
            "band_distribution": band_dist,
            "kpis": kpis,
        })

    return {
        "level": "governorate",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "governorates": result,
    }


@router.get("/kpi/alerts")
def get_kpi_alerts(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return actionable KPI alerts for the authenticated user's scope.
    Managers see their own kindergarten; Admins see all or a specific one.
    """
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Access denied")

    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=29)

    if current_user.role == models.UserRole.MANAGER:
        target_kg_id = current_user.kindergarten_id
        if not target_kg_id:
            return {"alerts": []}
        kg_query = db.query(models.Kindergarten).filter(models.Kindergarten.id == target_kg_id)
    elif current_user.role == models.UserRole.ADMIN:
        if kindergarten_id:
            kg_query = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id)
        else:
            kg_query = db.query(models.Kindergarten).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            )
    else:
        kg_query = None

    kindergartens = kg_query.all() if kg_query is not None else []

    # This scans every kindergarten in scope with compute_kpi_bundle (the same
    # multi-query-per-kindergarten aggregator used by governance scoring) —
    # for an admin with no kindergarten filter that's all active kindergartens
    # (629 in this dataset), which previously took 15s+ and had no caching at
    # all, unlike the sibling dashboard-data endpoint. Reuse that exact cache
    # pattern (60s TTL, bypassed under TESTING) instead of rewriting the
    # underlying per-kindergarten computation.
    #
    # Scope key must NOT be current_user.role alone: a MANAGER's actual scope
    # is their own kindergarten_id, which differs per manager and is never
    # reflected in the `kindergarten_id` query param (managers don't pass it —
    # the code above resolves their scope from current_user.kindergarten_id
    # instead). Keying on role alone would let two different managers share
    # one cache entry within the same 60s window, each silently seeing the
    # other's kindergarten's alerts. ADMINs share a scope key since every
    # admin sees the identical (optionally kindergarten_id-filtered) view.
    scope_key = "ADMIN" if current_user.role == models.UserRole.ADMIN else f"user:{current_user.id}"
    cache_key = (
        f"kpi:alerts:{period_start}:{period_end}:"
        f"{kindergarten_id or 'all'}:{scope_key}"
    )
    if not getattr(settings, "TESTING", False):
        try:
            cached = dashboard_cache.get(cache_key)
        except Exception:
            cached = None
        if cached is not None:
            return cached

    alerts = []
    today = _today_jordan()

    for kg in kindergartens:
        kg_id = kg.id
        kg_name = kg.name_ar or kg.name_en or f"KG #{kg_id}"

        # License expiry
        if kg.license_valid_until:
            if kg.license_valid_until < today:
                alerts.append({
                    "type": "LICENSE_EXPIRED", "priority": "critical",
                    "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                    "message_ar": f"ترخيص {kg_name} منتهٍ منذ {kg.license_valid_until}",
                    "message_en": f"{kg_name} license expired on {kg.license_valid_until}",
                    "action_ar": "تجديد الترخيص فوراً",
                    "action_en": "Renew the license immediately",
                })
            elif kg.license_valid_until <= today + timedelta(days=30):
                alerts.append({
                    "type": "LICENSE_EXPIRING", "priority": "high",
                    "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                    "message_ar": f"ترخيص {kg_name} ينتهي في {kg.license_valid_until}",
                    "message_en": f"{kg_name} license expires on {kg.license_valid_until}",
                    "action_ar": "ابدأ إجراءات تجديد الترخيص",
                    "action_en": "Initiate license renewal process",
                })

        # Open critical incidents
        open_critical = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id == kg_id,
            models.Incident.severity_level == models.SeverityLevel.CRITICAL,
            models.Incident.followup_required_flag == True,
            models.Incident.closed_at.is_(None),
            models.Incident.deleted_at.is_(None),
        ).scalar() or 0
        if open_critical > 0:
            alerts.append({
                "type": "OPEN_CRITICAL_INCIDENT", "priority": "critical",
                "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                "message_ar": f"يوجد {open_critical} حادث حرج مفتوح في {kg_name}",
                "message_en": f"{open_critical} open critical incident(s) in {kg_name}",
                "action_ar": "راجع وأغلق الحوادث الحرجة المفتوحة فوراً",
                "action_en": "Review and close open critical incidents immediately",
            })

        # KPI threshold breaches
        try:
            bundle = KPIService.compute_kpi_bundle(db, kg_id, period_start, period_end)
            if bundle.get("attendance_rate", 100.0) < 70.0 and bundle["quality"]["attendance_rate"]["has_data"]:
                alerts.append({
                    "type": "LOW_ATTENDANCE", "priority": "high",
                    "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                    "value": bundle["attendance_rate"],
                    "message_ar": f"نسبة الحضور في {kg_name}: {bundle['attendance_rate']}% — أقل من الحد الأدنى 70%",
                    "message_en": f"Attendance rate at {kg_name}: {bundle['attendance_rate']}% — below 70% threshold",
                    "action_ar": "تواصل مع الأسر وراجع أسباب الغياب",
                    "action_en": "Contact families and investigate absence causes",
                })
            if bundle.get("chronic_absence_rate", 0.0) > 10.0:
                alerts.append({
                    "type": "HIGH_CHRONIC_ABSENCE", "priority": "high",
                    "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                    "value": bundle["chronic_absence_rate"],
                    "message_ar": f"معدل الغياب المزمن في {kg_name}: {bundle['chronic_absence_rate']}%",
                    "message_en": f"Chronic absence rate at {kg_name}: {bundle['chronic_absence_rate']}%",
                    "action_ar": "حدد الأطفال المتغيبين بشكل مزمن وتواصل مع أسرهم",
                    "action_en": "Identify chronically absent children and contact their families",
                })
            if bundle.get("ratio_compliance", 100.0) < 80.0 and bundle["quality"]["ratio_compliance"]["has_data"]:
                alerts.append({
                    "type": "LOW_RATIO_COMPLIANCE", "priority": "critical" if bundle["ratio_compliance"] < 60 else "high",
                    "kindergarten_id": kg_id, "kindergarten_name": kg_name,
                    "value": bundle["ratio_compliance"],
                    "message_ar": f"امتثال نسبة الموظف للأطفال في {kg_name}: {bundle['ratio_compliance']}%",
                    "message_en": f"Staff-child ratio compliance at {kg_name}: {bundle['ratio_compliance']}%",
                    "action_ar": "راجع جدولة الموظفين وضمان الغطاء الكافي",
                    "action_en": "Review staff scheduling and ensure adequate coverage",
                })
        except Exception:
            pass

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: priority_order.get(a.get("priority", "low"), 3))

    result = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "alerts": alerts,
        "total": len(alerts),
    }
    if not getattr(settings, "TESTING", False):
        try:
            dashboard_cache.set(cache_key, result, ttl_seconds=60)
        except Exception:
            pass
    return result


@router.get("/kpi/recommended-actions")
def get_kpi_recommended_actions(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return prioritized recommended actions based on current KPI status.
    Each action is tied to a specific KPI breach or data quality issue.
    """
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Access denied")

    if period_end is None:
        period_end = _today_jordan()
    if period_start is None:
        period_start = period_end - timedelta(days=29)

    if current_user.role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        kg_id = current_user.kindergarten_id
        if not kg_id:
            return {"recommended_actions": []}
    elif current_user.role == models.UserRole.ADMIN:
        kg_id = kindergarten_id
        if not kg_id:
            return {"message": "Specify kindergarten_id for action recommendations, or use /kpi/alerts for network-wide alerts."}
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    try:
        bundle = KPIService.compute_kpi_bundle(db, kg_id, period_start, period_end)
    except Exception:
        return {"recommended_actions": [], "error": "Could not compute KPI bundle"}

    actions = []

    kpi_action_map = [
        ("attendance_rate", 90.0, 70.0, True,
         "راجع أسباب غياب الأطفال وتواصل مع أسر ذوي الغياب المتكرر.",
         "Review causes of child absences and contact families of frequently absent children."),
        ("chronic_absence_rate", None, 10.0, False,
         "حدد الأطفال الغائبين بشكل مزمن وضع خطة متابعة مع الأسر.",
         "Identify chronically absent children and develop a follow-up plan with families."),
        ("ratio_compliance", 95.0, 80.0, True,
         "حسّن جدولة الموظفين لضمان الامتثال لنسب المعلم للأطفال.",
         "Improve staff scheduling to ensure staff-child ratio compliance."),
        ("incident_followup_sla", 100.0, 90.0, True,
         "راجع الحوادث المفتوحة وأغلق جميع الحوادث التي تجاوزت مهلة 48 ساعة.",
         "Review open incidents and close all that have exceeded the 48-hour SLA deadline."),
        ("report_submission_rate", 95.0, 85.0, True,
         "راجع معدلات تقديم التقارير للمشرفين وحدد سبب الانخفاض.",
         "Review supervisor report submission rates and identify the cause of any shortfall."),
        ("training_completion_rate", 90.0, 75.0, True,
         "جدوِل جلسات تدريبية للموظفين المتأخرين في إتمام الوحدات الإلزامية.",
         "Schedule training sessions for staff who have not completed mandatory modules."),
        ("checklist_compliance", 95.0, 80.0, True,
         "راجع قوائم الفحص الناقصة وتحقق من الإجراءات اليومية للمشرفين.",
         "Review missing checklists and verify supervisors are following daily procedures."),
    ]

    for kpi_key, green_thresh, amber_thresh, higher_is_better, action_ar, action_en in kpi_action_map:
        val = bundle.get(kpi_key)
        if val is None:
            continue
        quality = bundle.get("quality", {}).get(kpi_key, {})
        if not quality.get("has_data", False):
            actions.append({
                "kpi_key": kpi_key,
                "priority": "medium",
                "type": "data_quality",
                "action_ar": f"أضف بيانات {STANDARDS[kpi_key].name_ar if kpi_key in STANDARDS else kpi_key} لتفعيل هذا المؤشر.",
                "action_en": f"Add {STANDARDS[kpi_key].name_en if kpi_key in STANDARDS else kpi_key} data to activate this indicator.",
                "value": None,
                "band": "gray",
            })
            continue

        if higher_is_better:
            if amber_thresh is not None and val < amber_thresh:
                priority = "critical" if (green_thresh and val < green_thresh - 20) else "high"
                actions.append({"kpi_key": kpi_key, "priority": priority, "type": "kpi_breach",
                                 "action_ar": action_ar, "action_en": action_en,
                                 "value": val, "band": "red" if val < amber_thresh else "amber"})
            elif green_thresh is not None and val < green_thresh:
                actions.append({"kpi_key": kpi_key, "priority": "medium", "type": "kpi_watch",
                                 "action_ar": action_ar, "action_en": action_en,
                                 "value": val, "band": "amber"})
        else:
            if amber_thresh is not None and val > amber_thresh:
                actions.append({"kpi_key": kpi_key, "priority": "high", "type": "kpi_breach",
                                 "action_ar": action_ar, "action_en": action_en,
                                 "value": val, "band": "red"})
            elif green_thresh is not None and val > green_thresh:
                actions.append({"kpi_key": kpi_key, "priority": "medium", "type": "kpi_watch",
                                 "action_ar": action_ar, "action_en": action_en,
                                 "value": val, "band": "amber"})

    # Add override-rule triggered actions
    for rule_id in bundle.get("override_rules_triggered", []):
        rule = next((r for r in HARD_OVERRIDE_RULES if r.rule_id == rule_id), None)
        if rule:
            actions.insert(0, {
                "kpi_key": "hard_override",
                "rule_id": rule_id,
                "priority": "critical",
                "type": "hard_override",
                "action_ar": rule.description_ar,
                "action_en": rule.description_en,
                "band": rule.forces_band.value,
            })

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions.sort(key=lambda a: priority_order.get(a.get("priority", "low"), 3))

    return {
        "kindergarten_id": kg_id,
        "kindergarten_name": kg.name_ar or kg.name_en,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "recommended_actions": actions,
        "total": len(actions),
    }


@router.get("/kpi/network-summary")
def get_kpi_network_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """KPI network summary across all active kindergartens (admin only)"""
    validators.validate_admin_role(current_user)

    if end_date is None:
        end_date = _today_jordan()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    kg_query = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if governorate:
        kg_query = kg_query.filter(models.Kindergarten.governorate == governorate)
    kindergartens = kg_query.all()

    per_kg = []
    attendance_rates = []
    incident_rates = []
    ratio_compliances = []
    gqi_scores = []

    for kg in kindergartens:
        ar = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
        ir = KPIService.compute_incident_rate(db, kg.id, start_date, end_date)
        rc = KPIService.compute_ratio_compliance(db, kg.id, start_date, end_date)
        gs, band = KPIService.compute_governance_score(db, kg.id, start_date, end_date)

        attendance_rates.append(ar)
        incident_rates.append(ir)
        ratio_compliances.append(rc)
        gqi_scores.append(gs)

        per_kg.append({
            "kindergarten_id": kg.id,
            "kindergarten_name": kg.name_ar or kg.name_en,
            "governorate": kg.governorate,
            "attendance_rate": ar,
            "incident_rate": ir,
            "ratio_compliance": rc,
            "governance_score": gs,
            "governance_band": band,
        })

    def _avg(lst: list) -> float:
        # A kindergarten with no data for the period yields None from the KPI
        # computers. Exclude those rather than coercing them to 0.0, which would
        # silently drag the network average down.
        vals = [v for v in lst if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "kindergarten_count": len(kindergartens),
        "avg_attendance_rate": _avg(attendance_rates),
        "avg_incident_rate": _avg(incident_rates),
        "avg_ratio_compliance": _avg(ratio_compliances),
        "avg_gqi_score": _avg(gqi_scores),
        "per_kindergarten": per_kg,
    }
