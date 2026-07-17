from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from app.models.schemas import DOSReportFilters, ReportResponse
from admin_security import require_admin_role
from fastapi import Depends
from app.services.dos_reports_service import (
    get_dos_summary,
    get_children_demographics_report,
    get_enrollment_participation_36_59_report,
    get_institutions_report,
    get_capacity_occupancy_report,
    get_attendance_absence_report,
    get_supervisor_ratio_report,
    get_incident_safety_report,
    get_geographic_gaps_report,
    get_data_quality_report,
    get_trends_report,
)
from app.utils.export import export_csv, export_excel, export_pdf, export_json
from app.utils.filters import parse_filters

router = APIRouter(
    prefix="/admin/agency-reports",
    tags=["Admin DOS Reports"],
    dependencies=[Depends(require_admin_role)]
)

@router.get("/dos")
async def render_dos_page(request: Request):
    # In production, return a Jinja2 template response (placeholder here)
    html_content = "<html><body><h1>Admin DOS Reports (Arabic UI placeholder)</h1></body></html>"
    return Response(content=html_content, media_type="text/html")

@router.get("/dos", response_model=ReportResponse)
async def get_report(
    report_type: str = Query(..., description="Report identifier"),
    request: Request = None,
):
    filters = parse_filters(request)
    # Dispatch to the correct service function
    service_map = {
        "summary": get_dos_summary,
        "children_demographics": get_children_demographics_report,
        "enrollment_36_59": get_enrollment_participation_36_59_report,
        "institutions": get_institutions_report,
        "capacity_occupancy": get_capacity_occupancy_report,
        "attendance_absence": get_attendance_absence_report,
        "supervisors": get_supervisor_ratio_report,
        "incidents": get_incident_safety_report,
        "geo_gaps": get_geographic_gaps_report,
        "data_quality": get_data_quality_report,
        "trends": get_trends_report,
    }
    if report_type not in service_map:
        return JSONResponse({"error": "Invalid report_type"}, status_code=400)
    result = service_map[report_type](filters)
    return result

# Export endpoints – format determined by path suffix
@router.get("/dos/export.{format}")
async def export_report(
    format: str,
    report_type: str = Query(...),
    request: Request = None,
):
    filters = parse_filters(request)
    service_map = {
        "summary": get_dos_summary,
        "children_demographics": get_children_demographics_report,
        "enrollment_36_59": get_enrollment_participation_36_59_report,
        "institutions": get_institutions_report,
        "capacity_occupancy": get_capacity_occupancy_report,
        "attendance_absence": get_attendance_absence_report,
        "supervisors": get_supervisor_ratio_report,
        "incidents": get_incident_safety_report,
        "geo_gaps": get_geographic_gaps_report,
        "data_quality": get_data_quality_report,
        "trends": get_trends_report,
    }
    result = service_map[report_type](filters)
    data = result["data"]
    if format == "csv":
        return export_csv(data)
    if format in ("xlsx", "excel"):
        return export_excel(data)
    if format == "pdf":
        return export_pdf(data)
    if format == "json":
        return export_json(data)
    return JSONResponse({"error": "Unsupported export format"}, status_code=400)

@router.get("/dos/metadata.json")
async def get_metadata(report_type: str = Query(...), request: Request = None):
    filters = parse_filters(request)
    service_map = {
        "summary": get_dos_summary,
        "children_demographics": get_children_demographics_report,
        "enrollment_36_59": get_enrollment_participation_36_59_report,
        "institutions": get_institutions_report,
        "capacity_occupancy": get_capacity_occupancy_report,
        "attendance_absence": get_attendance_absence_report,
        "supervisors": get_supervisor_ratio_report,
        "incidents": get_incident_safety_report,
        "geo_gaps": get_geographic_gaps_report,
        "data_quality": get_data_quality_report,
        "trends": get_trends_report,
    }
    result = service_map[report_type](filters)
    return JSONResponse(result["metadata"])
