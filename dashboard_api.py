"""
Dashboard customization API endpoints
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Dict
from dependencies import get_current_user
from dashboard_customization import dashboard_customization
import models

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Customization"])
logger = logging.getLogger(__name__)


@router.get("/widgets")
async def get_user_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        widgets = dashboard_customization.get_user_widgets(current_user.id, current_user.role.value.lower())
        return {"widgets": widgets}
    except SQLAlchemyError as e:
        logger.error("Database error fetching dashboard widgets for user_id=%s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard widget configuration")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget configuration for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard widget configuration")


@router.put("/widgets")
async def update_user_widgets(
    widgets: List[Dict],
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.update_user_widgets(current_user.id, widgets)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid widget configuration")

        return {"message": "Dashboard widget configuration updated"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget update request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update dashboard widget configuration")


@router.post("/widgets/reset")
async def reset_user_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.reset_user_widgets(current_user.id, current_user.role.value.lower())
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset dashboard widget configuration")

        return {"message": "Dashboard widgets reset to role defaults"}
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard reset request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to reset dashboard widget configuration")


@router.patch("/widgets/{widget_id}/toggle")
async def toggle_widget(
    widget_id: str,
    enabled: bool,
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.toggle_widget(current_user.id, widget_id, enabled)
        if not success:
            raise HTTPException(status_code=404, detail="Widget not found or operation invalid")

        return {"message": f"Widget {'enabled' if enabled else 'disabled'}"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard toggle request for user_id=%s widget_id=%s: %s", current_user.id, widget_id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update widget state")


@router.put("/widgets/reorder")
async def reorder_widgets(
    widget_order: List[str],
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.reorder_widgets(current_user.id, widget_order)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid widget order")

        return {"message": "Widget order updated"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard reorder request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update widget order")


@router.get("/widgets/available")
async def get_available_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        widgets = dashboard_customization.get_available_widgets(current_user.role.value.lower())
        return {"widgets": widgets}
    except (TypeError, ValueError) as e:
        logger.warning("Invalid role while fetching available dashboard widgets for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch available widgets")
