"""
Advanced filtering and search service for dashboard
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from database import get_db
from cache_service import cache_service
import models


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
        db = next(get_db())
        user_filters = db.query(models.UserFilterPreference).filter(
            models.UserFilterPreference.user_id == user_id
        ).first()

        if user_filters and user_filters.filter_config:
            import json
            filters = json.loads(user_filters.filter_config)
        else:
            filters = self.default_filters.copy()

        # Cache for 30 minutes
        cache_service.set(cache_key, filters, 1800)
        return filters

    def save_user_filters(self, user_id: int, filters: Dict[str, Any]) -> bool:
        """Save user's filter preferences"""
        try:
            import json
            db = next(get_db())

            # Validate filters
            if not self._validate_filters(filters):
                return False

            # Update or create preference record
            user_filters = db.query(models.UserFilterPreference).filter(
                models.UserFilterPreference.user_id == user_id
            ).first()

            if user_filters:
                user_filters.filter_config = json.dumps(filters)
            else:
                user_filters = models.UserFilterPreference(
                    user_id=user_id,
                    filter_config=json.dumps(filters)
                )
                db.add(user_filters)

            db.commit()

            # Clear cache
            cache_key = f"user_filters:{user_id}"
            cache_service.delete(cache_key)

            return True
        except Exception as e:
            db.rollback()
            print(f"Error saving user filters: {e}")
            return False

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

            # Apply date filter (this will vary based on the model)
            # This is a generic implementation - specific models may need custom date field filtering
            pass

        # Kindergarten filter
        kindergarten_ids = filters.get("kindergarten_ids", [])
        if kindergarten_ids and user.role != models.UserRole.ADMIN:
            # Non-admin users can only see their own kindergarten
            kindergarten_ids = [user.kindergarten_id]

        if kindergarten_ids:
            query = query.filter(models.Kindergarten.id.in_(kindergarten_ids))

        # Governorate filter
        governorates = filters.get("governorates", [])
        if governorates:
            query = query.filter(models.Kindergarten.governorate.in_(governorates))

        # City filter
        cities = filters.get("cities", [])
        if cities:
            query = query.filter(models.Kindergarten.city.in_(cities))

        # Status filter
        status = filters.get("status")
        if status and status != "all":
            # This will vary based on the model - generic implementation
            pass

        # Search query
        search_query = filters.get("search_query", "").strip()
        if search_query:
            # Generic text search - specific models should implement their own search logic
            pass

        return query

    def apply_sorting_and_pagination(self, query, filters: Dict[str, Any]):
        """Apply sorting and pagination to query"""
        # Sorting
        sort_by = filters.get("sort_by", "date")
        sort_order = filters.get("sort_order", "desc")

        # This is generic - specific models should implement their own sorting
        if sort_order == "desc":
            query = query.order_by(getattr(models.Kindergarten, sort_by).desc())
        else:
            query = query.order_by(getattr(models.Kindergarten, sort_by).asc())

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
        db = next(get_db())

        # Base query for kindergartens user can access
        kg_query = db.query(models.Kindergarten)

        if user.role != models.UserRole.ADMIN:
            kg_query = kg_query.filter(models.Kindergarten.id == user.kindergarten_id)

        kindergartens = kg_query.all()

        # Extract unique values
        governorates = sorted(list(set(kg.governorate for kg in kindergartens if kg.governorate)))
        cities = sorted(list(set(kg.city for kg in kindergartens if kg.city)))

        return {
            "kindergartens": [{"id": kg.id, "name": kg.name_ar or kg.name_en} for kg in kindergartens],
            "governorates": governorates,
            "cities": cities,
            "statuses": ["active", "inactive", "draft"]  # Generic statuses
        }

    def search_kindergartens(self, query: str, user: models.User, limit: int = 10) -> List[Dict]:
        """Search kindergartens by name"""
        db = next(get_db())

        # Base query
        kg_query = db.query(models.Kindergarten).filter(
            or_(
                models.Kindergarten.name_ar.ilike(f"%{query}%"),
                models.Kindergarten.name_en.ilike(f"%{query}%")
            )
        )

        # Apply permissions
        if user.role != models.UserRole.ADMIN:
            kg_query = kg_query.filter(models.Kindergarten.id == user.kindergarten_id)

        kindergartens = kg_query.limit(limit).all()

        return [
            {
                "id": kg.id,
                "name_ar": kg.name_ar,
                "name_en": kg.name_en,
                "governorate": kg.governorate,
                "city": kg.city
            }
            for kg in kindergartens
        ]

    def export_filtered_data(self, filters: Dict[str, Any], user: models.User, export_format: str = "csv"):
        """Export filtered data in specified format"""
        # This is a placeholder for export functionality
        # Implementation would depend on what data is being exported
        pass


# Global instance
filter_service = DashboardFilterService()