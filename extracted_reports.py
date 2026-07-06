# Admin Incident Reporting Endpoints
# =============================================================================

@router.post("/incidents/generate")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def generate_incident_report(
    request: Request,
    scope_type: str = Form(...),
    kindergarten_id: Optional[int] = Form(None),
    governorate: Optional[str] = Form(None),
    period_type: str = Form(...),
    year: Optional[int] = Form(None),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Generate and save an incident report"""
    try:
        # Validate scope
        try:
            scope_enum = models.ReportScopeType(scope_type)
        except ValueError:
            raise validation_error("Invalid scope type")

        # Calculate date range
        from report_service import ReportService
        reference_date = date(year, 1, 1) if period_type == "annual" and year else None
        start_date, end_date = ReportService.calculate_date_range(period_type, reference_date)

        # Generate metrics
        metrics = ReportService.generate_incident_report(
            scope_enum, start_date, end_date, kindergarten_id, governorate, db
        )

        # Create report record
        report = models.Report(
            report_type=models.ReportType.INCIDENT_SUMMARY,
            scope_type=scope_enum,
            kindergarten_id=kindergarten_id,
            governorate=governorate,
            start_date=start_date,
            end_date=end_date,
            metrics_json=metrics,
            created_by=current_user.id
        )

        db.add(report)
        db.commit()
        db.refresh(report)

        log_audit_event(
            db, AuditAction.REPORT_GENERATED, current_user, "report",
            target_ids=report.id,
            metadata={
                "description": f"Generated incident report ID {report.id} for scope {scope_type}",
                "correlation_id": get_correlation_id()
            }
        )

        return JSONResponse({
            "success": True,
            "report_id": report.id,
            "message": "تم إنشاء التقرير بنجاح"
        })

    except HTTPException:
        db.rollback()
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to generate incident report: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_incident_reports(
    request: Request,
    scope_filter: Optional[str] = Query(None, description="Filter by scope type: KINDERGARTEN, GOVERNORATE, ALL"),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List incident reports with filtering"""
    try:
        query = db.query(models.Report).options(
            selectinload(models.Report.kindergarten),
            selectinload(models.Report.creator),
        ).filter(
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        )

        # Apply scope filters
        if scope_filter:
            try:
                scope_enum = models.ReportScopeType(scope_filter)
                query = query.filter(models.Report.scope_type == scope_enum)
            except ValueError:
                raise validation_error("Invalid scope filter")

        if kindergarten_id:
            query = query.filter(models.Report.kindergarten_id == kindergarten_id)

        if governorate:
            query = query.filter(models.Report.governorate == governorate)

        # Pagination
        total = query.count()
        reports = query.order_by(models.Report.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        # Format response
        report_list = []
        for report in reports:
            scope_name = ""
            if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
                scope_name = report.kindergarten.name_ar
            elif report.scope_type == models.ReportScopeType.GOVERNORATE:
                scope_name = report.governorate
            elif report.scope_type == models.ReportScopeType.ALL:
                scope_name = "جميع الحضانات"

            report_list.append({
                "id": report.id,
                "title": f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
                "scope_type": report.scope_type.value,
                "scope_name": scope_name,
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
                "created_at": report.created_at.isoformat(),
                "created_by": report.creator.username if report.creator else "غير معروف",
                "total_incidents": report.metrics_json.get("total_incidents", 0)
            })

        return {
            "reports": report_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to list incident reports: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents/{report_id}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_incident_report_detail(
    report_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get detailed incident report"""
    try:
        report = db.query(models.Report).filter(
            models.Report.id == report_id,
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        ).first()

        if not report:
            raise not_found_error("Report not found")

        # Format scope name
        scope_name = ""
        if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
            scope_name = report.kindergarten.name_ar
        elif report.scope_type == models.ReportScopeType.GOVERNORATE:
            scope_name = report.governorate
        elif report.scope_type == models.ReportScopeType.ALL:
            scope_name = "جميع الحضانات"

        return {
            "id": report.id,
            "title": f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
            "scope_type": report.scope_type.value,
            "scope_name": scope_name,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "created_at": report.created_at.isoformat(),
            "created_by": report.creator.username if report.creator else "غير معروف",
            "metrics": report.metrics_json
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get incident report detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents/{report_id}/export")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def export_incident_report_csv(
    report_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Export incident report as CSV"""
    try:
        report = db.query(models.Report).filter(
            models.Report.id == report_id,
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        ).first()

        if not report:
            raise not_found_error("Report not found")

        # Generate CSV content
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        report_title = f"{report.report_type.value.replace('_', ' ').title()} - {report.scope_type.value.title()}"
        writer.writerow(['Report Title', report_title])
        writer.writerow(['Scope', report.scope_type.value])
        writer.writerow(['Start Date', report.start_date.isoformat()])
        writer.writerow(['End Date', report.end_date.isoformat()])
        writer.writerow(['Generated By', report.creator.username if report.creator else 'Unknown'])
        writer.writerow(['Generated At', report.created_at.isoformat()])
        writer.writerow([])

        # Write metrics
        metrics = report.metrics_json
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Incidents', metrics.get('total_incidents', 0)])
        writer.writerow(['Open Incidents', metrics.get('open_incidents', 0)])
        writer.writerow(['Closed Incidents', metrics.get('closed_incidents', 0)])
        writer.writerow([])

        # Incidents by type
        writer.writerow(['Incidents by Type'])
        writer.writerow(['Type', 'Count'])
        for type_name, count in metrics.get('incidents_by_type', {}).items():
            writer.writerow([type_name, count])
        writer.writerow([])

        # Incidents by severity
        writer.writerow(['Incidents by Severity'])
        writer.writerow(['Severity', 'Count'])
        for severity, count in metrics.get('incidents_by_severity', {}).items():
            writer.writerow([severity, count])
        writer.writerow([])

        # Per kindergarten (if applicable)
        per_kg = metrics.get('per_kindergarten', {})
        if per_kg:
            writer.writerow(['Incidents by Kindergarten'])
            writer.writerow(['Kindergarten', 'Count'])
            for kg, count in per_kg.items():
                writer.writerow([kg, count])

        csv_content = output.getvalue()
        output.close()

        log_audit_event(
            db=db,
            action=AuditAction.INCIDENT_REPORT_EXPORT,
            actor=current_user,
            target_type="Report",
            target_ids=report.id,
            metadata={
                "format": "csv",
                "report_type": report.report_type.value,
                "scope_type": report.scope_type.value,
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
            },
            sensitivity_level=2,
        )

        # Return CSV file
        filename = f"incident_report_{report_id}_{report.created_at.date().isoformat()}.csv"
        return Response(
            csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except (SQLAlchemyError, ValueError, IOError, OSError) as e:
        log_audit_event(
            db=db,
            action=AuditAction.INCIDENT_REPORT_EXPORT_FAILED,
            actor=current_user,
            target_type="Report",
            target_ids=report_id,
            metadata={"format": "csv", "error_message": str(e)},
            sensitivity_level=3,
        )
        logger.error(f"Failed to export incident report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scopes")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_available_scopes(
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get available report scopes for the current user"""
    try:
        from report_service import ReportService
        scopes = ReportService.get_available_scopes(current_user, db)
        return {"scopes": scopes}

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get available scopes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Admin Alerts API
# =============================================================================

class AdminAlertResponse(BaseModel):
    id: int
    severity: str
    governorate: Optional[str] = None
    kindergarten_name: Optional[str] = None
    metric: str
    current_value: float
    threshold: Optional[float] = None
    triggered_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by_id: Optional[int] = None
    status: str
    message: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None


class AdminAlertsListResponse(BaseModel):
    alerts: List[AdminAlertResponse]
    total: int
    page: int
    page_size: int
