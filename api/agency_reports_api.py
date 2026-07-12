"""Admin Official Agency Reports API.

Mounted through api.missing_endpoints wrapper under /api, yielding paths such as:
/api/admin/agency-reports/catalog
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

import immunization_service
import models
from admin_security import log_audit_event
from audit_actions import AuditAction
from agency_reports_export import custom_report_to_csv, to_csv
from agency_reports_service import AgencyReportError, AgencyReportsService
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Admin Agency Reports"])


def _require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def _filters(
    request: Request,
    admission_year: Optional[int] = None,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
    kindergarten_id: Optional[int] = None,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    enrollment_status: Optional[str] = None,
    aggregation_level: Optional[str] = Query(default="governorate"),
    geography_basis: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> dict:
    return {
        "admission_year": admission_year,
        "period": period,
        "date_from": date_from,
        "date_to": date_to,
        "governorate": governorate,
        "city": city,
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
    raw = file.file.read()
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
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
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
        return AgencyReportsService(db).generate_report(agency_code, report_code, _filters(request, admission_year, period, date_from, date_to, governorate, city, kindergarten_id, gender, age_group, enrollment_status, aggregation_level, geography_basis, status, severity))
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


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
        filename = f"agency_report_{agency_code}_{report_code}.csv"
        return Response(
            content=csv_payload,
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
    scope: dict[str, Any],
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        return {"success": True, "data": AgencyReportsService(db).custom_report(scope)}
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/admin/agency-reports/custom/export.csv")
def custom_report_export_csv(
    scope: dict[str, Any],
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = AgencyReportsService(db).custom_report(scope)
        csv_payload = custom_report_to_csv(payload)
        filename = "custom_agency_report.csv"
        return Response(
            content=csv_payload,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AgencyReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
