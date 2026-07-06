"""
Advanced Analytics Endpoints — All 33 Metrics
Covers: Network (1-7), Governorate (8-14), KG (15-22),
        Child (23-27), Predictive (28-31), Governance (32-33)
"""
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import distinct as sqla_distinct
from sqlalchemy.orm import Session

import models
from database import get_db
from dependencies import require_admin
from analytics_gap_service import AnalyticsGapService
from schemas.chart_dto import LayerMetricsResponse
from cache_service import dashboard_cache

router = APIRouter(prefix="/analytics", tags=["Advanced Analytics"])


@router.get(
    "/network",
    response_model=dict,
    summary="Network-level analytics (Metrics 1–7)",
)
async def get_network_analytics(
    locale: str = Query("ar", description="Response locale: 'ar' or 'en'"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 7 network-wide metrics: equity index, capacity pressure,
    digital engagement, license expiry distribution, attendance rate,
    staff attrition proxy, and improvement velocity trend.
    """
    cache_key = f"adv_analytics:network:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_network_metrics(locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/governorate/{gov_name}",
    response_model=dict,
    summary="Governorate-level analytics (Metrics 8–14)",
)
async def get_governorate_analytics(
    gov_name: str = Path(..., description="Governorate name string (e.g. 'عمّان')"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 7 governorate-level metrics: inter-KG variance, chronic
    absenteeism, NPS, incident density, report submission rate,
    enrollment growth, and average GQI.
    """
    cache_key = f"adv_analytics:governorate:{gov_name}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_governorate_metrics(gov_name, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/kg/{kg_id}",
    response_model=dict,
    summary="Kindergarten-level analytics (Metrics 15–22)",
)
async def get_kg_analytics(
    kg_id: int = Path(..., description="Kindergarten numeric ID"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 8 KG-level metrics: child risk composite, parent engagement,
    teacher timeliness, meal compliance, health alert density,
    data quality, age appropriateness, and safeguarding resolution rate.
    """
    cache_key = f"adv_analytics:kg:{kg_id}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_kg_metrics(kg_id, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/child/{child_id}",
    response_model=dict,
    summary="Child-level analytics (Metrics 23–27)",
)
async def get_child_analytics(
    child_id: int = Path(..., description="Child numeric ID"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 5 child-level metrics: attendance pattern, development
    profile (radar), engagement score, incident history, and health alerts.
    """
    cache_key = f"adv_analytics:child:{child_id}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_child_metrics(child_id, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/predictive",
    response_model=dict,
    summary="Predictive analytics (Metrics 28–31)",
)
async def get_predictive_analytics(
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 4 predictive metrics: dropout risk per KG, performance
    trajectory classification, 3-month enrollment forecast, and
    attendance–incident cross-correlation.
    """
    cache_key = f"adv_analytics:predictive:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_predictive_metrics(locale).model_dump(mode="json"),
        ttl_seconds=3600
    )


@router.get(
    "/governance",
    response_model=dict,
    summary="Governance analytics (Metrics 32–33)",
)
async def get_governance_analytics(
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 2 governance metrics: enhanced GQI radar (6 sub-indicators
    including wired DataQualityMetric) and network health composite bar.
    """
    cache_key = f"adv_analytics:governance:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_governance_metrics(locale).model_dump(mode="json"),
        ttl_seconds=3600
    )


@router.get(
    "/governorates",
    summary="List all distinct governorate names available for analytics",
)
async def list_governorates(
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """Returns the distinct governorate name strings usable in /governorate/{gov_name}."""
    rows = (
        db.query(sqla_distinct(models.Kindergarten.governorate))
        .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        .all()
    )
    return {"governorates": sorted(r[0] for r in rows if r[0])}
