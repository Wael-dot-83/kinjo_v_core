import re

with open("analytics_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# attendance
content = content.replace(
    '{"id": "total_present", "label": "إجمالي الحضور", "value": 0, "unit": ""}',
    '{"id": "total_present", "label_ar": "إجمالي الحضور", "label_en": "Total Present", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "total_absent", "label": "إجمالي الغياب", "value": 0, "unit": ""}',
    '{"id": "total_absent", "label_ar": "إجمالي الغياب", "label_en": "Total Absent", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "attendance_rate", "label": "معدل الحضور", "value": 0, "unit": "%"}',
    '{"id": "attendance_rate", "label_ar": "معدل الحضور", "label_en": "Attendance Rate", "value": 0, "unit": "%"}'
)
content = content.replace(
    '{"id": "absence_rate", "label": "معدل الغياب", "value": 0, "unit": "%"}',
    '{"id": "absence_rate", "label_ar": "معدل الغياب", "label_en": "Absence Rate", "value": 0, "unit": "%"}'
)

content = content.replace(
    '{"id": "attendance_trend", "type": "line", "label": "اتجاه الحضور"}',
    '{"id": "attendance_trend", "type": "line", "label_ar": "اتجاه الحضور", "label_en": "Attendance Trend"}'
)
content = content.replace(
    '{"id": "absence_by_governorate", "type": "bar", "label": "الغياب حسب المحافظة"}',
    '{"id": "absence_by_governorate", "type": "bar", "label_ar": "الغياب حسب المحافظة", "label_en": "Absence by Governorate"}'
)

content = content.replace(
    'warnings.append("تعذر تحميل بيانات الحضور")',
    'warnings.append({"ar": "تعذر تحميل بيانات الحضور", "en": "Failed to load attendance data"})'
)
content = content.replace(
    'insights.append("لا توجد بيانات كافية للحضور في الفترة المحددة")',
    'insights.append({"ar": "لا توجد بيانات كافية للحضور في الفترة المحددة", "en": "Insufficient attendance data for the selected period"})'
)

# incidents
content = content.replace(
    '{"id": "total_incidents", "label": "إجمالي الحوادث", "value": 0, "unit": ""}',
    '{"id": "total_incidents", "label_ar": "إجمالي الحوادث", "label_en": "Total Incidents", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "open_incidents", "label": "الحوادث المفتوحة", "value": 0, "unit": ""}',
    '{"id": "open_incidents", "label_ar": "الحوادث المفتوحة", "label_en": "Open Incidents", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "critical_incidents", "label": "حوادث حرجة", "value": 0, "unit": ""}',
    '{"id": "critical_incidents", "label_ar": "حوادث حرجة", "label_en": "Critical Incidents", "value": 0, "unit": ""}'
)

content = content.replace(
    '{"id": "incidents_over_time", "type": "line", "label": "الحوادث عبر الزمن"}',
    '{"id": "incidents_over_time", "type": "line", "label_ar": "الحوادث عبر الزمن", "label_en": "Incidents Over Time"}'
)
content = content.replace(
    '{"id": "incidents_by_severity", "type": "doughnut", "label": "حسب الخطورة"}',
    '{"id": "incidents_by_severity", "type": "doughnut", "label_ar": "حسب الخطورة", "label_en": "By Severity"}'
)

content = content.replace(
    'warnings.append("تعذر تحميل بيانات الحوادث")',
    'warnings.append({"ar": "تعذر تحميل بيانات الحوادث", "en": "Failed to load incident data"})'
)

# compliance
content = content.replace(
    '{"id": "compliance_score", "label": "درجة الامتثال", "value": 0, "unit": "/ 100"}',
    '{"id": "compliance_score", "label_ar": "درجة الامتثال", "label_en": "Compliance Score", "value": 0, "unit": "/ 100"}'
)
content = content.replace(
    '{"id": "governance_score", "label": "درجة الحوكمة", "value": 0, "unit": "/ 100"}',
    '{"id": "governance_score", "label_ar": "درجة الحوكمة", "label_en": "Governance Score", "value": 0, "unit": "/ 100"}'
)

content = content.replace(
    '{"id": "governance_distribution", "type": "pie", "label": "توزيع الحوكمة"}',
    '{"id": "governance_distribution", "type": "pie", "label_ar": "توزيع الحوكمة", "label_en": "Governance Distribution"}'
)

content = content.replace(
    'warnings.append("تعذر تحميل بيانات الحوكمة")',
    'warnings.append({"ar": "تعذر تحميل بيانات الحوكمة", "en": "Failed to load governance data"})'
)

# enrollment
content = content.replace(
    '{"id": "total_applications", "label": "إجمالي الطلبات", "value": 0, "unit": ""}',
    '{"id": "total_applications", "label_ar": "إجمالي الطلبات", "label_en": "Total Applications", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "approved", "label": "موافق عليه", "value": 0, "unit": ""}',
    '{"id": "approved", "label_ar": "موافق عليه", "label_en": "Approved", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "rejected", "label": "مرفوض", "value": 0, "unit": ""}',
    '{"id": "rejected", "label_ar": "مرفوض", "label_en": "Rejected", "value": 0, "unit": ""}'
)

content = content.replace(
    '{"id": "enrollment_funnel", "type": "bar", "label": "قمع التسجيل"}',
    '{"id": "enrollment_funnel", "type": "bar", "label_ar": "قمع التسجيل", "label_en": "Enrollment Funnel"}'
)
content = content.replace(
    '{"id": "source_breakdown", "type": "doughnut", "label": "توزيع المصادر"}',
    '{"id": "source_breakdown", "type": "doughnut", "label_ar": "توزيع المصادر", "label_en": "Source Breakdown"}'
)

content = content.replace(
    'warnings.append("تعذر تحميل بيانات التسجيل")',
    'warnings.append({"ar": "تعذر تحميل بيانات التسجيل", "en": "Failed to load enrollment data"})'
)

# full_audit
content = content.replace(
    '{"id": "total_actions", "label": "إجمالي الإجراءات", "value": 0, "unit": ""}',
    '{"id": "total_actions", "label_ar": "إجمالي الإجراءات", "label_en": "Total Actions", "value": 0, "unit": ""}'
)
content = content.replace(
    '{"id": "failed_actions", "label": "إجراءات فاشلة", "value": 0, "unit": ""}',
    '{"id": "failed_actions", "label_ar": "إجراءات فاشلة", "label_en": "Failed Actions", "value": 0, "unit": ""}'
)

content = content.replace(
    '{"id": "actions_by_module", "type": "bar", "label": "حسب الوحدة"}',
    '{"id": "actions_by_module", "type": "bar", "label_ar": "حسب الوحدة", "label_en": "By Module"}'
)

content = content.replace(
    'warnings.append("تعذر تحميل سجل التدقيق")',
    'warnings.append({"ar": "تعذر تحميل سجل التدقيق", "en": "Failed to load audit log data"})'
)

# general warning
content = content.replace(
    'warnings.append("لا توجد سجلات مطابقة للفلاتر المحددة")',
    'warnings.append({"ar": "لا توجد سجلات مطابقة للفلاتر المحددة", "en": "No records match the selected filters"})'
)

with open("analytics_service.py", "w", encoding="utf-8") as f:
    f.write(content)
