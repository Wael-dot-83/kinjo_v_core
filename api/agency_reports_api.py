"""Admin Official Agency Reports API.

Mounted in main.py under /api (no /api/admin prefix), yielding paths such as:
/api/admin/agency-reports/catalog

The router's internal route paths already include the /admin/agency-reports
prefix, so mounting under /api produces the expected /api/admin/agency-reports/...
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

import immunization_service
import models
from admin_security import log_audit_event
from audit_actions import AuditAction
from services.agency_reports.exporter import custom_report_to_csv, to_csv, to_json, to_xlsx
from agency_reports_service import AgencyReportError, AgencyReportsService
from services.agency_reports.registry import get_agency_service
from config import settings
from database import get_db
from dependencies import get_current_user, Permission, has_permission
from upload_security import validate_xlsx_archive

router = APIRouter(tags=["Admin Agency Reports"])


def _require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not has_permission(current_user, Permission.ADMIN_PANEL):
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def _filters(
    request: Request,
    admission_year: Optional[int] = None,
    period: Optional[str] = None,
    year: Optional[str] = None,
    quarter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
    district: Optional[str] = None,
    area: Optional[str] = None,
    kindergarten_id: Optional[int] = None,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    enrollment_status: Optional[str] = None,
    aggregation_level: Optional[str] = Query(default="governorate"),
    geography_basis: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> dict:
    resolved_city = city or district
    return {
        "admission_year": admission_year,
        "period": period,
        "year": year,
        "quarter": quarter,
        "date_from": date_from,
        "date_to": date_to,
        "governorate": governorate,
        "city": resolved_city,
        "district": resolved_city,
        "area": area,
        "kindergarten_id": kindergarten_id,
        "gender": gender,
        "age_group": age_group,
        "enrollment_status": enrollment_status,
        "aggregation_level": aggregation_level,
        "geography_basis": geography_basis,
        "status": status,
        "severity": severity,
    }


@router.get("/admin/agency-reports/catalog")
def agency_report_catalog(
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return AgencyReportsService(db).catalog()


@router.get("/admin/agency-reports/summary")
def agency_report_summary(
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return AgencyReportsService(db).summary()


@router.get("/admin/agency-reports/governance/overview")
def agency_report_governance_overview(
    governorate: Optional[str] = Query(default=None),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Governance KPI overview for the NCFA report sidebar.

    Returns the Governance Quality Index (GQI) and submission/delivery/view
    rates for the selected governorate (or national if no governorate given).
    Pulled from governance_scores when available, falling back to live
    computation via governance_kpi_service.
    """
    from datetime import date, timedelta
    from governance_kpi_service import compute_governance_funnel

    today = date.today()
    start = today - timedelta(days=30)

    # Try cached governance scores first
    q = db.query(models.GovernanceScore).filter(
        models.GovernanceScore.period_end >= start,
        models.GovernanceScore.period_start <= today,
    )
    if governorate:
        q = q.join(models.Kindergarten, models.Kindergarten.id == models.GovernanceScore.kindergarten_id)
        q = q.filter(models.Kindergarten.governorate == governorate)

    scores = q.all()
    if scores:
        gqi_values = [s.governance_quality_index for s in scores if s.governance_quality_index is not None]
        avg_gqi = sum(gqi_values) / len(gqi_values) if gqi_values else 0
        return {
            "source": "cache",
            "governorate": governorate or "national",
            "period_start": start.isoformat(),
            "period_end": today.isoformat(),
            "gqi": round(avg_gqi, 2),
            "kindergarten_count": len(scores),
        }

    # Fall back to live computation
    funnel = compute_governance_funnel(db, start, today)
    totals = funnel.get("totals", {})
    required = totals.get("required", 0)
    submitted = totals.get("submitted", 0)
    delivered = totals.get("delivered", 0)
    viewed = totals.get("viewed", 0)

    return {
        "source": "live",
        "governorate": governorate or "national",
        "period_start": start.isoformat(),
        "period_end": today.isoformat(),
        "submission_rate": round(submitted / required * 100, 1) if required else None,
        "delivery_rate": round(delivered / submitted * 100, 1) if submitted else None,
        "view_rate": round(viewed / delivered * 100, 1) if delivered else None,
        "required": required,
        "submitted": submitted,
        "delivered": delivered,
        "viewed": viewed,
        "kindergarten_count": funnel.get("kindergarten_count", 0),
    }


