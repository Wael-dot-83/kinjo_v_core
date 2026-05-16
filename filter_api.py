"""
Advanced filtering and search API endpoints
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from database import get_db
from dependencies import get_current_user
from filter_service import filter_service
import models

router = APIRouter(prefix="/api/filters", tags=["Advanced Filtering"])
logger = logging.getLogger(__name__)


@router.get("/preferences")
async def get_user_filter_preferences(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's saved filter preferences"""
    try:
        filters = filter_service.get_user_filters(current_user.id)
        return {"filters": filters}
    except SQLAlchemyError as e:
        logger.error("Database error retrieving filter preferences for user_id=%s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve filter preferences")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Invalid stored filter preferences for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve filter preferences")


@router.put("/preferences")
async def save_user_filter_preferences(
    filters: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save user's filter preferences"""
    try:
        success = filter_service.save_user_filters(current_user.id, filters)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid filter configuration")

        return {"message": "Filter preferences saved successfully"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid filter preference save request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to save filter preferences")


@router.get("/options")
async def get_filter_options(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available filter options based on user permissions"""
    try:
        options = filter_service.get_filter_options(current_user)
        return {"options": options}
    except SQLAlchemyError as e:
        logger.error("Database error retrieving filter options for user_id=%s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve filter options")


@router.get("/search/kindergartens")
async def search_kindergartens(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, description="Maximum number of results"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search kindergartens by name"""
    try:
        if len(q.strip()) < 2:
            raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

        results = filter_service.search_kindergartens(q, current_user, limit)
        return {"results": results}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error("Database error searching kindergartens for user_id=%s query=%s: %s", current_user.id, q, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed")
    except (TypeError, ValueError) as e:
        logger.warning("Invalid kindergarten search request for user_id=%s query=%s: %s", current_user.id, q, str(e))
        raise HTTPException(status_code=500, detail="Search failed")


@router.post("/apply")
async def apply_filters(
    filters: Dict[str, Any],
    entity_type: str = Query(..., description="Type of entity to filter (kindergartens, users, etc.)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Apply filters and return paginated results"""
    try:
        if entity_type == "kindergartens":
            # Apply filters to kindergarten query
            query = db.query(models.Kindergarten)
            query = filter_service.apply_filters_to_query(query, filters, current_user)
            result = filter_service.apply_sorting_and_pagination(query, filters)

            return {
                "entity_type": entity_type,
                "data": result,
                "applied_filters": filters
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported entity type: {entity_type}")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error("Database error applying filters for user_id=%s entity_type=%s: %s", current_user.id, entity_type, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to apply filters")
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Invalid filter application request for user_id=%s entity_type=%s: %s", current_user.id, entity_type, str(e))
        raise HTTPException(status_code=500, detail="Failed to apply filters")


@router.get("/defaults")
async def get_default_filters():
    """Get default filter configuration"""
    return {"filters": filter_service.default_filters}