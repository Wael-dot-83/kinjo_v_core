@router.post("/export")
def export_analytics_data(
    request: ExportRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export analytics reports (CSV).
    """
    validators.validate_admin_role(current_user)

    # Extract dates from filters if present
    start_str = request.filters.get("period_start") if request.filters else None
    end_str = request.filters.get("period_end") if request.filters else None
    
    if not start_str or not end_str:
         # Default to last 30 days if not provided
         end_date = date.today()
         start_date = end_date - timedelta(days=30)
    else:
        try:
            start_date = datetime.strptime(str(start_str), "%Y-%m-%d").date()
            end_date = datetime.strptime(str(end_str), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    import csv
    import io
    from fastapi.responses import Response

    output = io.StringIO()
    writer = csv.writer(output)

    if request.report_type == "attendance":
        writer.writerow(["Kindergarten", "Children Count", "Capacity", "Attendance Rate %"])
        # Re-use governorate breakdown or network summary logic? 
        # Better to iterate all KGs for a detailed report
        kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        for kg in kgs:
            rate = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
            # Fetch other metrics if needed
            writer.writerow([kg.name_ar, len(kg.enrollments), "N/A", rate])

    elif request.report_type == "incidents":
        writer.writerow(["Date", "Kindergarten", "Type", "Severity", "Description", "Child"])
        incidents = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= start_date,
            func.date(models.Incident.occurred_at) <= end_date
        ).all()
        for inc in incidents:
            writer.writerow([
                inc.occurred_at.strftime("%Y-%m-%d"),
                inc.kindergarten.name_ar,
                inc.type.value,
                inc.severity_level.value,
                inc.description,
                f"{inc.child.first_name} {inc.child.last_name}"
            ])

    elif request.report_type == "compliance":
        writer.writerow(["Kindergarten", "Ratio Compliance %", "Governance Score"])
        kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        for kg in kgs:
            ratio = KPIService.compute_ratio_compliance(db, kg.id, start_date, end_date)
            # Governance Score logic might be complex, verify if exists in KPIService
            # KPIService.compute_governance_score returns (score, band)
            gov_score, _ = KPIService.compute_governance_score(db, kg.id, start_date, end_date)
            writer.writerow([kg.name_ar, ratio, gov_score])

    elif request.report_type == "full_audit":
        writer.writerow(["Timestamp", "User", "Action", "Entity", "Details", "IP"])
        logs = db.query(models.AuditLog).filter(
             func.date(models.AuditLog.created_at) >= start_date,
             func.date(models.AuditLog.created_at) <= end_date
        ).order_by(desc(models.AuditLog.created_at)).all()
        
        # Pre-fetch users to avoid N+1
        user_map = {u.id: u.username for u in db.query(models.User).all()}
        
        for log in logs:
            username = user_map.get(log.user_id, "Unknown")
            writer.writerow([
                log.created_at,
                username,
                log.action,
                log.entity_type,
                log.details,
                log.ip_address
            ])

    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    filename = f"{request.report_type}_report_{start_date}_{end_date}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
