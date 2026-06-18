# -*- coding: utf-8 -*-
"""Round 3: replace Font Awesome icon classes with Bootstrap Icons equivalents
across the 27 admin templates that still use Font Awesome, so the whole app
is on one consistent icon system (Bootstrap Icons — already the dominant
choice: 107 templates / 233 distinct glyphs vs. Font Awesome's 27 / 58)."""
import io
import re
import sys

ICON_MAP = {
    "home": "house",
    "chevron-down": "chevron-down",
    "upload": "upload",
    "triangle-exclamation": "exclamation-triangle",
    "inbox": "inbox",
    "rotate-right": "arrow-clockwise",
    "history": "clock-history",
    "users": "people",
    "globe": "globe",
    "file-import": "file-earmark-arrow-down",
    "envelope": "envelope",
    "download": "download",
    "database": "database",
    "comments": "chat-dots",
    "clock-rotate-left": "clock-history",
    "circle-info": "info-circle",
    "circle-exclamation": "exclamation-circle",
    "check-circle": "check-circle",
    "chart-line": "graph-up",
    "chart-bar": "bar-chart",
    "bell": "bell",
    "xmark": "x-lg",
    "user-secret": "incognito",
    "user-plus": "person-plus",
    "user-circle": "person-circle",
    "user": "person",
    "trophy": "trophy",
    "tachometer-alt": "speedometer2",
    "sync-alt": "arrow-repeat",
    "spinner": "arrow-repeat",
    "sign-out-alt": "box-arrow-right",
    "shield-halved": "shield-check",
    "shield-alt": "shield-check",
    "school": "building",
    "redo": "arrow-clockwise",
    "question-circle": "question-circle",
    "plus": "plus-lg",
    "pen-to-square": "pencil-square",
    "map-marker-alt": "geo-alt",
    "map": "map",
    "list-ul": "list-ul",
    "list-check": "list-check",
    "list": "list",
    "filter": "funnel",
    "file-medical-alt": "file-medical",
    "file-lines": "file-text",
    "file-alt": "file-text",
    "eye": "eye",
    "exclamation-triangle": "exclamation-triangle",
    "envelopes-bulk": "envelope-paper",
    "cog": "gear",
    "clock": "clock",
    "clipboard-list": "clipboard-data",
    "clipboard-check": "clipboard-check",
    "check": "check-lg",
    "calendar-day": "calendar-day",
    "bars": "list",
    "balance-scale": "bank",
}

MODIFIER_MAP = {
    "fa-lg": "fs-4",
    "fa-2x": "fs-1",
    "fa-spin": "bi-spin",
}

FILES = """templates/admin/alerts.html
templates/admin/analytics/daily_reports.html
templates/admin/analytics/dashboard.html
templates/admin/analytics/drilldown.html
templates/admin/analytics/incident_reports_generate.html
templates/admin/analytics/incident_report_detail.html
templates/admin/analytics/reports.html
templates/admin/audit_logs.html
templates/admin/classification.html
templates/admin/contact_messages.html
templates/admin/daily_reports_organization.html
templates/admin/governance_reminders.html
templates/admin/governance_reports.html
templates/admin/heatmap.html
templates/admin/impersonate.html
templates/admin/imported_kindergartens.html
templates/admin/import_kindergartens.html
templates/admin/import_logs.html
templates/admin/import_users.html
templates/admin/incident_reports_list.html
templates/admin/messages/compose.html
templates/admin/messages/list.html
templates/admin/profile.html
templates/admin/safety_analytics.html
templates/admin/settings.html
templates/admin_base.html
templates/admin_dashboard.html""".strip().splitlines()

FA_CLASS_RE = re.compile(r"fa[srb]? fa-([a-z0-9-]+)")

unmapped = set()
total_replacements = 0

for relpath in FILES:
    with io.open(relpath, "r", encoding="utf-8-sig") as f:
        content = f.read()
    original = content

    def _replace(match):
        global total_replacements
        fa_name = match.group(1)
        bi_name = ICON_MAP.get(fa_name)
        if bi_name is None:
            unmapped.add(fa_name)
            return match.group(0)
        total_replacements += 1
        return f"bi bi-{bi_name}"

    content = FA_CLASS_RE.sub(_replace, content)

    for fa_mod, bs_mod in MODIFIER_MAP.items():
        content = content.replace(fa_mod, bs_mod)

    if content != original:
        with io.open(relpath, "w", encoding="utf-8-sig") as f:
            f.write(content)
        print(f"Updated: {relpath}")

print()
print("Total icon-class replacements:", total_replacements)
if unmapped:
    print("UNMAPPED fa- names (left untouched):", sorted(unmapped))
    sys.exit(1)
else:
    print("All Font Awesome icon classes mapped successfully.")
