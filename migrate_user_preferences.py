"""
Data Migration Script for User Preferences
Migrates existing data and sets up default preferences for users
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import get_db
from models import User, UserDashboardPreference, UserFilterPreference, UserRole

logger = logging.getLogger(__name__)


def migrate_user_preferences():
    """Migrate user preferences data"""
    db = next(get_db())

    try:
        # Get all users
        users = db.query(User).all()
        logger.info(f"Found {len(users)} users to process")

        migrated_dashboard = 0
        migrated_filters = 0

        for user in users:
            # Check if user already has dashboard preferences
            dashboard_prefs = db.query(UserDashboardPreference).filter(
                UserDashboardPreference.user_id == user.id
            ).first()

            if not dashboard_prefs:
                # Create default dashboard preferences based on role
                default_widgets = get_default_widgets_for_role(user.role.value.lower())
                dashboard_prefs = UserDashboardPreference(
                    user_id=user.id,
                    widget_config=json.dumps(default_widgets)
                )
                db.add(dashboard_prefs)
                migrated_dashboard += 1
                logger.debug(f"Created dashboard preferences for user {user.id} ({user.role.value})")

            # Check if user already has filter preferences
            filter_prefs = db.query(UserFilterPreference).filter(
                UserFilterPreference.user_id == user.id
            ).first()

            if not filter_prefs:
                # Create default filter preferences
                default_filters = get_default_filters()
                filter_prefs = UserFilterPreference(
                    user_id=user.id,
                    filter_config=json.dumps(default_filters)
                )
                db.add(filter_prefs)
                migrated_filters += 1
                logger.debug(f"Created filter preferences for user {user.id} ({user.role.value})")

        # Commit all changes
        db.commit()
        logger.info(f"Successfully migrated preferences: {migrated_dashboard} dashboard, {migrated_filters} filter preferences")

        return {
            "success": True,
            "dashboard_preferences_created": migrated_dashboard,
            "filter_preferences_created": migrated_filters,
            "total_users_processed": len(users)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to migrate user preferences: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


def get_default_widgets_for_role(role: str) -> list:
    """Get default dashboard widgets for a specific role"""
    defaults = {
        "admin": [
            {"id": "operational_metrics", "title": "المؤشرات التشغيلية", "type": "kpi_cards", "enabled": True, "order": 1},
            {"id": "attendance_trend", "title": "اتجاهات الحضور", "type": "chart", "enabled": True, "order": 2},
            {"id": "incidents_trend", "title": "اتجاهات الحوادث", "type": "chart", "enabled": True, "order": 3},
            {"id": "enrollment_trend", "title": "اتجاهات التسجيل", "type": "chart", "enabled": True, "order": 4},
            {"id": "gcei_trend", "title": "اتجاهات GCEI", "type": "chart", "enabled": True, "order": 5},
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

    return defaults.get(role, defaults["admin"])


def get_default_filters() -> dict:
    """Get default filter preferences"""
    from datetime import date, timedelta

    return {
        "date_range": {
            "start_date": (date.today() - timedelta(days=30)).isoformat(),
            "end_date": date.today().isoformat()
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


def validate_migration():
    """Validate that the migration was successful"""
    db = next(get_db())

    try:
        # Count users
        total_users = db.query(User).count()

        # Count preferences
        dashboard_prefs = db.query(UserDashboardPreference).count()
        filter_prefs = db.query(UserFilterPreference).count()

        validation_result = {
            "total_users": total_users,
            "dashboard_preferences": dashboard_prefs,
            "filter_preferences": filter_prefs,
            "dashboard_coverage": (dashboard_prefs / total_users * 100) if total_users > 0 else 0,
            "filter_coverage": (filter_prefs / total_users * 100) if total_users > 0 else 0,
            "is_complete": dashboard_prefs == total_users and filter_prefs == total_users
        }

        logger.info(f"Migration validation: {validation_result}")
        return validation_result

    except Exception as e:
        logger.error(f"Failed to validate migration: {e}")
        return {"error": str(e)}
    finally:
        db.close()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    print("Starting user preferences data migration...")

    # Run migration
    result = migrate_user_preferences()

    if result["success"]:
        print("✅ Migration completed successfully!")
        print(f"   - Dashboard preferences created: {result['dashboard_preferences_created']}")
        print(f"   - Filter preferences created: {result['filter_preferences_created']}")
        print(f"   - Total users processed: {result['total_users_processed']}")

        # Validate
        validation = validate_migration()
        if validation.get("is_complete"):
            print("✅ Migration validation passed - all users have preferences")
        else:
            print("⚠️  Migration validation warning:")
            print(f"   - Dashboard coverage: {validation['dashboard_coverage']:.1f}%")
            print(f"   - Filter coverage: {validation['filter_coverage']:.1f}%")
    else:
        print(f"❌ Migration failed: {result['error']}")
        exit(1)