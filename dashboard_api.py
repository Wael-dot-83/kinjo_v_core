"""
Dashboard customization API endpoints
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List, Dict
from database import get_db
from dependencies import get_current_user
from dashboard_customization import dashboard_customization
import models

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Customization"])
logger = logging.getLogger(__name__)


@router.get("/widgets")
async def get_user_widgets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's dashboard widget configuration"""
    try:
        widgets = dashboard_customization.get_user_widgets(current_user.id, current_user.role.value.lower())
        return {"widgets": widgets}
    except SQLAlchemyError as e:
        logger.error("Database error fetching dashboard widgets for user_id=%s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="تعذر جلب إعدادات لوحة التحكم")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget configuration for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="تعذر جلب إعدادات لوحة التحكم")


@router.put("/widgets")
async def update_user_widgets(
    widgets: List[Dict],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's dashboard widget configuration"""
    try:
        success = dashboard_customization.update_user_widgets(current_user.id, widgets)
        if not success:
            raise HTTPException(status_code=400, detail="إعداد عناصر اللوحة غير صالح")

        return {"message": "تم تحديث إعدادات لوحة التحكم بنجاح"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget update request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="تعذر تحديث إعدادات لوحة التحكم")


@router.post("/widgets/reset")
async def reset_user_widgets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset user's dashboard widgets to role-based defaults"""
    try:
        success = dashboard_customization.reset_user_widgets(current_user.id, current_user.role.value.lower())
        if not success:
            raise HTTPException(status_code=500, detail="تعذر إعادة ضبط إعدادات لوحة التحكم")

        return {"message": "تمت إعادة ضبط إعدادات لوحة التحكم إلى الوضع الافتراضي"}
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard reset request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="تعذر إعادة ضبط إعدادات لوحة التحكم")


@router.patch("/widgets/{widget_id}/toggle")
async def toggle_widget(
    widget_id: str,
    enabled: bool,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle a specific widget on/off"""
    try:
        success = dashboard_customization.toggle_widget(current_user.id, widget_id, enabled)
        if not success:
            raise HTTPException(status_code=404, detail="العنصر غير موجود أو العملية غير صالحة")

        return {"message": f"تم {'تفعيل' if enabled else 'تعطيل'} العنصر بنجاح"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard toggle request for user_id=%s widget_id=%s: %s", current_user.id, widget_id, str(e))
        raise HTTPException(status_code=500, detail="تعذر تغيير حالة العنصر")


@router.put("/widgets/reorder")
async def reorder_widgets(
    widget_order: List[str],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update widget order"""
    try:
        success = dashboard_customization.reorder_widgets(current_user.id, widget_order)
        if not success:
            raise HTTPException(status_code=400, detail="ترتيب العناصر غير صالح")

        return {"message": "تم تحديث ترتيب العناصر بنجاح"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard reorder request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="تعذر تحديث ترتيب العناصر")


@router.get("/widgets/available")
async def get_available_widgets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available widgets for user's role"""
    try:
        widgets = dashboard_customization.get_available_widgets(current_user.role.value.lower())
        return {"widgets": widgets}
    except (TypeError, ValueError) as e:
        logger.warning("Invalid role while fetching available dashboard widgets for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="تعذر جلب العناصر المتاحة")
