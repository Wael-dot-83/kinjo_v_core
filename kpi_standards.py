"""
KPI Standards, Thresholds, and Source Metadata Registry.

This is the single source of truth for all KPI threshold definitions,
source metadata, minimum denominator rules, confidence levels, and
hard override rules.

Design principles:
- Never scatter thresholds in UI components or multiple services.
- Every threshold must have a source, jurisdiction, and validation status.
- Standards are configurable without code changes via the KPITarget model.
- Hard override rules are documented and centrally enforced.
- Missing data is never treated as good performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BandColor(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    GRAY = "gray"          # No data / not applicable
    INSUFFICIENT = "insufficient_data"


class ConfidenceLevel(str, Enum):
    HIGH = "high"         # denominator >= min_denominator, full data
    MEDIUM = "medium"     # denominator >= min_denominator / 2, partial data
    LOW = "low"           # denominator present but small sample
    INSUFFICIENT = "insufficient"  # denominator below absolute minimum


class ValidationStatus(str, Enum):
    OFFICIAL_VERIFIED = "official_verified"   # Confirmed official Jordanian or international standard
    NEEDS_VALIDATION = "needs_validation"     # Not yet confirmed from official source
    INTERNAL_POLICY = "internal_policy"       # Internal operational policy, no external mandate


class ThresholdDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ThresholdSource:
    """Source metadata for a threshold value."""
    source_name: str
    jurisdiction: str  # "Jordan", "International", "Internal", "WHO", etc.
    validation_status: ValidationStatus
    effective_date: str              # ISO date string "YYYY-MM-DD"
    source_url: Optional[str] = None
    review_date: Optional[str] = None
    notes_en: Optional[str] = None
    notes_ar: Optional[str] = None


@dataclass
class ThresholdDefinition:
    """
    Full threshold definition for one KPI.
    green/amber/red are defined as (min_inclusive, max_inclusive) tuples
    where None means unbounded.
    """
    green: tuple            # (min, max) both-inclusive; None = unbounded
    amber: tuple            # (min, max)
    red: tuple              # (min, max)
    direction: ThresholdDirection
    unit: str
    source: ThresholdSource

    # Band label texts
    green_label_en: str = "Good"
    green_label_ar: str = "جيد"
    amber_label_en: str = "Needs Attention"
    amber_label_ar: str = "يحتاج مراجعة"
    red_label_en: str = "Action Required"
    red_label_ar: str = "إجراء فوري مطلوب"
    gray_label_en: str = "No Data"
    gray_label_ar: str = "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف."

    # Meaning texts per band
    green_meaning_en: str = ""
    green_meaning_ar: str = ""
    amber_meaning_en: str = ""
    amber_meaning_ar: str = ""
    red_meaning_en: str = ""
    red_meaning_ar: str = ""

    # Decision guidance per band
    green_action_en: str = "Maintain and monitor regularly."
    green_action_ar: str = "استمر في المتابعة الدورية."
    amber_action_en: str = "Review causes and monitor closely."
    amber_action_ar: str = "راجع الأسباب وتابع عن كثب."
    red_action_en: str = "Immediate action required."
    red_action_ar: str = "إجراء فوري مطلوب."


@dataclass
class KPIStandard:
    """Full standard definition for one KPI."""
    kpi_key: str
    name_en: str
    name_ar: str
    description_en: str
    description_ar: str
    formula_en: str
    formula_ar: str
    numerator_description_en: str
    numerator_description_ar: str
    denominator_description_en: str
    denominator_description_ar: str
    unit: str
    threshold: ThresholdDefinition
    min_denominator: int            # Minimum denominator for "medium" confidence
    min_denominator_high: int       # Minimum denominator for "high" confidence
    category: str                   # "safety", "attendance", "staffing", "parent", "governance", "data_quality"
    tags: List[str] = field(default_factory=list)


@dataclass
class HardOverrideRule:
    """A rule that overrides the calculated band regardless of score."""
    rule_id: str
    description_en: str
    description_ar: str
    forces_band: BandColor
    condition_description_en: str
    condition_description_ar: str


# ---------------------------------------------------------------------------
# Source definitions (reusable)
# ---------------------------------------------------------------------------

_SRC_JORDAN_MOE = ThresholdSource(
    source_name="Jordan Ministry of Education — Early Childhood Education Standards",
    jurisdiction="Jordan",
    validation_status=ValidationStatus.NEEDS_VALIDATION,
    effective_date="2024-01-01",
    source_url=None,
    notes_en="Threshold aligned with Jordan MOE ECE operational guidelines. Requires official validation against latest circular.",
    notes_ar="العتبة متوافقة مع إرشادات وزارة التربية الأردنية. تحتاج إلى مراجعة رسمية مقابل آخر تعميم.",
)

_SRC_WHO_ECEC = ThresholdSource(
    source_name="WHO / UNICEF — Early Childhood Education & Care Quality Indicators",
    jurisdiction="International",
    validation_status=ValidationStatus.NEEDS_VALIDATION,
    effective_date="2022-01-01",
    source_url="https://www.unicef.org/early-childhood-development",
    notes_en="International benchmark. Apply with caution in Jordan context until officially validated.",
    notes_ar="معيار دولي. يُطبق بحذر في السياق الأردني حتى يتم التحقق الرسمي.",
)

_SRC_INTERNAL = ThresholdSource(
    source_name="KinJo Internal Operational Policy",
    jurisdiction="Internal",
    validation_status=ValidationStatus.INTERNAL_POLICY,
    effective_date="2024-06-01",
    notes_en="Internal operational threshold. Should be reviewed against official Jordan standards when available.",
    notes_ar="عتبة تشغيلية داخلية. يجب مراجعتها مقابل المعايير الأردنية الرسمية عند توفرها.",
)

_SRC_JORDAN_MOE_VERIFIED = ThresholdSource(
    source_name="Jordan Ministry of Education — Kindergarten Licensing Regulations",
    jurisdiction="Jordan",
    validation_status=ValidationStatus.OFFICIAL_VERIFIED,
    effective_date="2023-01-01",
    notes_en="License validity requirement is a direct legal obligation under Jordan kindergarten licensing law.",
    notes_ar="اشتراط صلاحية الترخيص التزام قانوني مباشر بموجب قانون ترخيص الحضانات الأردني.",
)


# ---------------------------------------------------------------------------
# KPI Standards Registry
# ---------------------------------------------------------------------------

STANDARDS: Dict[str, KPIStandard] = {

    # -----------------------------------------------------------------------
    # A. ATTENDANCE & CHILD WELLBEING
    # -----------------------------------------------------------------------

    "physical_attendance_rate": KPIStandard(
        kpi_key="physical_attendance_rate",
        name_en="Physical Attendance Rate",
        name_ar="نسبة الحضور الفعلي",
        description_en="Percentage of expected child-days where the child was physically present (PRESENT or LATE status). Excludes excused absences.",
        description_ar="نسبة أيام الطفل المتوقعة التي كان فيها الطفل حاضراً فعلياً (حاضر أو متأخر). لا تشمل الغياب المعذور.",
        formula_en="(PRESENT_child_days + LATE_child_days) / Expected_child_days × 100",
        formula_ar="(أيام الحضور + أيام التأخير) ÷ أيام الحضور المتوقعة × 100",
        numerator_description_en="Child-days with PRESENT or LATE attendance status",
        numerator_description_ar="أيام الأطفال بحالة حاضر أو متأخر",
        denominator_description_en="Expected child-days based on active enrollments × working days",
        denominator_description_ar="أيام الأطفال المتوقعة بناءً على التسجيلات النشطة × أيام الدوام",
        unit="%",
        threshold=ThresholdDefinition(
            green=(90.0, None),
            amber=(70.0, 89.99),
            red=(None, 69.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_JORDAN_MOE,
            green_meaning_en="Children are attending regularly. Educational continuity is well maintained.",
            green_meaning_ar="الأطفال يحضرون بانتظام. الاستمرارية التعليمية محققة.",
            amber_meaning_en="Attendance is below expected levels. Some children may be missing important learning.",
            amber_meaning_ar="الحضور دون المستوى المطلوب. قد يفوت بعض الأطفال تعلماً مهماً.",
            red_meaning_en="Attendance is critically low. Immediate investigation and parent outreach required.",
            red_meaning_ar="الحضور منخفض بشكل حرج. يستلزم تحقيقاً فورياً والتواصل مع الأسر.",
            green_action_en="Maintain. Monitor for seasonal dips and communicate proactively with parents.",
            green_action_ar="استمر. راقب التغيرات الموسمية وتواصل مع الأهالي مسبقاً.",
            amber_action_en="Identify children with low attendance patterns. Contact parents. Review transportation, illness, and scheduling barriers.",
            amber_action_ar="حدد الأطفال ذوي أنماط الغياب المتكررة. تواصل مع الأهالي. راجع عوائق النقل والمرض والجدول الزمني.",
            red_action_en="Urgent: contact families of all absent children, review class-level variation, check for systemic barriers. Escalate to supervisor.",
            red_action_ar="عاجل: تواصل مع أسر جميع الأطفال الغائبين، راجع التباين على مستوى الفصل، تحقق من العوائق المنهجية. أحل للمشرف.",
        ),
        min_denominator=10,
        min_denominator_high=50,
        category="attendance",
        tags=["attendance", "child_wellbeing", "core"],
    ),

    "excused_absence_rate": KPIStandard(
        kpi_key="excused_absence_rate",
        name_en="Excused Absence Rate",
        name_ar="نسبة الغياب المعذور",
        description_en="Percentage of expected child-days recorded as excused absences. High excused absence may indicate illness patterns or documentation practices.",
        description_ar="نسبة أيام الأطفال المتوقعة المسجلة كغياب معذور. قد يشير الارتفاع إلى أنماط مرض أو ممارسات توثيق.",
        formula_en="EXCUSED_child_days / Expected_child_days × 100",
        formula_ar="أيام الغياب المعذور ÷ أيام الحضور المتوقعة × 100",
        numerator_description_en="Child-days with EXCUSED attendance status",
        numerator_description_ar="أيام الأطفال بحالة غياب معذور",
        denominator_description_en="Expected child-days based on active enrollments × working days",
        denominator_description_ar="أيام الأطفال المتوقعة بناءً على التسجيلات النشطة × أيام الدوام",
        unit="%",
        threshold=ThresholdDefinition(
            green=(None, 5.0),
            amber=(5.01, 15.0),
            red=(15.01, None),
            direction=ThresholdDirection.LOWER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Excused absences are within expected normal range.",
            green_meaning_ar="الغياب المعذور ضمن النطاق الطبيعي المتوقع.",
            amber_meaning_en="Elevated excused absences. Monitor for illness patterns or documentation issues.",
            amber_meaning_ar="غياب معذور مرتفع. راقب أنماط المرض أو مشاكل التوثيق.",
            red_meaning_en="High excused absence rate. Investigate illness outbreaks, documentation practices, or parent patterns.",
            red_meaning_ar="معدل غياب معذور مرتفع جداً. حقق في حالات المرض والتوثيق وأنماط الأهالي.",
        ),
        min_denominator=10,
        min_denominator_high=50,
        category="attendance",
        tags=["attendance", "absence"],
    ),

    "chronic_absence_rate": KPIStandard(
        kpi_key="chronic_absence_rate",
        name_en="Chronic Absence Rate",
        name_ar="معدل الغياب المزمن",
        description_en="Percentage of enrolled children absent (unexcused + excused) for 10% or more of their expected school days.",
        description_ar="نسبة الأطفال الملتحقين الغائبين بنسبة 10% أو أكثر من أيام الدوام المتوقعة لهم.",
        formula_en="(Children with ≥10% total absence) / Active_children × 100",
        formula_ar="(أطفال غائبون بنسبة ≥10%) ÷ الأطفال النشطون × 100",
        numerator_description_en="Children with total absence rate ≥ 10% of their expected days",
        numerator_description_ar="أطفال غائبون بنسبة إجمالية ≥10% من أيامهم المتوقعة",
        denominator_description_en="Total active enrolled children with at least 1 expected day",
        denominator_description_ar="إجمالي الأطفال النشطين الملتحقين مع وجود يوم متوقع واحد على الأقل",
        unit="%",
        threshold=ThresholdDefinition(
            green=(None, 5.0),
            amber=(5.01, 10.0),
            red=(10.01, None),
            direction=ThresholdDirection.LOWER_IS_BETTER,
            unit="%",
            source=_SRC_WHO_ECEC,
            green_meaning_en="Few children are chronically absent. Educational continuity is strong.",
            green_meaning_ar="قلة من الأطفال غائبون بشكل مزمن. الاستمرارية التعليمية قوية.",
            amber_meaning_en="A notable portion of children miss enough days to impact learning significantly.",
            amber_meaning_ar="شريحة ملحوظة من الأطفال يفوتهم عدد من أيام الدوام يؤثر على تعلمهم.",
            red_meaning_en="Chronic absence is at a level that seriously undermines educational outcomes.",
            red_meaning_ar="الغياب المزمن بمستوى يؤثر بشكل جدي على المخرجات التعليمية.",
        ),
        min_denominator=5,
        min_denominator_high=20,
        category="attendance",
        tags=["attendance", "child_wellbeing", "core"],
    ),

    "late_arrival_rate": KPIStandard(
        kpi_key="late_arrival_rate",
        name_en="Late Arrival Rate",
        name_ar="معدل التأخر",
        description_en="Percentage of attended child-days where the child arrived late.",
        description_ar="نسبة أيام الحضور التي وصل فيها الطفل متأخراً.",
        formula_en="LATE_child_days / (PRESENT + LATE)_child_days × 100",
        formula_ar="أيام التأخير ÷ (أيام الحضور + أيام التأخير) × 100",
        numerator_description_en="Child-days with LATE status",
        numerator_description_ar="أيام الأطفال بحالة متأخر",
        denominator_description_en="Total physically attended child-days (PRESENT + LATE)",
        denominator_description_ar="إجمالي أيام الحضور الفعلي (حاضر + متأخر)",
        unit="%",
        threshold=ThresholdDefinition(
            green=(None, 5.0),
            amber=(5.01, 15.0),
            red=(15.01, None),
            direction=ThresholdDirection.LOWER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Punctuality is strong. Children arrive on time consistently.",
            green_meaning_ar="الانضباط في المواعيد ممتاز. الأطفال يصلون في الوقت المحدد باستمرار.",
            amber_meaning_en="Late arrivals are notable. Review pickup logistics, parent schedules, or class start times.",
            amber_meaning_ar="التأخر ملحوظ. راجع لوجستيات التوصيل وجداول الأهالي أو أوقات بدء الدراسة.",
            red_meaning_en="High late arrival rate. Disrupts class routine and child learning.",
            red_meaning_ar="معدل تأخر مرتفع. يعطل روتين الفصل وتعلم الأطفال.",
        ),
        min_denominator=10,
        min_denominator_high=50,
        category="attendance",
        tags=["attendance", "punctuality"],
    ),

    # -----------------------------------------------------------------------
    # B. SAFETY & PROTECTION
    # -----------------------------------------------------------------------

    "incident_rate": KPIStandard(
        kpi_key="incident_rate",
        name_en="Total Incident Rate",
        name_ar="معدل الحوادث الإجمالي",
        description_en="All reported incidents per 1,000 attended child-days. Expressed per 1,000 because incidents are rare events; per-100 would give misleadingly small decimals.",
        description_ar="إجمالي الحوادث المُبلَّغ عنها لكل 1,000 طفل-يوم حضور. يُعبَّر عنها من كل 1,000 لأن الحوادث نادرة؛ القسمة على 100 تعطي أرقاماً صغيرة مضللة.",
        formula_en="Incident_count / Attended_child_days × 1,000",
        formula_ar="عدد الحوادث ÷ أيام الحضور × 1,000",
        numerator_description_en="Count of all incidents (any severity) occurred in period",
        numerator_description_ar="عدد جميع الحوادث (بأي خطورة) التي وقعت في الفترة",
        denominator_description_en="Total attended child-days (PRESENT + LATE)",
        denominator_description_ar="إجمالي أيام الحضور الفعلي (حاضر + متأخر)",
        unit="per 1,000 child-days",
        threshold=ThresholdDefinition(
            green=(None, 2.0),
            amber=(2.01, 5.0),
            red=(5.01, None),
            direction=ThresholdDirection.LOWER_IS_BETTER,
            unit="per 1,000 child-days",
            source=_SRC_INTERNAL,
            green_meaning_en="Incident rate is within safe operating range. Safety procedures are effective.",
            green_meaning_ar="معدل الحوادث ضمن النطاق الآمن. إجراءات السلامة فعّالة.",
            amber_meaning_en="Incident rate is elevated. Review safety procedures and physical environment.",
            amber_meaning_ar="معدل الحوادث مرتفع. راجع إجراءات السلامة والبيئة المادية.",
            red_meaning_en="High incident rate. Immediate safety audit required.",
            red_meaning_ar="معدل حوادث مرتفع جداً. مراجعة سلامة فورية مطلوبة.",
        ),
        min_denominator=100,
        min_denominator_high=500,
        category="safety",
        tags=["safety", "incidents", "core"],
    ),

    "serious_incident_rate": KPIStandard(
        kpi_key="serious_incident_rate",
        name_en="Serious Incident Rate",
        name_ar="معدل الحوادث الخطيرة",
        description_en="HIGH/CRITICAL severity incidents per 1,000 attended child-days.",
        description_ar="الحوادث ذات الخطورة العالية/الحرجة لكل 1,000 طفل-يوم حضور.",
        formula_en="(HIGH + CRITICAL incidents) / Attended_child_days × 1,000",
        formula_ar="(الحوادث العالية + الحرجة) ÷ أيام الحضور × 1,000",
        numerator_description_en="Count of HIGH or CRITICAL severity incidents in period",
        numerator_description_ar="عدد الحوادث ذات الخطورة العالية أو الحرجة في الفترة",
        denominator_description_en="Total attended child-days (PRESENT + LATE)",
        denominator_description_ar="إجمالي أيام الحضور الفعلي",
        unit="per 1,000 child-days",
        threshold=ThresholdDefinition(
            green=(None, 0.0),
            amber=(0.001, 0.5),
            red=(0.501, None),
            direction=ThresholdDirection.LOWER_IS_BETTER,
            unit="per 1,000 child-days",
            source=_SRC_INTERNAL,
            green_meaning_en="No serious incidents. Excellent safety record.",
            green_meaning_ar="لا توجد حوادث خطيرة. سجل سلامة ممتاز.",
            amber_meaning_en="Some serious incidents occurred. Each must be investigated with corrective actions.",
            amber_meaning_ar="وقعت بعض الحوادث الخطيرة. يجب التحقيق في كل منها مع اتخاذ إجراءات تصحيحية.",
            red_meaning_en="Critical safety concern. Immediate escalation, parent notification, and safety inspection required.",
            red_meaning_ar="مشكلة سلامة حرجة. التصعيد الفوري وإبلاغ الأسر ومراجعة السلامة مطلوبة.",
        ),
        min_denominator=100,
        min_denominator_high=500,
        category="safety",
        tags=["safety", "incidents", "core", "high_priority"],
    ),

    "incident_followup_sla": KPIStandard(
        kpi_key="incident_followup_sla",
        name_en="Incident Follow-up SLA",
        name_ar="معدل إغلاق الحوادث في المهلة",
        description_en="Percentage of incidents requiring follow-up that were closed within the 48-hour SLA deadline.",
        description_ar="نسبة الحوادث التي تتطلب متابعة والتي أُغلقت خلال مهلة 48 ساعة.",
        formula_en="Closed_within_SLA / Followup_required_incidents × 100",
        formula_ar="المغلقة في المهلة ÷ الحوادث التي تستلزم متابعة × 100",
        numerator_description_en="Incidents closed at or before their 48-hour SLA deadline",
        numerator_description_ar="الحوادث المغلقة قبل أو عند انتهاء مهلة الـ48 ساعة",
        denominator_description_en="All incidents with followup_required_flag = True in period",
        denominator_description_ar="جميع الحوادث التي تستلزم متابعة في الفترة",
        unit="%",
        threshold=ThresholdDefinition(
            green=(100.0, 100.0),
            amber=(90.0, 99.99),
            red=(None, 89.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="All incidents requiring follow-up were resolved within the 48-hour deadline.",
            green_meaning_ar="جميع الحوادث التي تستلزم متابعة أُغلقت خلال مهلة الـ48 ساعة.",
            amber_meaning_en="Most incidents were resolved in time, but some missed the SLA. Review case management process.",
            amber_meaning_ar="معظم الحوادث أُغلقت في الوقت المحدد، لكن بعضها تجاوز المهلة. راجع عملية إدارة الحوادث.",
            red_meaning_en="Significant SLA breach. Many incidents are not being closed in time. Review follow-up workflow.",
            red_meaning_ar="خرق جسيم للمهلة. كثير من الحوادث لا تُغلق في الوقت المحدد. راجع سير عمل المتابعة.",
        ),
        min_denominator=1,
        min_denominator_high=5,
        category="safety",
        tags=["safety", "incidents", "sla"],
    ),

    # -----------------------------------------------------------------------
    # C. STAFFING & SUPERVISION
    # -----------------------------------------------------------------------

    "ratio_compliance": KPIStandard(
        kpi_key="ratio_compliance",
        name_en="Staff-Child Ratio Compliance",
        name_ar="الامتثال لنسبة الموظف للأطفال",
        description_en="Percentage of operating minutes compliant with the required 1:10 staff-to-child ratio.",
        description_ar="نسبة دقائق التشغيل المتوافقة مع نسبة الموظف للأطفال المطلوبة 1:10.",
        formula_en="Compliant_minutes / Operating_minutes × 100",
        formula_ar="الدقائق المتوافقة ÷ إجمالي دقائق التشغيل × 100",
        numerator_description_en="Minutes where actual staff count meets or exceeds required ratio",
        numerator_description_ar="الدقائق التي يفي فيها عدد الموظفين الفعلي بالنسبة المطلوبة أو يتجاوزها",
        denominator_description_en="Total operating minutes in period (from operating hours)",
        denominator_description_ar="إجمالي دقائق التشغيل في الفترة (من ساعات العمل)",
        unit="%",
        threshold=ThresholdDefinition(
            green=(95.0, None),
            amber=(80.0, 94.99),
            red=(None, 79.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_JORDAN_MOE,
            green_meaning_en="Staff-child ratios are maintained at all times. Children are well supervised.",
            green_meaning_ar="نسب الموظف للأطفال محافظ عليها في جميع الأوقات. الأطفال تحت إشراف جيد.",
            amber_meaning_en="Some periods with insufficient staff coverage. Review scheduling and absences.",
            amber_meaning_ar="بعض الفترات يوجد فيها تغطية موظفين غير كافية. راجع الجدول والغيابات.",
            red_meaning_en="Critical understaffing detected. Child safety may be at risk. Immediate corrective action required.",
            red_meaning_ar="نقص حرج في الموظفين. سلامة الأطفال قد تكون في خطر. إجراء تصحيحي فوري مطلوب.",
        ),
        min_denominator=60,
        min_denominator_high=480,
        category="staffing",
        tags=["staffing", "safety", "compliance", "core"],
    ),

    "training_completion_rate": KPIStandard(
        kpi_key="training_completion_rate",
        name_en="Training Completion Rate",
        name_ar="معدل إتمام التدريب",
        description_en="Percentage of mandatory training module completions achieved by active staff in the period.",
        description_ar="نسبة وحدات التدريب الإلزامية المنجزة من قبل الموظفين النشطين في الفترة.",
        formula_en="Completed_training_records / (Active_staff × Mandatory_modules) × 100",
        formula_ar="سجلات التدريب المنجزة ÷ (الموظفون النشطون × الوحدات الإلزامية) × 100",
        numerator_description_en="Staff training completion records with COMPLETED status in period",
        numerator_description_ar="سجلات إتمام التدريب بحالة مكتمل في الفترة",
        denominator_description_en="Active staff count × mandatory module count",
        denominator_description_ar="عدد الموظفين النشطين × عدد الوحدات الإلزامية",
        unit="%",
        threshold=ThresholdDefinition(
            green=(90.0, None),
            amber=(75.0, 89.99),
            red=(None, 74.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Staff are well trained. Required competencies are being maintained.",
            green_meaning_ar="الموظفون مدربون جيداً. الكفاءات المطلوبة يتم الحفاظ عليها.",
            amber_meaning_en="Some training gaps exist. Identify which staff and modules are outstanding.",
            amber_meaning_ar="توجد بعض الثغرات التدريبية. حدد الموظفين والوحدات المتأخرة.",
            red_meaning_en="Significant training deficiency. Staff may lack critical competencies.",
            red_meaning_ar="نقص تدريبي كبير. قد يفتقر الموظفون إلى الكفاءات الحرجة.",
        ),
        min_denominator=1,
        min_denominator_high=5,
        category="staffing",
        tags=["staffing", "compliance", "training"],
    ),

    # -----------------------------------------------------------------------
    # D. PARENT ENGAGEMENT
    # -----------------------------------------------------------------------

    "report_submission_rate": KPIStandard(
        kpi_key="report_submission_rate",
        name_en="Daily Report Submission Rate",
        name_ar="معدل تقديم التقارير اليومية",
        description_en="Percentage of expected daily reports (one per child per working day) that reached at least SUBMITTED status.",
        description_ar="نسبة التقارير اليومية المتوقعة (واحدة لكل طفل لكل يوم دراسي) التي وصلت إلى مرحلة التقديم على الأقل.",
        formula_en="Submitted_reports / Expected_reports × 100  (capped at 100%)",
        formula_ar="التقارير المقدمة ÷ التقارير المتوقعة × 100 (بحد أقصى 100%)",
        numerator_description_en="Daily reports with status SUBMITTED, APPROVED, SENT_TO_PARENT, REJECTED, or RETURNED",
        numerator_description_ar="تقارير بحالة مقدم أو موافق عليه أو مرسل للأهل أو مرفوض أو معاد",
        denominator_description_en="Expected child-days (active enrollments × working days)",
        denominator_description_ar="أيام الأطفال المتوقعة (التسجيلات النشطة × أيام الدوام)",
        unit="%",
        threshold=ThresholdDefinition(
            green=(95.0, None),
            amber=(85.0, 94.99),
            red=(None, 84.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Reports are being submitted consistently. Parents receive timely updates.",
            green_meaning_ar="التقارير تُقدَّم بانتظام. الأهالي يتلقون تحديثات في الوقت المناسب.",
            amber_meaning_en="Some reports are missing. Identify supervisors with low submission rates.",
            amber_meaning_ar="بعض التقارير ناقصة. حدد المشرفين ذوي معدلات التقديم المنخفضة.",
            red_meaning_en="Low report submission. Parents are not receiving adequate daily updates.",
            red_meaning_ar="معدل تقديم التقارير منخفض. الأهالي لا يتلقون تحديثات يومية كافية.",
        ),
        min_denominator=5,
        min_denominator_high=20,
        category="parent_engagement",
        tags=["reports", "parent_engagement", "core"],
    ),

    "parent_satisfaction_score": KPIStandard(
        kpi_key="parent_satisfaction_score",
        name_en="Parent Satisfaction Score",
        name_ar="درجة رضا الأهالي",
        description_en="NPS-derived satisfaction score on a 0-100 scale. NPS = Promoters% − Detractors%. Promoters: score ≥ 9. Detractors: score ≤ 6. Score = (NPS + 100) / 2.",
        description_ar="درجة رضا مشتقة من NPS على مقياس 0-100. NPS = %المروجون - %المعارضون. المروجون: درجة ≥9. المعارضون: درجة ≤6. الدرجة = (NPS + 100) / 2.",
        formula_en="(NPS + 100) / 2  where NPS = (Promoters% - Detractors%)",
        formula_ar="(NPS + 100) / 2 حيث NPS = (%المروجون - %المعارضون)",
        numerator_description_en="NPS score derived from survey responses (Promoters - Detractors)",
        numerator_description_ar="درجة NPS المشتقة من استجابات الاستطلاع",
        denominator_description_en="Eligible parents with active enrolled children",
        denominator_description_ar="الأهالي المؤهلون الذين لديهم أطفال ملتحقون نشطون",
        unit="score (0-100)",
        threshold=ThresholdDefinition(
            green=(75.0, None),
            amber=(50.0, 74.99),
            red=(None, 49.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="score",
            source=_SRC_INTERNAL,
            green_meaning_en="Parents are highly satisfied. Strong trust and engagement.",
            green_meaning_ar="الأهالي راضون جداً. ثقة ومشاركة عالية.",
            amber_meaning_en="Moderate satisfaction. Identify concerns and improve communication.",
            amber_meaning_ar="رضا متوسط. حدد المخاوف وحسّن التواصل.",
            red_meaning_en="Low parent satisfaction. Urgent review of communication and service quality.",
            red_meaning_ar="رضا الأهالي منخفض. مراجعة عاجلة للتواصل وجودة الخدمة.",
        ),
        min_denominator=10,
        min_denominator_high=30,
        category="parent_engagement",
        tags=["parent_engagement", "satisfaction", "nps"],
    ),

    # -----------------------------------------------------------------------
    # E. COMPLIANCE & GOVERNANCE
    # -----------------------------------------------------------------------

    "checklist_compliance": KPIStandard(
        kpi_key="checklist_compliance",
        name_en="Safety Checklist Compliance",
        name_ar="الامتثال لقوائم الفحص",
        description_en="Percentage of required daily checklists (opening, safety, closing) completed on working days.",
        description_ar="نسبة قوائم الفحص اليومية المطلوبة (افتتاح، سلامة، إغلاق) المكتملة في أيام الدوام.",
        formula_en="Completed_checklists / (Working_days × 3) × 100",
        formula_ar="قوائم الفحص المكتملة ÷ (أيام الدوام × 3) × 100",
        numerator_description_en="Completed checklist records (opening, safety, closing) in period",
        numerator_description_ar="سجلات قوائم الفحص المكتملة في الفترة",
        denominator_description_en="Working days × 3 required checklist types",
        denominator_description_ar="أيام الدوام × 3 أنواع قوائم فحص مطلوبة",
        unit="%",
        threshold=ThresholdDefinition(
            green=(95.0, None),
            amber=(80.0, 94.99),
            red=(None, 79.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Daily checklists are being completed consistently. Good operational discipline.",
            green_meaning_ar="قوائم الفحص اليومية تُكتمل باستمرار. انضباط تشغيلي جيد.",
            amber_meaning_en="Some checklists are being missed. Identify patterns by type or day.",
            amber_meaning_ar="بعض قوائم الفحص تُفوَّت. حدد الأنماط حسب النوع أو اليوم.",
            red_meaning_en="Significant checklist gaps. Safety and compliance risk is elevated.",
            red_meaning_ar="ثغرات كبيرة في قوائم الفحص. مخاطر السلامة والامتثال مرتفعة.",
        ),
        min_denominator=3,
        min_denominator_high=15,
        category="governance",
        tags=["compliance", "safety", "checklists"],
    ),

    "capacity_utilization_rate": KPIStandard(
        kpi_key="capacity_utilization_rate",
        name_en="Capacity Utilization Rate",
        name_ar="معدل استغلال الطاقة الاستيعابية",
        description_en="Active enrolled children as a percentage of total licensed class capacity.",
        description_ar="الأطفال المسجلون النشطون كنسبة من إجمالي الطاقة الاستيعابية المرخصة للفصول.",
        formula_en="Active_enrollments / Total_class_capacity × 100",
        formula_ar="التسجيلات النشطة ÷ إجمالي طاقة الفصول × 100",
        numerator_description_en="Active enrollment applications",
        numerator_description_ar="طلبات التسجيل النشطة",
        denominator_description_en="Sum of capacity_total for all active classes",
        denominator_description_ar="مجموع السعة الإجمالية لجميع الفصول النشطة",
        unit="%",
        threshold=ThresholdDefinition(
            green=(70.0, 99.99),
            amber=(50.0, 69.99),
            red=(None, 49.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_INTERNAL,
            green_meaning_en="Kindergarten is operating at a healthy enrollment level.",
            green_meaning_ar="الحضانة تعمل بمستوى تسجيل صحي.",
            amber_meaning_en="Underutilized capacity. Review enrollment strategies.",
            amber_meaning_ar="طاقة غير مستغلة. راجع استراتيجيات التسجيل.",
            red_meaning_en="Very low enrollment. Financial and operational sustainability may be at risk.",
            red_meaning_ar="تسجيل منخفض جداً. الاستدامة المالية والتشغيلية قد تكون في خطر.",
        ),
        min_denominator=1,
        min_denominator_high=1,
        category="governance",
        tags=["enrollment", "capacity", "governance"],
    ),

    "regulatory_status": KPIStandard(
        kpi_key="regulatory_status",
        name_en="License & Regulatory Status",
        name_ar="حالة الترخيص والامتثال التنظيمي",
        description_en="License validity score: 100% if valid and not expiring soon, 60% if expiring within 30 days, 0% if expired.",
        description_ar="درجة صلاحية الترخيص: 100% إذا كان صالحاً وغير منتهٍ قريباً، 60% إذا كان ينتهي خلال 30 يوماً، 0% إذا انتهى.",
        formula_en="100% if valid >30 days; 60% if expiring ≤30 days; 0% if expired or missing",
        formula_ar="100% إذا صالح أكثر من 30 يوم؛ 60% إذا ينتهي خلال ≤30 يوم؛ 0% إذا انتهى أو غائب",
        numerator_description_en="License validity score",
        numerator_description_ar="درجة صلاحية الترخيص",
        denominator_description_en="Maximum score (100)",
        denominator_description_ar="الدرجة القصوى (100)",
        unit="%",
        threshold=ThresholdDefinition(
            green=(100.0, 100.0),
            amber=(60.0, 99.99),
            red=(None, 59.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="%",
            source=_SRC_JORDAN_MOE_VERIFIED,
            green_meaning_en="License is valid and not at risk of expiry.",
            green_meaning_ar="الترخيص صالح وليس في خطر الانتهاء.",
            amber_meaning_en="License expires within 30 days. Renewal must be initiated immediately.",
            amber_meaning_ar="الترخيص ينتهي خلال 30 يوماً. يجب البدء بالتجديد فوراً.",
            red_meaning_en="License is expired or missing. Operations may be illegal. Immediate action required.",
            red_meaning_ar="الترخيص منتهٍ أو غائب. قد تكون العمليات غير قانونية. إجراء فوري مطلوب.",
        ),
        min_denominator=1,
        min_denominator_high=1,
        category="governance",
        tags=["compliance", "licensing", "governance", "hard_override"],
    ),

    # -----------------------------------------------------------------------
    # F. COMPOSITE SCORES
    # -----------------------------------------------------------------------

    "gqi_score": KPIStandard(
        kpi_key="gqi_score",
        name_en="Governance Quality Index (GQI)",
        name_ar="مؤشر جودة الحوكمة",
        description_en="Weighted composite of governance KPIs: Ratio Compliance (30%), Checklist Compliance (20%), Regulatory Status (20%), Training Completion (15%), Incident Follow-up SLA (15%).",
        description_ar="مركّب موزون من مؤشرات الحوكمة: نسبة الموظف للأطفال (30%)، قوائم الفحص (20%)، حالة الترخيص (20%)، التدريب (15%)، متابعة الحوادث (15%).",
        formula_en="Σ(component_value × weight) / Σ(weights with data)",
        formula_ar="مجموع(قيمة المؤشر × الوزن) ÷ مجموع(الأوزان التي لها بيانات)",
        numerator_description_en="Weighted sum of available governance components",
        numerator_description_ar="المجموع الموزون للمكونات المتاحة",
        denominator_description_en="Sum of weights for components with data",
        denominator_description_ar="مجموع أوزان المكونات التي لها بيانات",
        unit="score (0-100)",
        threshold=ThresholdDefinition(
            green=(80.0, None),
            amber=(60.0, 79.99),
            red=(None, 59.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="score",
            source=_SRC_INTERNAL,
        ),
        min_denominator=1,
        min_denominator_high=1,
        category="governance",
        tags=["governance", "composite", "core"],
    ),

    "cei_score": KPIStandard(
        kpi_key="cei_score",
        name_en="Child Experience Index (CEI)",
        name_ar="مؤشر تجربة الطفل",
        description_en="Weighted composite of child experience KPIs: Physical Attendance Rate (35%), Chronic Absence (inverted, 25%), Serious Incident Rate (inverted, 20%), Parent Satisfaction (20%).",
        description_ar="مركّب موزون من مؤشرات تجربة الطفل: نسبة الحضور الفعلي (35%)، الغياب المزمن (معكوس، 25%)، معدل الحوادث الخطيرة (معكوس، 20%)، رضا الأهالي (20%).",
        formula_en="Σ(component_value × weight) / Σ(weights with data)",
        formula_ar="مجموع(قيمة المؤشر × الوزن) ÷ مجموع(الأوزان التي لها بيانات)",
        numerator_description_en="Weighted sum of available child experience components",
        numerator_description_ar="المجموع الموزون لمكونات تجربة الطفل المتاحة",
        denominator_description_en="Sum of weights for components with data",
        denominator_description_ar="مجموع أوزان المكونات التي لها بيانات",
        unit="score (0-100)",
        threshold=ThresholdDefinition(
            green=(80.0, None),
            amber=(60.0, 79.99),
            red=(None, 59.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="score",
            source=_SRC_INTERNAL,
        ),
        min_denominator=1,
        min_denominator_high=1,
        category="governance",
        tags=["child_experience", "composite", "core"],
    ),

    "overall_gcei": KPIStandard(
        kpi_key="overall_gcei",
        name_en="Governance & Child Experience Index (GCEI)",
        name_ar="مؤشر الحوكمة وتجربة الطفل",
        description_en="Top-level composite index: 60% GQI + 40% CEI. Subject to hard override rules.",
        description_ar="المؤشر المركّب الرئيسي: 60% مؤشر جودة الحوكمة + 40% مؤشر تجربة الطفل. يخضع لقواعد التجاوز الصارمة.",
        formula_en="(GQI × 0.60) + (CEI × 0.40)",
        formula_ar="(مؤشر الحوكمة × 0.60) + (مؤشر تجربة الطفل × 0.40)",
        numerator_description_en="Weighted sum of GQI and CEI",
        numerator_description_ar="المجموع الموزون لمؤشر الحوكمة ومؤشر تجربة الطفل",
        denominator_description_en="Total weight (1.0 if both present, partial otherwise)",
        denominator_description_ar="الوزن الإجمالي (1.0 إذا كلاهما موجود، جزئي بخلاف ذلك)",
        unit="score (0-100)",
        threshold=ThresholdDefinition(
            green=(80.0, None),
            amber=(60.0, 79.99),
            red=(None, 59.99),
            direction=ThresholdDirection.HIGHER_IS_BETTER,
            unit="score",
            source=_SRC_INTERNAL,
            green_meaning_en="Kindergarten is performing well across governance and child experience dimensions.",
            green_meaning_ar="الحضانة تؤدي أداءً جيداً في مجالي الحوكمة وتجربة الطفل.",
            amber_meaning_en="Performance is acceptable but improvements are needed in one or more areas.",
            amber_meaning_ar="الأداء مقبول لكن هناك تحسينات مطلوبة في مجال أو أكثر.",
            red_meaning_en="Performance is below acceptable levels. Comprehensive review and action plan required.",
            red_meaning_ar="الأداء دون المستوى المقبول. مراجعة شاملة وخطة عمل مطلوبة.",
        ),
        min_denominator=1,
        min_denominator_high=1,
        category="governance",
        tags=["governance", "composite", "core", "top_level"],
    ),
}

# Aliases — bundle and legacy code use these short names; point to canonical standards
STANDARDS["attendance_rate"] = STANDARDS["physical_attendance_rate"]
STANDARDS["parent_satisfaction"] = STANDARDS["parent_satisfaction_score"]


# ---------------------------------------------------------------------------
# Hard override rules
# ---------------------------------------------------------------------------

HARD_OVERRIDE_RULES: List[HardOverrideRule] = [
    HardOverrideRule(
        rule_id="LICENSE_EXPIRED",
        description_en="If the kindergarten's operating license is expired, the overall status must be RED regardless of other scores.",
        description_ar="إذا انتهت صلاحية ترخيص الحضانة، يجب أن يكون الوضع العام أحمر بصرف النظر عن الدرجات الأخرى.",
        forces_band=BandColor.RED,
        condition_description_en="license_valid_until < today",
        condition_description_ar="تاريخ انتهاء الترخيص < اليوم",
    ),
    HardOverrideRule(
        rule_id="UNRESOLVED_CRITICAL_INCIDENT",
        description_en="If there is an unresolved CRITICAL severity incident, the overall status cannot be GREEN.",
        description_ar="إذا كان هناك حادث بخطورة حرجة غير محلول، لا يمكن أن يكون الوضع العام أخضر.",
        forces_band=BandColor.AMBER,
        condition_description_en="open CRITICAL incident with followup_required_flag=True and closed_at=None",
        condition_description_ar="حادث حرج مفتوح مع followup_required_flag=True و closed_at=None",
    ),
    HardOverrideRule(
        rule_id="RATIO_BELOW_MINIMUM",
        description_en="If staff-child ratio compliance falls below 60%, overall status must be RED.",
        description_ar="إذا انخفض امتثال نسبة الموظف للأطفال عن 60%، يجب أن يكون الوضع العام أحمر.",
        forces_band=BandColor.RED,
        condition_description_en="ratio_compliance < 60.0",
        condition_description_ar="نسبة الامتثال للموظف للأطفال < 60%",
    ),
    HardOverrideRule(
        rule_id="INSUFFICIENT_DATA_COVERAGE",
        description_en="If overall data coverage is below 60%, status is INSUFFICIENT_DATA rather than green/amber/red.",
        description_ar="إذا كانت تغطية البيانات الإجمالية أقل من 60%، تكون الحالة 'بيانات غير كافية' بدلاً من أخضر/أصفر/أحمر.",
        forces_band=BandColor.INSUFFICIENT,
        condition_description_en="data_coverage_pct < 60.0",
        condition_description_ar="نسبة تغطية البيانات < 60%",
    ),
    HardOverrideRule(
        rule_id="OVERCAPACITY",
        description_en="If active enrollments exceed licensed capacity, a HIGH RISK warning is triggered for capacity utilization.",
        description_ar="إذا تجاوزت التسجيلات النشطة الطاقة الاستيعابية المرخصة، يُطلق تحذير عالي المخاطر لاستغلال الطاقة.",
        forces_band=BandColor.RED,
        condition_description_en="active_enrollments > total_class_capacity",
        condition_description_ar="التسجيلات النشطة > إجمالي طاقة الفصول",
    ),
]

# Minimum coverage threshold for INSUFFICIENT_DATA override
MIN_COVERAGE_FOR_RATING = 60.0


# ---------------------------------------------------------------------------
# Confidence level logic
# ---------------------------------------------------------------------------

def compute_confidence(
    denominator: int,
    min_denominator: int,
    min_denominator_high: int,
    has_data: bool,
) -> ConfidenceLevel:
    """
    Return the confidence level based on denominator size and data presence.
    """
    if not has_data or denominator == 0:
        return ConfidenceLevel.INSUFFICIENT
    if denominator >= min_denominator_high:
        return ConfidenceLevel.HIGH
    if denominator >= min_denominator:
        return ConfidenceLevel.MEDIUM
    if denominator > 0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT


# ---------------------------------------------------------------------------
# Band assignment logic
# ---------------------------------------------------------------------------

def assign_band(
    kpi_key: str,
    value: float,
    has_data: bool,
    confidence: ConfidenceLevel,
    data_coverage_pct: float = 100.0,
) -> BandColor:
    """
    Assign a color band to a KPI value using the centralized standards.
    Returns GRAY if no data, INSUFFICIENT if coverage < 60% or confidence is insufficient.
    """
    if not has_data or confidence == ConfidenceLevel.INSUFFICIENT:
        return BandColor.GRAY

    if data_coverage_pct < MIN_COVERAGE_FOR_RATING:
        return BandColor.INSUFFICIENT

    std = STANDARDS.get(kpi_key)
    if not std:
        return BandColor.GRAY

    t = std.threshold
    if t.direction == ThresholdDirection.LOWER_IS_BETTER:
        green_min, green_max = t.green
        amber_min, amber_max = t.amber

        if green_max is None:
            # Lower is green means: value <= green_min (no, this is wrong)
            # For lower_is_better, green = (None, X) means value <= X
            if value <= (green_min if green_min is not None else float("inf")):
                return BandColor.GREEN
            elif value <= (amber_max if amber_max is not None else float("inf")):
                return BandColor.AMBER
            else:
                return BandColor.RED
        else:
            if (green_min is None or value >= green_min) and (green_max is None or value <= green_max):
                return BandColor.GREEN
            elif (amber_min is None or value >= amber_min) and (amber_max is None or value <= amber_max):
                return BandColor.AMBER
            else:
                return BandColor.RED
    else:
        # Higher is better
        green_min, green_max = t.green
        amber_min, amber_max = t.amber

        if green_min is None or value >= green_min:
            if green_max is None or value <= green_max:
                return BandColor.GREEN
        if amber_min is None or value >= amber_min:
            if amber_max is None or value <= amber_max:
                return BandColor.AMBER
        return BandColor.RED


def get_band_label(kpi_key: str, band: BandColor, lang: str = "ar") -> str:
    """Return the status label for a given band."""
    std = STANDARDS.get(kpi_key)
    if not std:
        return band.value
    t = std.threshold
    if lang == "en":
        labels = {
            BandColor.GREEN: t.green_label_en,
            BandColor.AMBER: t.amber_label_en,
            BandColor.RED: t.red_label_en,
            BandColor.GRAY: t.gray_label_en,
            BandColor.INSUFFICIENT: "Insufficient Data",
        }
    else:
        labels = {
            BandColor.GREEN: t.green_label_ar,
            BandColor.AMBER: t.amber_label_ar,
            BandColor.RED: t.red_label_ar,
            BandColor.GRAY: t.gray_label_ar,
            BandColor.INSUFFICIENT: "بيانات غير كافية",
        }
    return labels.get(band, band.value)


def get_band_meaning(kpi_key: str, band: BandColor, lang: str = "ar") -> str:
    """Return the meaning text for a given band."""
    std = STANDARDS.get(kpi_key)
    if not std:
        return ""
    t = std.threshold
    if lang == "en":
        meanings = {
            BandColor.GREEN: t.green_meaning_en,
            BandColor.AMBER: t.amber_meaning_en,
            BandColor.RED: t.red_meaning_en,
        }
    else:
        meanings = {
            BandColor.GREEN: t.green_meaning_ar,
            BandColor.AMBER: t.amber_meaning_ar,
            BandColor.RED: t.red_meaning_ar,
        }
    return meanings.get(band, "")


def get_band_action(kpi_key: str, band: BandColor, lang: str = "ar") -> str:
    """Return the recommended action for a given band."""
    std = STANDARDS.get(kpi_key)
    if not std:
        return ""
    t = std.threshold
    if lang == "en":
        actions = {
            BandColor.GREEN: t.green_action_en,
            BandColor.AMBER: t.amber_action_en,
            BandColor.RED: t.red_action_en,
        }
    else:
        actions = {
            BandColor.GREEN: t.green_action_ar,
            BandColor.AMBER: t.amber_action_ar,
            BandColor.RED: t.red_action_ar,
        }
    return actions.get(band, "")


def get_threshold_source_dict(kpi_key: str) -> dict:
    """Return threshold source metadata as a dict for API responses."""
    std = STANDARDS.get(kpi_key)
    if not std:
        return {}
    src = std.threshold.source
    return {
        "source_name": src.source_name,
        "jurisdiction": src.jurisdiction,
        "validation_status": src.validation_status.value,
        "effective_date": src.effective_date,
        "source_url": src.source_url,
        "review_date": src.review_date,
        "notes_en": src.notes_en,
        "notes_ar": src.notes_ar,
    }


def list_all_standards() -> List[dict]:
    """Return all KPI standards as a list of dicts for the /kpi/standards endpoint."""
    result = []
    for key, std in STANDARDS.items():
        t = std.threshold
        result.append({
            "kpi_key": key,
            "name_en": std.name_en,
            "name_ar": std.name_ar,
            "description_en": std.description_en,
            "description_ar": std.description_ar,
            "formula_en": std.formula_en,
            "formula_ar": std.formula_ar,
            "numerator_description_en": std.numerator_description_en,
            "numerator_description_ar": std.numerator_description_ar,
            "denominator_description_en": std.denominator_description_en,
            "denominator_description_ar": std.denominator_description_ar,
            "unit": std.unit,
            "category": std.category,
            "tags": std.tags,
            "direction": t.direction.value,
            "thresholds": {
                "green": {"min": t.green[0], "max": t.green[1]},
                "amber": {"min": t.amber[0], "max": t.amber[1]},
                "red": {"min": t.red[0], "max": t.red[1]},
            },
            "threshold_source": get_threshold_source_dict(key),
            "min_denominator": std.min_denominator,
            "min_denominator_high": std.min_denominator_high,
        })
    return result


def list_hard_override_rules() -> List[dict]:
    """Return all hard override rules as dicts."""
    return [
        {
            "rule_id": r.rule_id,
            "description_en": r.description_en,
            "description_ar": r.description_ar,
            "forces_band": r.forces_band.value,
            "condition_description_en": r.condition_description_en,
            "condition_description_ar": r.condition_description_ar,
        }
        for r in HARD_OVERRIDE_RULES
    ]
