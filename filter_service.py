"""
Advanced filtering and search service for dashboard
"""
import json
import csv
import logging
import io
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from database import get_db
from cache_service import cache_service
import models

logger = logging.getLogger(__name__)


class DashboardFilterService:
    """Service for advanced dashboard filtering and search"""

    def __init__(self):
        self.default_filters = {
            "date_range": {
                "start_date": (datetime.now() - timedelta(days=30)).date(),
                "end_date": datetime.now().date()
            },
            "kindergarten_ids": [],
            "governorates": [],
            "cities": [],
            "status": "all",
            "search_query": "",
            "sort_by": "date",
            "sort_order": "desc",
            "page": 1,
            "per_page": 50
        }

    def get_user_filters(self, user_id: int) -> Dict[str, Any]:
        """Get user's saved filter preferences"""
        cache_key = f"user_filters:{user_id}"

        # Try cache first
        cached = cache_service.get(cache_key)
        if cached:
            return cached

        # Get from database or use defaults
        db: Optional[Session] = None
        try:
            db = next(get_db())
            user_filters = db.query(models.UserFilterPreference).filter(
                models.UserFilterPreference.user_id == user_id
            ).first()

            if user_filters and user_filters.filter_config:
                stored_filters = user_filters.filter_config
                if isinstance(stored_filters, str):
                    filters = json.loads(stored_filters)
                elif isinstance(stored_filters, dict):
                    filters = stored_filters
                else:
                    filters = self.default_filters.copy()
            else:
                filters = self.default_filters.copy()

            # Cache for 30 minutes
            cache_service.set(cache_key, filters, 1800)
            return filters
        finally:
            if db is not None:
                db.close()

    def save_user_filters(self, user_id: int, filters: Dict[str, Any]) -> bool:
        """Save user's filter preferences"""
        db: Optional[Session] = None
        try:
            db = next(get_db())

            # Validate filters
            if not self._validate_filters(filters):
                return False

            # Update or create preference record
            user_filters = db.query(models.UserFilterPreference).filter(
                models.UserFilterPreference.user_id == user_id
            ).first()

            if user_filters:
                user_filters.filter_config = filters
            else:
                user_filters = models.UserFilterPreference(
                    user_id=user_id,
                    filter_config=filters
                )
                db.add(user_filters)

            db.commit()

            # Clear cache
            cache_key = f"user_filters:{user_id}"
            cache_service.delete(cache_key)

            return True
        except SQLAlchemyError as e:
            if db is not None:
                db.rollback()
            logger.error("Database error saving filter preferences for user_id=%s: %s", user_id, str(e), exc_info=True)
            return False
        except (TypeError, ValueError) as e:
            if db is not None:
                db.rollback()
            logger.warning("Invalid filter payload for user_id=%s: %s", user_id, str(e))
            return False
        finally:
            if db is not None:
                db.close()

    def _validate_filters(self, filters: Dict[str, Any]) -> bool:
        """Validate filter configuration"""
        required_fields = ["date_range", "page", "per_page"]
        for field in required_fields:
            if field not in filters:
                return False

        # Validate date range
        date_range = filters.get("date_range", {})
        if not isinstance(date_range, dict) or "start_date" not in date_range or "end_date" not in date_range:
            return False

        # Validate pagination
        if not isinstance(filters.get("page", 0), int) or filters["page"] < 1:
            return False
        if not isinstance(filters.get("per_page", 0), int) or filters["per_page"] < 1 or filters["per_page"] > 1000:
            return False

        return True

    def apply_filters_to_query(self, query, filters: Dict[str, Any], user: models.User):
        """Apply filters to a SQLAlchemy query"""
        # Date range filter
        date_range = filters.get("date_range", {})
        start_date = date_range.get("start_date")
        end_date = date_range.get("end_date")

        if start_date and end_date:
            # Convert to datetime if needed
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date).date()
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date).date()

            if hasattr(models.Kindergarten, "created_at"):
                query = query.filter(
                    func.date(models.Kindergarten.created_at) >= start_date,
                    func.date(models.Kindergarten.created_at) <= end_date,
                )

        # Kindergarten filter
        kindergarten_ids = filters.get("kindergarten_ids", [])
        if user.role != models.UserRole.ADMIN:
            kindergarten_ids = [user.kindergarten_id] if user.kindergarten_id else []

        if kindergarten_ids:
            query = query.filter(models.Kindergarten.id.in_(kindergarten_ids))

        # Governorate filter
        governorates = filters.get("governorates", [])
        if governorates:
            query = query.filter(models.Kindergarten.governorate.in_(governorates))

        # City filter
        cities = filters.get("cities", [])
        if cities:
            query = query.filter(models.Kindergarten.district.in_(cities))

        # Status filter
        status = filters.get("status")
        if status and status != "all":
            try:
                query = query.filter(models.Kindergarten.status == models.KindergartenStatus(str(status).upper()))
            except (ValueError, TypeError):
                logger.debug("Ignoring unsupported kindergarten status filter: %s", status)

        # Search query
        search_query = filters.get("search_query", "").strip()
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    models.Kindergarten.name_ar.ilike(search_term),
                    models.Kindergarten.name_en.ilike(search_term),
                    models.Kindergarten.governorate.ilike(search_term),
                    models.Kindergarten.district.ilike(search_term),
                    models.Kindergarten.area.ilike(search_term),
                    models.Kindergarten.address_line.ilike(search_term),
                    models.Kindergarten.license_number.ilike(search_term),
                )
            )

        return query

    def apply_sorting_and_pagination(self, query, filters: Dict[str, Any]):
        """Apply sorting and pagination to query"""
        # Sorting
        sort_by = filters.get("sort_by", "date")
        sort_order = filters.get("sort_order", "desc")

        sortable_fields = {
            "id": models.Kindergarten.id,
            "name_ar": models.Kindergarten.name_ar,
            "name_en": models.Kindergarten.name_en,
            "governorate": models.Kindergarten.governorate,
            "city": models.Kindergarten.district,
            "area": models.Kindergarten.area,
            "status": models.Kindergarten.status,
            "created_at": models.Kindergarten.created_at,
            "updated_at": models.Kindergarten.updated_at,
            "date": models.Kindergarten.created_at,
        }
        sort_column = sortable_fields.get(sort_by, models.Kindergarten.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Pagination
        page = filters.get("page", 1)
        per_page = filters.get("per_page", 50)
        offset = (page - 1) * per_page

        total_count = query.count()
        results = query.offset(offset).limit(per_page).all()

        return {
            "items": results,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page
        }

    def get_filter_options(self, user: models.User) -> Dict[str, List]:
        """Get available filter options based on user permissions"""
        db: Optional[Session] = None
        try:
            db = next(get_db())

            kg_query = db.query(models.Kindergarten)
            if user.role != models.UserRole.ADMIN:
                kg_query = kg_query.filter(models.Kindergarten.id == user.kindergarten_id)

            kindergartens = kg_query.all()
            governorates = sorted({kg.governorate for kg in kindergartens if kg.governorate})
            cities = sorted({kg.district for kg in kindergartens if kg.district})

            return {
                "kindergartens": [{"id": kg.id, "name": kg.name_ar or kg.name_en} for kg in kindergartens],
                "governorates": list(governorates),
                "cities": list(cities),
                "statuses": [status.value.lower() for status in models.KindergartenStatus],
            }
        finally:
            if db is not None:
                db.close()

    def search_kindergartens(self, query: str, user: models.User, limit: int = 10) -> List[Dict]:
        """Search kindergartens by name"""
        db: Optional[Session] = None
        try:
            db = next(get_db())

            kg_query = db.query(models.Kindergarten).filter(
                or_(
                    models.Kindergarten.name_ar.ilike(f"%{query}%"),
                    models.Kindergarten.name_en.ilike(f"%{query}%"),
                    models.Kindergarten.governorate.ilike(f"%{query}%"),
                    models.Kindergarten.district.ilike(f"%{query}%"),
                )
            )

            if user.role != models.UserRole.ADMIN:
                kg_query = kg_query.filter(models.Kindergarten.id == user.kindergarten_id)

            kindergartens = kg_query.order_by(models.Kindergarten.name_ar.asc()).limit(limit).all()

            return [
                {
                    "id": kg.id,
                    "name_ar": kg.name_ar,
                    "name_en": kg.name_en,
                    "governorate": kg.governorate,
                    "city": kg.district,
                }
                for kg in kindergartens
            ]
        finally:
            if db is not None:
                db.close()

    def export_filtered_data(self, filters: Dict[str, Any], user: models.User, export_format: str = "csv"):
        """Export filtered data in specified format"""
        db: Optional[Session] = None
        try:
            db = next(get_db())
            query = db.query(models.Kindergarten)
            query = self.apply_filters_to_query(query, filters, user)
            query = query.order_by(models.Kindergarten.id.asc())
            rows = query.all()

            serialized_rows = [
                {
                    "id": kg.id,
                    "name_ar": kg.name_ar,
                    "name_en": kg.name_en,
                    "governorate": kg.governorate,
                    "city": kg.district,
                    "area": kg.area,
                    "status": kg.status.value if hasattr(kg.status, "value") else str(kg.status),
                    "license_number": kg.license_number,
                    "license_valid_until": kg.license_valid_until.isoformat() if kg.license_valid_until else None,
                }
                for kg in rows
            ]

            if export_format.lower() == "json":
                return json.dumps(serialized_rows, ensure_ascii=False)

            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["id", "name_ar", "name_en", "governorate", "city", "area", "status", "license_number", "license_valid_until"],
            )
            writer.writeheader()
            writer.writerows(serialized_rows)
            return output.getvalue()
        finally:
            if db is not None:
                db.close()


# Global instance
filter_service = DashboardFilterService()