"""
Report generation service for admin incident reports
"""
import json
import logging
from datetime import datetime, date, timedelta
from utils.time_utils import today_amman as _today
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from database import get_db
import models
from services.jordan_locations import governorate_filter


logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating and managing admin reports"""

    @staticmethod
    def generate_incident_report(
        scope_type: models.ReportScopeType,
        start_date: date,
        end_date: date,
        kindergarten_id: Optional[int] = None,
        governorate: Optional[str] = None,
        district: Optional[str] = None,
        area: Optional[str] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """Generate incident summary report for the given scope and date range"""
        if db is None:
            db = next(get_db())

        # Build query filters
        from utils.time_utils import jordan_date_range_filter
        filters = jordan_date_range_filter(models.Incident.occurred_at, start_date, end_date)

        if scope_type == models.ReportScopeType.KINDERGARTEN:
            if kindergarten_id is None:
                raise ValueError("kindergarten_id required for KINDERGARTEN scope")
            filters.append(models.Incident.kindergarten_id == kindergarten_id)
        elif scope_type == models.ReportScopeType.GOVERNORATE:
            if governorate is None:
                raise ValueError("governorate required for GOVERNORATE scope")
            # Get all kindergartens in the governorate
            kindergarten_ids = db.query(models.Kindergarten.id).filter(
                governorate_filter(models.Kindergarten.governorate, governorate)
            ).all()
            kindergarten_ids = [k.id for k in kindergarten_ids]
            filters.append(models.Incident.kindergarten_id.in_(kindergarten_ids))
        elif scope_type == models.ReportScopeType.DISTRICT:
            if district is None:
                raise ValueError("district required for DISTRICT scope")
            # Get all kindergartens in the district
            kindergarten_ids = db.query(models.Kindergarten.id).filter(
                models.Kindergarten.district == district
            ).all()
            kindergarten_ids = [k.id for k in kindergarten_ids]
            filters.append(models.Incident.kindergarten_id.in_(kindergarten_ids))
        elif scope_type == models.ReportScopeType.AREA:
            if area is None:
                raise ValueError("area required for AREA scope")
            # Get all kindergartens in the area
            kindergarten_ids = db.query(models.Kindergarten.id).filter(
                models.Kindergarten.area == area
            ).all()
            kindergarten_ids = [k.id for k in kindergarten_ids]
            filters.append(models.Incident.kindergarten_id.in_(kindergarten_ids))
        # For ALL scope, no additional filters needed

        # Query incidents
        incidents = db.query(models.Incident).filter(and_(*filters)).all()

        # Calculate metrics
        total_incidents = len(incidents)

        # Incidents by type
        incidents_by_type = {}
        for incident_type in models.IncidentType:
            count = len([i for i in incidents if i.type == incident_type])
            incidents_by_type[incident_type.value] = count

        # Incidents by severity
        incidents_by_severity = {}
        for severity in models.SeverityLevel:
            count = len([i for i in incidents if i.severity_level == severity])
            incidents_by_severity[severity.value] = count

        # Incidents by status (open/closed)
        open_incidents = len([i for i in incidents if i.closed_at is None])
        closed_incidents = total_incidents - open_incidents

        # Per-kindergarten breakdown (if applicable)
        per_kindergarten = {}
        if scope_type in [models.ReportScopeType.GOVERNORATE, models.ReportScopeType.DISTRICT, models.ReportScopeType.AREA, models.ReportScopeType.ALL]:
            kindergarten_incidents = db.query(
                models.Kindergarten.name_ar,
                func.count(models.Incident.id).label('incident_count')
            ).join(models.Incident).filter(and_(*filters)).group_by(
                models.Kindergarten.id, models.Kindergarten.name_ar
            ).all()

            for kg_name, count in kindergarten_incidents:
                per_kindergarten[kg_name] = count

        # Build metrics dict
        metrics = {
            "total_incidents": total_incidents,
            "incidents_by_type": incidents_by_type,
            "incidents_by_severity": incidents_by_severity,
            "open_incidents": open_incidents,
            "closed_incidents": closed_incidents,
            "per_kindergarten": per_kindergarten,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }

        return metrics

    @staticmethod
    def calculate_date_range(period_type: str, reference_date: Optional[date] = None) -> tuple[date, date]:
        """Calculate start and end dates for different period types"""
        if reference_date is None:
            reference_date = _today()

        if period_type == "week":
            # This week (last 7 days)
            end_date = reference_date
            start_date = end_date - timedelta(days=6)
        elif period_type == "month":
            # This month (last 30 days)
            end_date = reference_date
            start_date = end_date - timedelta(days=29)
        elif period_type == "3years":
            # Rolling last 3 years
            end_date = reference_date
            start_date = date(end_date.year - 3, end_date.month, end_date.day) + timedelta(days=1)
        elif period_type == "annual":
            # Current year
            start_date = date(reference_date.year, 1, 1)
            end_date = date(reference_date.year, 12, 31)
        else:
            raise ValueError(f"Unknown period type: {period_type}")

        return start_date, end_date

    @staticmethod
    def get_available_scopes(user: models.User, db: Session = None) -> List[Dict[str, Any]]:
        """Get available scopes for the user"""
        if db is None:
            db = next(get_db())

        scopes = []

        # Kindergarten scope (if user has restricted access)
        if user.role == models.UserRole.MANAGER and user.kindergarten_id:
            kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == user.kindergarten_id).first()
            if kg:
                scopes.append({
                    "type": "KINDERGARTEN",
                    "id": kg.id,
                    "name": kg.name_ar,
                    "governorate": kg.governorate
                })

        # Admin can see all scopes
        if user.role == models.UserRole.ADMIN:
            # All kindergartens
            scopes.append({
                "type": "ALL",
                "name": "جميع الحضانات"
            })

            # Governorates
            governorates = db.query(models.Kindergarten.governorate).distinct().all()
            for gov in governorates:
                if gov[0]:
                    scopes.append({
                        "type": "GOVERNORATE",
                        "name": gov[0],
                        "governorate": gov[0]
                    })

            # Districts
            districts = db.query(models.Kindergarten.district).distinct().all()
            for dist in districts:
                if dist[0]:
                    scopes.append({
                        "type": "DISTRICT",
                        "name": dist[0],
                        "district": dist[0]
                    })

            # Areas
            areas = db.query(models.Kindergarten.area).distinct().all()
            for ar in areas:
                if ar[0]:
                    scopes.append({
                        "type": "AREA",
                        "name": ar[0],
                        "area": ar[0]
                    })

            # Individual kindergartens
            kindergartens = db.query(models.Kindergarten).all()
            for kg in kindergartens:
                scopes.append({
                    "type": "KINDERGARTEN",
                    "id": kg.id,
                    "name": kg.name_ar,
                    "governorate": kg.governorate
                })

        return scopes