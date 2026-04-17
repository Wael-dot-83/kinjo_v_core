# api/reports/constants.py

REPORT_STATUS_DISPLAY = {
    "received": "تم استلامه من قبل الوالدين",
    "pending": "بانتظار مراجعة المدير",
    "incomplete": "غير مكتمل",
    "absent": "غير مملوء – غياب الطفل",
    "not_submitted": "غير مملوء – لم يقدم المشرف/المعلم",
}

REPORT_STATUS_UI_METADATA = {
    "received": {
        "label": "تم استلامه من قبل الوالدين",
        "color_class": "text-success",
        "bg_class": "bg-success-subtle",
        "icon": "fas fa-check-circle",
        "sort_priority": 1,
        "color": "#4CAF50"
    },
    "pending": {
        "label": "بانتظار مراجعة المدير",
        "color_class": "text-warning",
        "bg_class": "bg-warning-subtle",
        "icon": "fas fa-clock",
        "sort_priority": 2,
        "color": "#FFC107"
    },
    "incomplete": {
        "label": "غير مكتمل",
        "color_class": "text-info",
        "bg_class": "bg-info-subtle",
        "icon": "fas fa-exclamation-triangle",
        "sort_priority": 3,
        "color": "#EF5350"
    },
    "absent": {
        "label": "غير مملوء – غياب الطفل",
        "color_class": "text-danger",
        "bg_class": "bg-danger-subtle",
        "icon": "fas fa-user-slash",
        "sort_priority": 4,
        "color": "#D32F2F"
    },
    "not_submitted": {
        "label": "غير مملوء – لم يقدم المشرف/المعلم",
        "color_class": "text-secondary",
        "bg_class": "bg-secondary-subtle",
        "icon": "fas fa-file-excel",
        "sort_priority": 5,
        "color": "#C62828"
    }
}

# For dropdowns / choices if needed
REPORT_STATUS_CHOICES = [(k, v) for k, v in REPORT_STATUS_DISPLAY.items()]