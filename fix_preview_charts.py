import re

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. ATTENDANCE
    old_att = """            kpis[0]["value"] = total_present
            kpis[1]["value"] = total_absent
            kpis[2]["value"] = summary.attendance_rate
            kpis[3]["value"] = round(100 - summary.attendance_rate, 2)
            total_records = total_present + total_absent"""
            
    new_att = """            kpis[0]["value"] = total_present
            kpis[1]["value"] = total_absent
            kpis[2]["value"] = summary.attendance_rate
            kpis[3]["value"] = round(100 - summary.attendance_rate, 2)
            total_records = total_present + total_absent
            
            from sqlalchemy import func
            trend_q = db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT
            )
            if kg_filter:
                trend_q = trend_q.join(models.Class).filter(models.Class.kindergarten_id.in_(kg_filter))
            trend_data = trend_q.group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()
            charts[0]["data"] = {
                "labels": [str(row[0]) for row in trend_data],
                "datasets": [{"label": "Present", "data": [row[1] for row in trend_data], "borderColor": "#0d6efd", "backgroundColor": "rgba(13, 110, 253, 0.1)", "fill": True}]
            }
            
            gov_q = db.query(models.Kindergarten.governorate, func.count(models.AttendanceLog.id)).join(
                models.Class, models.AttendanceLog.class_id == models.Class.id
            ).join(models.Kindergarten, models.Class.kindergarten_id == models.Kindergarten.id).filter(
                models.AttendanceLog.date >= period_start, models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([models.AttendanceStatus.ABSENT, models.AttendanceStatus.EXCUSED_ABSENCE])
            )
            if kg_filter: gov_q = gov_q.filter(models.Kindergarten.id.in_(kg_filter))
            gov_data = gov_q.group_by(models.Kindergarten.governorate).all()
            from config import settings
            charts[1]["data"] = {
                "labels": [settings.JORDAN_GOVERNORATE_ALIASES.get(row[0].lower(), row[0]) if row[0] else "Unknown" for row in gov_data],
                "datasets": [{"label": "Absences", "data": [row[1] for row in gov_data], "backgroundColor": "#dc3545"}]
            }"""
    content = content.replace(old_att, new_att)

    # 2. INCIDENTS
    old_inc = """        try:
            breakdown = AnalyticsService.get_governorate_breakdown(db, period_start, period_end, gov_filter, kg_filter, None)
            total_inc = sum(getattr(b, "incident_rate", 0) for b in breakdown)
            kpis[0]["value"] = int(total_inc)
            total_records = int(total_inc)"""
            
    new_inc = """        try:
            from sqlalchemy import func
            inc_base = db.query(models.Incident).filter(
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) >= period_start,
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) <= period_end
            )
            if kg_filter: inc_base = inc_base.filter(models.Incident.kindergarten_id.in_(kg_filter))
            
            kpis[0]["value"] = inc_base.count()
            kpis[1]["value"] = inc_base.filter(models.Incident.status == models.IncidentStatus.OPEN).count()
            kpis[2]["value"] = inc_base.filter(models.Incident.severity_level == models.SeverityLevel.CRITICAL).count()
            total_records = kpis[0]["value"]

            trend_data = db.query(func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)).label("d"), func.count(models.Incident.id)).filter(
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) >= period_start,
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) <= period_end
            )
            if kg_filter: trend_data = trend_data.filter(models.Incident.kindergarten_id.in_(kg_filter))
            trend_data = trend_data.group_by("d").order_by("d").all()
            charts[0]["data"] = {
                "labels": [str(row[0]) for row in trend_data],
                "datasets": [{"label": "Incidents", "data": [row[1] for row in trend_data], "borderColor": "#dc3545", "backgroundColor": "rgba(220, 53, 69, 0.1)", "fill": True}]
            }

            sev_data = inc_base.with_entities(models.Incident.severity_level, func.count(models.Incident.id)).group_by(models.Incident.severity_level).all()
            charts[1]["data"] = {
                "labels": [row[0].value if hasattr(row[0], 'value') else str(row[0]) for row in sev_data],
                "datasets": [{"label": "Severity", "data": [row[1] for row in sev_data], "backgroundColor": ["#0d6efd", "#ffc107", "#fd7e14", "#dc3545"]}]
            }"""
    content = content.replace(old_inc, new_inc)

    # 3. COMPLIANCE
    old_comp = """            total = max(dist.green + dist.amber + dist.red, 1)
            total_records = total
            
            # Use dynamic quality evaluation
            data_quality["completeness_percent"] = 100.0 if count > 0 else 0.0"""
            
    new_comp = """            total = max(dist.green + dist.amber + dist.red, 1)
            total_records = total
            
            charts[0]["data"] = {
                "labels": ["Green", "Amber", "Red"],
                "datasets": [{"data": [dist.green, dist.amber, dist.red], "backgroundColor": ["#198754", "#ffc107", "#dc3545"]}]
            }
            
            # Use dynamic quality evaluation
            data_quality["completeness_percent"] = 100.0 if count > 0 else 0.0"""
    content = content.replace(old_comp, new_comp)

    # 4. ENROLLMENT
    old_enr = """            kpis[0]["value"] = analytics.get("total_applications", 0)
            kpis[1]["value"] = analytics.get("status_breakdown", {}).get("ACCEPTED", 0)
            kpis[2]["value"] = analytics.get("status_breakdown", {}).get("REJECTED", 0)
            total_records = analytics.get("total_applications", 0)"""
            
    new_enr = """            kpis[0]["value"] = analytics.get("total_applications", 0)
            kpis[1]["value"] = analytics.get("status_breakdown", {}).get("ACCEPTED", 0)
            kpis[2]["value"] = analytics.get("status_breakdown", {}).get("REJECTED", 0)
            total_records = analytics.get("total_applications", 0)
            
            charts[0]["data"] = {
                "labels": ["Total", "Approved", "Rejected"],
                "datasets": [{"label": "Applications", "data": [total_records, kpis[1]["value"], kpis[2]["value"]], "backgroundColor": ["#0d6efd", "#198754", "#dc3545"]}]
            }
            
            from sqlalchemy import func
            source_q = db.query(models.EnrollmentApplication.source, func.count(models.EnrollmentApplication.id)).filter(
                func.date(models.EnrollmentApplication.created_at) >= period_start,
                func.date(models.EnrollmentApplication.created_at) <= period_end
            )
            if kg_filter: source_q = source_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
            source_data = source_q.group_by(models.EnrollmentApplication.source).all()
            charts[1]["data"] = {
                "labels": [row[0].value if hasattr(row[0], 'value') else str(row[0]) for row in source_data],
                "datasets": [{"data": [row[1] for row in source_data], "backgroundColor": ["#6610f2", "#0dcaf0", "#ffc107", "#20c997"]}]
            }"""
    content = content.replace(old_enr, new_enr)

    # 5. AUDIT
    old_aud = """            kpis[0]["value"] = total
            kpis[1]["value"] = failed
            total_records = total"""
            
    new_aud = """            kpis[0]["value"] = total
            kpis[1]["value"] = failed
            total_records = total
            
            from sqlalchemy import func
            mod_data = query.with_entities(models.AuditLog.module_name, func.count(models.AuditLog.id)).group_by(models.AuditLog.module_name).all()
            charts[0]["data"] = {
                "labels": [row[0] for row in mod_data],
                "datasets": [{"label": "Actions", "data": [row[1] for row in mod_data], "backgroundColor": "#6c757d"}]
            }"""
    content = content.replace(old_aud, new_aud)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("Patched successfully!")

if __name__ == "__main__":
    patch_file(r"D:\Final Version\analytics_service.py")
