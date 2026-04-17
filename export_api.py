"""
Export and reporting API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import date
from database import get_db
from dependencies import get_current_user
from export_service import export_service
import models

router = APIRouter(prefix="/api/export", tags=["Export & Reporting"])


@router.get("/kpi-dashboard")
async def export_kpi_dashboard(
    format: str = Query("csv", description="Export format: csv, json, excel, pdf"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export KPI dashboard data"""
    try:
        result = export_service.export_kpi_dashboard(current_user, None, format)

        # Return streaming response for file download
        def generate():
            yield result["content"]

        return StreamingResponse(
            generate(),
            media_type=result["content_type"],
            headers={"Content-Disposition": f"attachment; filename={result['filename']}"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/analytics-report")
async def export_analytics_report(
    report_type: str = Query(..., description="Report type: attendance, incidents, enrollment"),
    date_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date (YYYY-MM-DD)"),
    format: str = Query("csv", description="Export format: csv, json, excel, pdf"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export analytics report"""
    try:
        # Validate date range
        if date_from > date_to:
            raise HTTPException(status_code=400, detail="Start date cannot be after end date")

        # Check date range (max 1 year)
        from datetime import timedelta
        if (date_to - date_from).days > 365:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 1 year")

        result = export_service.export_analytics_report(
            current_user, report_type, date_from, date_to, format
        )

        # Return streaming response for file download
        def generate():
            yield result["content"]

        return StreamingResponse(
            generate(),
            media_type=result["content_type"],
            headers={"Content-Disposition": f"attachment; filename={result['filename']}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/formats")
async def get_supported_formats():
    """Get list of supported export formats"""
    return {
        "formats": export_service.supported_formats,
        "descriptions": {
            "csv": "Comma-separated values - compatible with Excel and most spreadsheet applications",
            "json": "JavaScript Object Notation - structured data format",
            "excel": "Microsoft Excel format (.xlsx)",
            "pdf": "Portable Document Format - for reports and printing"
        }
    }


@router.get("/report-types")
async def get_report_types():
    """Get list of available report types"""
    return {
        "report_types": [
            {
                "id": "attendance",
                "name": "تقرير الحضور",
                "description": "بيانات حضور الأطفال والموظفين"
            },
            {
                "id": "incidents",
                "name": "تقرير الحوادث",
                "description": "حوادث الروضة والإصابات"
            },
            {
                "id": "enrollment",
                "name": "تقرير التسجيل",
                "description": "طلبات التسجيل والقبول"
            }
        ]
    }