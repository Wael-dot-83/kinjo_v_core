import re

path = r'D:\Final Version\templates\admin_base.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# The new sidebar structure. Grouping the requested items logically.
# Requested items:
# 1. لوحة التحكم العامة
# 2. المستخدمون
# 3. التواصل
# 4. إدارة البيانات
# 5. نظرة عامة على التحليلات
# 6. التقارير المفصلة
# 7. التقارير اليومية
# 8. جدولة التقارير
# 9. الحوادث
# 10. نظرة عامة على الخريطة
# 11. تحليل المحافظات
# 12. الحوكمة
# 13. الأمان
# 14. الإعدادات
# 15. المراقبة والأداء

new_sidebar_sections = """{% set sidebar_sections = [
            {
              "id": "main",
              "icon": "bi-grid",
              "label_ar": "الرئيسية",
              "label_en": "Main",
              "items": [
                {"href": "/admin/dashboard", "icon": "bi-speedometer2", "label_ar": "لوحة التحكم العامة", "label_en": "General Dashboard", "active_paths": ["/admin/dashboard"]},
                {"href": "/admin/heatmap", "icon": "bi-globe", "label_ar": "نظرة عامة على الخريطة", "label_en": "Map Overview", "active_paths": ["/admin/heatmap"]},
                {"href": "/admin/analytics", "icon": "bi-geo-alt", "label_ar": "تحليل المحافظات", "label_en": "Governorate Analysis", "active_paths": ["/admin/analytics"]}
              ]
            },
            {
              "id": "management",
              "icon": "bi-briefcase",
              "label_ar": "الإدارة والعمليات",
              "label_en": "Management",
              "items": [
                {"href": "/admin/users", "icon": "bi-people", "label_ar": "المستخدمون", "label_en": "Users", "active_paths": ["/admin/users"], "active_prefixes": ["/admin/users/"]},
                {"href": "/admin/messages", "icon": "bi-chat-dots", "label_ar": "التواصل", "label_en": "Communication", "active_paths": ["/admin/messages", "/admin/contact-messages"]},
                {"href": "/admin/imported-kindergartens", "icon": "bi-database", "label_ar": "إدارة البيانات", "label_en": "Data Management", "active_paths": ["/admin/imported-kindergartens", "/admin/import-kindergartens"]},
                {"href": "/admin/reports/incidents", "icon": "bi-exclamation-triangle", "label_ar": "الحوادث", "label_en": "Incidents", "active_paths": ["/admin/reports/incidents"]}
              ]
            },
            {
              "id": "reports",
              "icon": "bi-bar-chart-line",
              "label_ar": "التحليلات والتقارير",
              "label_en": "Analytics & Reports",
              "items": [
                {"href": "/admin/analytics", "icon": "bi-graph-up", "label_ar": "نظرة عامة على التحليلات", "label_en": "Analytics Overview", "active_paths": ["/admin/analytics"]},
                {"href": "/admin/analytics/reports", "icon": "bi-file-earmark-text", "label_ar": "التقارير المفصلة", "label_en": "Detailed Reports", "active_paths": ["/admin/analytics/reports"]},
                {"href": "/admin/analytics/daily-reports", "icon": "bi-calendar-day", "label_ar": "التقارير اليومية", "label_en": "Daily Reports", "active_paths": ["/admin/analytics/daily-reports"]},
                {"href": "/admin/daily-reports-organization", "icon": "bi-calendar-check", "label_ar": "جدولة التقارير", "label_en": "Report Scheduling", "active_paths": ["/admin/daily-reports-organization"]}
              ]
            },
            {
              "id": "system",
              "icon": "bi-sliders",
              "label_ar": "النظام والحوكمة",
              "label_en": "System",
              "items": [
                {"href": "/admin/governance-reports", "icon": "bi-clipboard-data", "label_ar": "الحوكمة", "label_en": "Governance", "active_paths": ["/admin/governance-reports"]},
                {"href": "/admin/audit-logs", "icon": "bi-shield-check", "label_ar": "الأمان", "label_en": "Security", "active_paths": ["/admin/audit-logs", "/admin/alerts"]},
                {"href": "/admin/observability", "icon": "bi-activity", "label_ar": "المراقبة والأداء", "label_en": "Monitoring & Performance", "active_paths": ["/admin/observability"]},
                {"href": "/admin/settings", "icon": "bi-gear", "label_ar": "الإعدادات", "label_en": "Settings", "active_paths": ["/admin/settings"]}
              ]
            }
          ] %}"""

# Use a regular expression to match from `{% set sidebar_sections = [` to `] %}`
# Note: re.DOTALL makes `.` match newlines.
content = re.sub(r'\{% set sidebar_sections = \[\s*\{.*?\s*\] %\}', new_sidebar_sections, content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Sidebar successfully reorganized.")
