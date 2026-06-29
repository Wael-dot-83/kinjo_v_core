from typing import Dict, Optional

# Basic I18n implementation for Analytics Metrics

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Network (1-7)
    "equity_index": {"en": "Equity Index", "ar": "مؤشر الإنصاف"},
    "capacity_pressure": {"en": "Capacity Pressure", "ar": "ضغط السعة الاستيعابية"},
    "digital_engagement": {"en": "Digital Engagement", "ar": "المشاركة الرقمية"},
    "license_expiry": {"en": "License Expiry Distribution", "ar": "توزيع انتهاء التراخيص"},
    "network_attendance": {"en": "Overall Network Attendance", "ar": "الحضور العام للشبكة"},
    "network_incidents": {"en": "Overall Network Incidents", "ar": "الحوادث العامة للشبكة"},
    "staff_retention": {"en": "Staff Retention Rate", "ar": "معدل استبقاء الموظفين"},
    
    # Governorate (8-14)
    "variance_index": {"en": "Performance Variance Index", "ar": "مؤشر التباين في الأداء"},
    "chronic_absenteeism": {"en": "Chronic Absenteeism", "ar": "التغيب المزمن"},
    "nps": {"en": "Net Promoter Score (NPS)", "ar": "صافي نقاط الترويج"},
    "incident_density": {"en": "Incident Density (Heatmap)", "ar": "كثافة الحوادث"},
    "capacity_utilization": {"en": "Capacity Utilization", "ar": "استخدام السعة"},
    "regulatory_compliance": {"en": "Regulatory Compliance", "ar": "الامتثال التنظيمي"},
    "gqi_average": {"en": "GQI Average", "ar": "متوسط مؤشر جودة الحوكمة"},
    
    # Kindergarten (15-21)
    "child_risk_score": {"en": "Child Risk Score", "ar": "درجة الخطر على الطفل"},
    "age_appropriateness": {"en": "Age-Appropriateness Ratio", "ar": "نسبة الملاءمة العمرية"},
    "parent_response": {"en": "Parent Response Time", "ar": "وقت استجابة الوالدين"},
    "staff_child_ratio": {"en": "Staff-to-Child Ratio Trend", "ar": "اتجاه نسبة الموظفين إلى الأطفال"},
    "hygiene_compliance": {"en": "Hygiene Compliance", "ar": "الامتثال للنظافة"},
    "report_submission_rate": {"en": "Report Submission Rate", "ar": "معدل تقديم التقارير"},
    "training_completion": {"en": "Training Completion", "ar": "إتمام التدريب"},
    
    # Child (22-26)
    "timeline_progress": {"en": "Timeline Progress", "ar": "التقدم الزمني"},
    "development_radar": {"en": "Development Progress (Radar)", "ar": "تطور النمو (رادار)"},
    "engagement_score": {"en": "Engagement Score", "ar": "درجة المشاركة"},
    "health_status": {"en": "Health Status Alerts", "ar": "تنبيهات الحالة الصحية"},
    "assessment_milestone": {"en": "Assessment Milestones", "ar": "إنجازات التقييم"},
    
    # Predictive (27-29)
    "dropout_risk": {"en": "Dropout Risk", "ar": "خطر التسرب"},
    "performance_trajectory": {"en": "Performance Trajectory", "ar": "مسار الأداء"},
    "time_series_forecast": {"en": "Time-Series Forecast", "ar": "توقعات السلاسل الزمنية"},
    
    # Governance (30-33)
    "anomaly_correlation": {"en": "Anomaly Cross-Correlation", "ar": "الترابط بين الحالات الشاذة"},
    "data_quality_metric": {"en": "Data Quality Metric (GQI)", "ar": "مقياس جودة البيانات"},
    "ratio_enforcement": {"en": "Ratio Enforcement Score", "ar": "درجة إنفاذ النسبة"},
    "compliance_audit": {"en": "Compliance Audit Score", "ar": "درجة تدقيق الامتثال"}
}

def get_message(key: str, locale: str = "en") -> str:
    """Retrieve localized string or fallback to English or Key."""
    return TRANSLATIONS.get(key, {}).get(locale, TRANSLATIONS.get(key, {}).get("en", key))

def get_label_dict(key: str) -> dict:
    """Returns a dict with 'en' and 'ar' keys."""
    return TRANSLATIONS.get(key, {"en": key, "ar": key})
