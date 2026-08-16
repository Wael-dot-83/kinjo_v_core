"""
Dashboard customization service for widget management
"""
import copy
import json
import logging
from typing import Dict, List
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from cache_service import cache_service
import models

logger = logging.getLogger(__name__)


class DashboardCustomizationService:
    """Service for managing user dashboard widget preferences"""

    DEFAULT_WIDGETS = {
        "admin": [
            {"id": "operational_metrics", "title": "المؤشرات التشغيلية", "type": "kpi_cards", "enabled": True, "order": 1},
            {"id": "attendance_trend", "title": "اتجاهات الحضور", "type": "chart", "enabled": True, "order": 2},
            {"id": "incidents_trend", "title": "اتجاهات الحوادث", "type": "chart", "enabled": True, "order": 3},
            {"id": "enrollment_trend", "title": "اتجاهات التسجيل", "type": "chart", "enabled": True, "order": 4},
            {"id": "gcei_trend", "title": "اتجاهات مؤشر الحوكمة", "type": "chart", "enabled": True, "order": 5},
            {"id": "alerts", "title": "التنبيهات", "type": "alerts", "enabled": True, "order": 6}
        ],
        "manager": [
            {"id": "operational_metrics", "title": "المؤشرات التشغيلية", "type": "kpi_cards", "enabled": True, "order": 1},
            {"id": "attendance_trend", "title": "اتجاهات الحضور", "type": "chart", "enabled": True, "order": 2},
            {"id": "incidents_trend", "title": "اتجاهات الحوادث", "type": "chart", "enabled": True, "order": 3},
            {"id": "alerts", "title": "التنبيهات", "type": "alerts", "enabled": True, "order": 4}
        ],
        "supervisor": [
            {"id": "operational_metrics", "title": "المؤشرات التشغيلية", "type": "kpi_cards", "enabled": True, "order": 1},
            {"id": "attendance_trend", "title": "اتجاهات الحضور", "type": "chart", "enabled": True, "order": 2},
            {"id": "alerts", "title": "التنبيهات", "type": "alerts", "enabled": True, "order": 3}
        ],
        "parent": [
            {"id": "child_info", "title": "معلومات الطفل", "type": "child_info", "enabled": True, "order": 1},
            {"id": "attendance_summary", "title": "ملخص الحضور", "type": "attendance", "enabled": True, "order": 2},
            {"id": "alerts", "title": "التنبيهات", "type": "alerts", "enabled": True, "order": 3}
        ]
    }

    @classmethod
    def _role_defaults(cls, role: str) -> List[Dict]:
        """Return an isolated copy of the widgets available to ``role``."""
        normalized_role = str(role or "").lower()
        if normalized_role not in cls.DEFAULT_WIDGETS:
            raise ValueError("Unsupported dashboard role")
        return copy.deepcopy(cls.DEFAULT_WIDGETS[normalized_role])

    @staticmethod
    def _cache_key(user_id: int, role: str) -> str:
        return f"user_widgets:{user_id}:{str(role or '').lower()}"

    def get_user_widgets(self, user_id: int, role: str, db: Session) -> List[Dict]:
        """Get user's customized dashboard widgets"""
        cache_key = self._cache_key(user_id, role)

        # Try cache first
        cached = cache_service.get(cache_key)
        if cached and self._validate_widgets(cached, role):
            return copy.deepcopy(cached)
        if cached:
            cache_service.delete(cache_key)

        # The request owns ``db`` and is responsible for closing it.
        user_prefs = db.query(models.UserDashboardPreference).filter(
            models.UserDashboardPreference.user_id == user_id
        ).first()

        if user_prefs and user_prefs.widget_config:
            raw_config = user_prefs.widget_config
            widgets = json.loads(raw_config) if isinstance(raw_config, str) else copy.deepcopy(raw_config)
            if not self._validate_widgets(widgets, role):
                logger.warning(
                    "Ignoring invalid dashboard widget configuration for user_id=%s role=%s",
                    user_id,
                    role,
                )
                widgets = self._role_defaults(role)
        else:
            widgets = self._role_defaults(role)

        # Cache for 1 hour
        cache_service.set(cache_key, copy.deepcopy(widgets), 3600)
        return copy.deepcopy(widgets)

    def update_user_widgets(self, user_id: int, widgets: List[Dict], role: str, db: Session) -> bool:
        """Update user's dashboard widget configuration"""
        try:
            # Validate widgets structure
            if not self._validate_widgets(widgets, role):
                return False

            stored_widgets = copy.deepcopy(widgets)

            # Update or create preference record
            user_prefs = db.query(models.UserDashboardPreference).filter(
                models.UserDashboardPreference.user_id == user_id
            ).first()

            if user_prefs:
                user_prefs.widget_config = stored_widgets
            else:
                user_prefs = models.UserDashboardPreference(
                    user_id=user_id,
                    widget_config=stored_widgets,
                )
                db.add(user_prefs)

            db.commit()

            # Clear cache
            cache_service.delete(self._cache_key(user_id, role))
            cache_service.delete(f"user_widgets:{user_id}")  # remove the legacy cache key

            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error("Database error updating dashboard widgets for user_id=%s: %s", user_id, str(e), exc_info=True)
            return False
        except (TypeError, ValueError) as e:
            db.rollback()
            logger.warning("Invalid dashboard widget payload for user_id=%s: %s", user_id, str(e))
            return False

    def reset_user_widgets(self, user_id: int, role: str, db: Session) -> bool:
        """Reset user's widgets to role-based defaults"""
        return self.update_user_widgets(user_id, self._role_defaults(role), role, db)

    def _validate_widgets(self, widgets: List[Dict], role: str) -> bool:
        """Validate widget configuration structure"""
        if not isinstance(widgets, list):
            return False

        try:
            available = self._role_defaults(role)
        except ValueError:
            return False

        if len(widgets) != len(available):
            return False

        required_fields = {"id", "title", "type", "enabled", "order"}
        available_by_id = {widget["id"]: widget for widget in available}
        ids = []
        orders = []

        for widget in widgets:
            if not isinstance(widget, dict):
                return False

            # Persist only the bounded canonical structure, not arbitrary nested data.
            if set(widget) != required_fields:
                return False

            widget_id = widget.get("id")
            canonical = available_by_id.get(widget_id)
            if canonical is None:
                return False
            if widget.get("title") != canonical["title"] or widget.get("type") != canonical["type"]:
                return False

            # Validate data types
            if not isinstance(widget.get("enabled"), bool):
                return False
            order = widget.get("order")
            if isinstance(order, bool) or not isinstance(order, int):
                return False
            ids.append(widget_id)
            orders.append(order)

        if len(ids) != len(set(ids)) or set(ids) != set(available_by_id):
            return False
        if len(orders) != len(set(orders)) or set(orders) != set(range(1, len(widgets) + 1)):
            return False

        return True

    def get_available_widgets(self, role: str) -> List[Dict]:
        """Get all available widgets for a role"""
        return self._role_defaults(role)

    def toggle_widget(self, user_id: int, widget_id: str, enabled: bool, role: str, db: Session) -> bool:
        """Toggle a specific widget on/off"""
        widgets = self.get_user_widgets(user_id, role, db)

        for widget in widgets:
            if widget["id"] == widget_id:
                widget["enabled"] = enabled
                break
        else:
            return False

        return self.update_user_widgets(user_id, widgets, role, db)

    def reorder_widgets(self, user_id: int, widget_order: List[str], role: str, db: Session) -> bool:
        """Update widget order"""
        available_ids = {widget["id"] for widget in self._role_defaults(role)}
        if (
            not isinstance(widget_order, list)
            or len(widget_order) != len(available_ids)
            or len(widget_order) != len(set(widget_order))
            or set(widget_order) != available_ids
        ):
            return False

        widgets = self.get_user_widgets(user_id, role, db)

        # Create order mapping
        order_map = {widget_id: idx + 1 for idx, widget_id in enumerate(widget_order)}

        # Update orders
        for widget in widgets:
            if widget["id"] in order_map:
                widget["order"] = order_map[widget["id"]]

        # Sort by order
        widgets.sort(key=lambda x: x["order"])

        return self.update_user_widgets(user_id, widgets, role, db)


# Global instance
dashboard_customization = DashboardCustomizationService()
