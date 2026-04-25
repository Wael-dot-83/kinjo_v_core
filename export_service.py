"""
Export and reporting service for dashboard data
"""
import csv
import io
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from database import get_db
from kpi_service import get_consolidated_kpi_dashboard_data
from cache_service import cache_service
import models

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting dashboard data in various formats"""

    def __init__(self):
        self.supported_formats = ["csv", "excel", "pdf", "json"]

    def export_kpi_dashboard(
        self,
        user: models.User,
        filters: Optional[Dict[str, Any]] = None,
        export_format: str = "csv"
    ) -> Dict[str, Any]:
        """Export KPI dashboard data"""
        db: Optional[Session] = None
        try:
            if export_format not in self.supported_formats:
                raise ValueError(f"Unsupported export format: {export_format}")

            # Get KPI data
            db = next(get_db())
            kpi_data = get_consolidated_kpi_dashboard_data(db, user.role.value.lower(), locale="ar")

            if export_format == "json":
                return self._export_kpi_json(kpi_data)
            elif export_format == "csv":
                return self._export_kpi_csv(kpi_data)
            elif export_format == "excel":
                return self._export_kpi_excel(kpi_data)
            elif export_format == "pdf":
                return self._export_kpi_pdf(kpi_data, user)
        except SQLAlchemyError as e:
            logger.error("Failed to export KPI dashboard due to database error: %s", str(e), exc_info=True)
            raise
        except (TypeError, ValueError) as e:
            logger.error("Failed to export KPI dashboard due to invalid export data: %s", str(e), exc_info=True)
            raise
        finally:
            if db is not None:
                db.close()

    def _export_kpi_json(self, kpi_data: Dict[str, Any]) -> Dict[str, Any]:
        """Export KPI data as JSON"""
        export_data = {
            "export_type": "kpi_dashboard",
            "generated_at": datetime.now().isoformat(),
            "data": kpi_data
        }

        return {
            "content": json.dumps(export_data, ensure_ascii=False, indent=2),
            "content_type": "application/json",
            "filename": f"kpi_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }

    def _export_kpi_csv(self, kpi_data: Dict[str, Any]) -> Dict[str, Any]:
        """Export KPI data as CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["Category", "Metric", "Value", "Unit", "Period"])

        # Write operational metrics
        operational = kpi_data.get("operational_metrics", {})
        for metric_key, metric_data in operational.items():
            if isinstance(metric_data, dict):
                writer.writerow([
                    "Operational",
                    metric_data.get("label", metric_key),
                    metric_data.get("value", ""),
                    metric_data.get("unit", ""),
                    "Current"
                ])

        # Write trend data (simplified)
        trends = kpi_data.get("trends", {})
        for trend_key, trend_data in trends.items():
            if isinstance(trend_data, list) and trend_data:
                # Just export the latest data point
                latest = trend_data[-1] if trend_data else {}
                writer.writerow([
                    "Trend",
                    trend_key,
                    latest.get("value", ""),
                    latest.get("unit", ""),
                    latest.get("date", "")
                ])

        return {
            "content": output.getvalue(),
            "content_type": "text/csv",
            "filename": f"kpi_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }

    def _export_kpi_excel(self, kpi_data: Dict[str, Any]) -> Dict[str, Any]:
        """Export KPI data as Excel (simplified - returns CSV for now)"""
        # For now, return CSV. In production, you'd use openpyxl or similar
        return self._export_kpi_csv(kpi_data)

    def _export_kpi_pdf(self, kpi_data: Dict[str, Any], user: models.User) -> Dict[str, Any]:
        """Export KPI data as PDF (simplified - returns JSON for now)"""
        # For now, return JSON. In production, you'd use reportlab or similar
        return self._export_kpi_json(kpi_data)

    def export_analytics_report(
        self,
        user: models.User,
        report_type: str,
        date_from: date,
        date_to: date,
        export_format: str = "csv"
    ) -> Dict[str, Any]:
        """Export analytics report"""
        db: Optional[Session] = None
        try:
            if export_format not in self.supported_formats:
                raise ValueError(f"Unsupported export format: {export_format}")

            # Get report data based on type
            db = next(get_db())
            report_data = self._get_report_data(db, user, report_type, date_from, date_to)

            if export_format == "json":
                return self._export_report_json(report_data, report_type)
            elif export_format == "csv":
                return self._export_report_csv(report_data, report_type)
            elif export_format == "excel":
                return self._export_report_excel(report_data, report_type)
            elif export_format == "pdf":
                return self._export_report_pdf(report_data, report_type, user)
        except SQLAlchemyError as e:
            logger.error("Failed to export analytics report due to database error: %s", str(e), exc_info=True)
            raise
        except (TypeError, ValueError) as e:
            logger.error("Failed to export analytics report due to invalid export data: %s", str(e), exc_info=True)
            raise
        finally:
            if db is not None:
                db.close()

    def _get_report_data(self, db: Session, user: models.User, report_type: str, date_from: date, date_to: date) -> List[Dict]:
        """Get report data based on type"""
        if report_type == "attendance":
            return self._get_attendance_report_data(db, user, date_from, date_to)
        elif report_type == "incidents":
            return self._get_incidents_report_data(db, user, date_from, date_to)
        elif report_type == "enrollment":
            return self._get_enrollment_report_data(db, user, date_from, date_to)
        else:
            raise ValueError(f"Unsupported report type: {report_type}")

    def _get_attendance_report_data(self, db: Session, user: models.User, date_from: date, date_to: date) -> List[Dict]:
        """Get attendance report data"""
        # Simplified implementation
        query = db.query(models.Attendance).filter(
            models.Attendance.date.between(date_from, date_to)
        )

        if user.role != models.UserRole.ADMIN:
            query = query.join(models.Child).join(models.Class).filter(
                models.Class.kindergarten_id == user.kindergarten_id
            )

        attendances = query.limit(1000).all()  # Limit for performance

        return [
            {
                "date": att.date.isoformat(),
                "child_id": att.child_id,
                "status": att.status.value,
                "method": att.method.value if att.method else None,
                "check_in_time": att.check_in_time.isoformat() if att.check_in_time else None,
                "check_out_time": att.check_out_time.isoformat() if att.check_out_time else None
            }
            for att in attendances
        ]

    def _get_incidents_report_data(self, db: Session, user: models.User, date_from: date, date_to: date) -> List[Dict]:
        """Get incidents report data"""
        query = db.query(models.Incident).filter(
            models.Incident.date.between(date_from, date_to)
        )

        if user.role != models.UserRole.ADMIN:
            query = query.filter(models.Incident.kindergarten_id == user.kindergarten_id)

        incidents = query.limit(1000).all()

        return [
            {
                "date": inc.date.isoformat(),
                "type": inc.type.value,
                "severity": inc.severity.value,
                "description": inc.description,
                "reported_by": inc.reported_by,
                "kindergarten_id": inc.kindergarten_id
            }
            for inc in incidents
        ]

    def _get_enrollment_report_data(self, db: Session, user: models.User, date_from: date, date_to: date) -> List[Dict]:
        """Get enrollment report data"""
        query = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.created_at.between(
                datetime.combine(date_from, datetime.min.time()),
                datetime.combine(date_to, datetime.max.time())
            )
        )

        if user.role != models.UserRole.ADMIN:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == user.kindergarten_id)

        enrollments = query.limit(1000).all()

        return [
            {
                "created_at": app.created_at.isoformat(),
                "status": app.status.value,
                "child_name": f"{app.first_name_ar} {app.last_name_ar}",
                "parent_name": f"{app.parent_first_name_ar} {app.parent_last_name_ar}",
                "kindergarten_id": app.kindergarten_id
            }
            for app in enrollments
        ]

    def _export_report_json(self, report_data: List[Dict], report_type: str) -> Dict[str, Any]:
        """Export report data as JSON"""
        export_data = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "record_count": len(report_data),
            "data": report_data
        }

        return {
            "content": json.dumps(export_data, ensure_ascii=False, indent=2),
            "content_type": "application/json",
            "filename": f"{report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }

    def _export_report_csv(self, report_data: List[Dict], report_type: str) -> Dict[str, Any]:
        """Export report data as CSV"""
        if not report_data:
            return {
                "content": "No data available",
                "content_type": "text/csv",
                "filename": f"{report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header from first record keys
        headers = list(report_data[0].keys())
        writer.writerow(headers)

        # Write data
        for record in report_data:
            row = [record.get(header, "") for header in headers]
            writer.writerow(row)

        return {
            "content": output.getvalue(),
            "content_type": "text/csv",
            "filename": f"{report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }

    def _export_report_excel(self, report_data: List[Dict], report_type: str) -> Dict[str, Any]:
        """Export report data as Excel (simplified - returns CSV)"""
        return self._export_report_csv(report_data, report_type)

    def _export_report_pdf(self, report_data: List[Dict], report_type: str, user: models.User) -> Dict[str, Any]:
        """Export report data as PDF (simplified - returns JSON)"""
        return self._export_report_json(report_data, report_type)


# Global instance
export_service = ExportService()