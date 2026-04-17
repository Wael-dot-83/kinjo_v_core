"""
Dashboard customization service for widget management
"""
import json
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from database import get_db
from cache_service import cache_service
import models


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

    def get_user_widgets(self, user_id: int, role: str) -> List[Dict]:
        """Get user's customized dashboard widgets"""
        cache_key = f"user_widgets:{user_id}"

        # Try cache first
        cached = cache_service.get(cache_key)
        if cached:
            return cached

        # Get from database or use defaults
        db = next(get_db())
        user_prefs = db.query(models.UserDashboardPreference).filter(
            models.UserDashboardPreference.user_id == user_id
        ).first()

        if user_prefs and user_prefs.widget_config:
            widgets = json.loads(user_prefs.widget_config)
        else:
            # Use role-based defaults
            widgets = self.DEFAULT_WIDGETS.get(role, self.DEFAULT_WIDGETS["admin"]).copy()

        # Cache for 1 hour
        cache_service.set(cache_key, widgets, 3600)
        return widgets

    def update_user_widgets(self, user_id: int, widgets: List[Dict]) -> bool:
        """Update user's dashboard widget configuration"""
        try:
            db = next(get_db())

            # Validate widgets structure
            if not self._validate_widgets(widgets):
                return False

            # Update or create preference record
            user_prefs = db.query(models.UserDashboardPreference).filter(
                models.UserDashboardPreference.user_id == user_id
            ).first()

            if user_prefs:
                user_prefs.widget_config = json.dumps(widgets)
            else:
                user_prefs = models.UserDashboardPreference(
                    user_id=user_id,
                    widget_config=json.dumps(widgets)
                )
                db.add(user_prefs)

            db.commit()

            # Clear cache
            cache_key = f"user_widgets:{user_id}"
            cache_service.delete(cache_key)

            return True
        except Exception as e:
            db.rollback()
            print(f"Error updating user widgets: {e}")
            return False

    def reset_user_widgets(self, user_id: int, role: str) -> bool:
        """Reset user's widgets to role-based defaults"""
        default_widgets = self.DEFAULT_WIDGETS.get(role, self.DEFAULT_WIDGETS["admin"]).copy()
        return self.update_user_widgets(user_id, default_widgets)

    def _validate_widgets(self, widgets: List[Dict]) -> bool:
        """Validate widget configuration structure"""
        if not isinstance(widgets, list):
            return False

        required_fields = ["id", "title", "type", "enabled", "order"]
        valid_types = ["kpi_cards", "chart", "alerts", "child_info", "attendance"]

        for widget in widgets:
            if not isinstance(widget, dict):
                return False

            # Check required fields
            for field in required_fields:
                if field not in widget:
                    return False

            # Validate types
            if widget.get("type") not in valid_types:
                return False

            # Validate data types
            if not isinstance(widget.get("enabled"), bool):
                return False
            if not isinstance(widget.get("order"), int):
                return False

        return True

    def get_available_widgets(self, role: str) -> List[Dict]:
        """Get all available widgets for a role"""
        return self.DEFAULT_WIDGETS.get(role, self.DEFAULT_WIDGETS["admin"]).copy()

    def toggle_widget(self, user_id: int, widget_id: str, enabled: bool) -> bool:
        """Toggle a specific widget on/off"""
        widgets = self.get_user_widgets(user_id, "")  # Role not needed for existing config

        for widget in widgets:
            if widget["id"] == widget_id:
                widget["enabled"] = enabled
                break

        return self.update_user_widgets(user_id, widgets)

    def reorder_widgets(self, user_id: int, widget_order: List[str]) -> bool:
        """Update widget order"""
        widgets = self.get_user_widgets(user_id, "")

        # Create order mapping
        order_map = {widget_id: idx + 1 for idx, widget_id in enumerate(widget_order)}

        # Update orders
        for widget in widgets:
            if widget["id"] in order_map:
                widget["order"] = order_map[widget["id"]]

        # Sort by order
        widgets.sort(key=lambda x: x["order"])

        return self.update_user_widgets(user_id, widgets)


# Global instance
dashboard_customization = DashboardCustomizationService()