# ---------------------------------------------------------------------------
# MOH national immunization schedule (powers vaccination_due_children)
# Declared before the parametrised /{agency_code}/reports routes.
# ---------------------------------------------------------------------------
@router.get("/admin/agency-reports/moh/immunization-schedule/template")
def immunization_schedule_template(
    current_user: models.User = Depends(_require_admin),
):
    data = immunization_service.build_template_xlsx()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="immunization_schedule_template.xlsx"'},
    )


@router.get("/admin/agency-reports/moh/immunization-schedule")
def immunization_schedule_current(
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    rows = immunization_service.get_schedule(db)
    return {
        "success": True,
        "count": len(rows),
        "rows": [
            {
                "id": r.id,
                "vaccine_name": r.vaccine_name,
                "age_value": r.age_value,
                "age_unit": r.age_unit.value,
                "age_unit_ar": immunization_service.unit_label_ar(r.age_unit),
                "due_age_days": r.due_age_days,
                "notes": r.notes,
            }
            for r in rows
        ],
    }


@router.post("/admin/agency-reports/moh/immunization-schedule")
def immunization_schedule_upload(
    file: UploadFile = File(...),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="يجب أن يكون الملف بصيغة Excel (.xlsx)")
    max_upload = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_upload:
        raise HTTPException(
            status_code=413, detail=f"حجم الملف يتجاوز الحد المسموح ({settings.MAX_UPLOAD_SIZE_MB} ميجابايت)"
        )
    raw = file.file.read()
    validate_xlsx_archive(raw, max_compressed_bytes=max_upload)
    if not raw:
        raise HTTPException(status_code=400, detail="الملف فارغ")
    try:
        rows, errors = immunization_service.parse_schedule_xlsx(raw)
    except immunization_service.ImmunizationScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        detail = "لم يتم العثور على صفوف صالحة في الملف."
        if errors:
            detail += " " + " | ".join(errors[:10])
        raise HTTPException(status_code=422, detail=detail)

    written = immunization_service.replace_schedule(db, rows, current_user.id)
    log_audit_event(
        db,
        AuditAction.IMMUNIZATION_SCHEDULE_UPLOAD,
        current_user,
        target_type="NationalImmunizationSchedule",
        after_state={"rows": written, "filename": file.filename},
        metadata={"skipped_rows": len(errors)},
        sensitivity_level=1,
    )
    db.commit()
    return {
        "success": True,
        "imported": written,
        "skipped": len(errors),
        "errors": errors[:20],
        "message_ar": f"تم رفع الجدول: {written} مطعوم." + (f" (تم تجاهل {len(errors)} صف)" if errors else ""),
    }


@router.get("/admin/agency-reports/{agency_code}/reports")
def agency_reports_for_agency(
    agency_code: str,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        return AgencyReportsService(db).reports_for_agency(agency_code)
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/admin/agency-reports/{agency_code}/reports/{report_code}")
def agency_report_detail(
    agency_code: str,
    report_code: str,
    request: Request,
    admission_year: Optional[int] = None,
    period: Optional[str] = None,
    year: Optional[str] = None,
    quarter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
    district: Optional[str] = None,
    area: Optional[str] = None,
    kindergarten_id: Optional[int] = None,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    enrollment_status: Optional[str] = None,
    aggregation_level: Optional[str] = Query(default="governorate"),
    geography_basis: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        return AgencyReportsService(db).generate_report(
            agency_code,
            report_code,
            _filters(
                request,
                admission_year,
                period,
                year,
                quarter,
                date_from,
                date_to,
                governorate,
                city,
                district,
                area,
                kindergarten_id,
                gender,
                age_group,
                enrollment_status,
                aggregation_level,
                geography_basis,
                status,
                severity,
            ),
        )
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _audit_export(db, actor, agency, report, fmt, extra=None):
    """Record an audit event for an agency-report export (actor, report, scope,
    format) so every data export is accountable."""
    metadata = {"agency": agency, "format": fmt}
    if report:
        metadata["report"] = report
    if extra:
        metadata.update({k: v for k, v in extra.items() if v is not None})
    log_audit_event(
        db,
        AuditAction.AGENCY_REPORT_EXPORT,
        actor,
        target_type="AgencyReport",
        metadata=metadata,
        sensitivity_level=1,
    )
    db.commit()


@router.get("/admin/agency-reports/{agency_code}/reports/{report_code}/export.json")
def agency_report_export_json(
    agency_code: str,
    report_code: str,
    request: Request,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = AgencyReportsService(db).generate_report(agency_code, report_code, dict(request.query_params))
        _audit_export(db, current_user, agency_code, report_code, "json", dict(request.query_params))
        return JSONResponse(content=payload)
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/admin/agency-reports/{agency_code}/reports/{report_code}/export.csv")
def agency_report_export_csv(
    agency_code: str,
    report_code: str,
    request: Request,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = AgencyReportsService(db).generate_report(agency_code, report_code, dict(request.query_params))
        if not payload.get("exports", {}).get("csv"):
            raise HTTPException(status_code=409, detail="CSV export is not available for this report")
        csv_payload = to_csv(payload)
        _audit_export(db, current_user, agency_code, report_code, "csv", dict(request.query_params))
        filename = f"agency_report_{agency_code}_{report_code}.csv"
        return Response(
            content="\ufeff" + csv_payload,  # UTF-8 BOM for Arabic Excel compatibility (CHART-003)
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/admin/agency-reports/{agency_code}/reports/{report_code}/export")
def agency_report_export_unified(
    agency_code: str,
    report_code: str,
    request: Request,
    fmt: str = Query(default="csv", pattern="^(csv|json|xlsx)$"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Unified export endpoint: ?format=csv|json|xlsx

    Consolidates the separate .csv and .json export routes into one endpoint
    with a query-parameter format selector. The legacy .csv and .json suffix
    routes are preserved as compatibility aliases.
    """
    try:
        payload = AgencyReportsService(db).generate_report(agency_code, report_code, dict(request.query_params))
        _audit_export(db, current_user, agency_code, report_code, fmt, dict(request.query_params))
        if fmt == "json":
            return JSONResponse(content=payload)
        if fmt == "xlsx":
            xlsx_bytes = to_xlsx(payload)
            filename = f"agency_report_{agency_code}_{report_code}.xlsx"
            return Response(
                content=xlsx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        # Default: CSV
        if not payload.get("exports", {}).get("csv"):
            raise HTTPException(status_code=409, detail="CSV export is not available for this report")
        csv_payload = to_csv(payload)
        filename = f"agency_report_{agency_code}_{report_code}.csv"
        return Response(
            content="\ufeff" + csv_payload,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/admin/agency-reports/custom/schema")
def custom_report_schema(
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": AgencyReportsService(db).custom_report_schema()}


@router.post("/admin/agency-reports/custom")
def custom_report(
    scope: dict = Body(...),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        # Admin surface: always show the real, complete values — no small-cell
        # suppression anywhere an authorized admin reviews the data.
        return {"success": True, "data": AgencyReportsService(db).custom_report(scope, suppress=False)}
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/admin/agency-reports/custom/export.csv")
def custom_report_export_csv(
    scope: dict = Body(...),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        # Admin export: same complete data as the on-screen view (suppress=False)
        # so downloaded CSVs never contain masked ("محجوب") cells.
        payload = AgencyReportsService(db).custom_report(scope, suppress=False)
        csv_payload = custom_report_to_csv(payload)
        _scope = payload.get("scope", {})
        _audit_export(
            db,
            current_user,
            _scope.get("agency"),
            None,
            "csv",
            {
                "level": _scope.get("level"),
                "period": _scope.get("period"),
                "governorate": _scope.get("governorate"),
                "city": _scope.get("city"),
                "start_date": _scope.get("start_date"),
                "end_date": _scope.get("end_date"),
            },
        )
        filename = "custom_agency_report.csv"
        return Response(
            content="\ufeff" + csv_payload,  # UTF-8 BOM for Arabic Excel compatibility (CHART-003)
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
