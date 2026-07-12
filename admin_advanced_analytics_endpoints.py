"""
Advanced Analytics Endpoints — All 33 Metrics
Covers: Network (1-7), Geographic/Governorate-District-Area (8-14), Nursery (15-22),
        Child (23-27), Predictive (28-31), Governance (32-33)

Mounted at ``/api/admin`` (see main.py) -> effective prefix ``/api/admin/analytics``.

Every metric-returning route delegates to ``analytics.metric_calculators``, which
wraps ``AnalyticsGapService`` (single source of computation) and annotates each
metric with an explicit ``data_state`` (valid | missing | insufficient_data |
suppressed | not_applicable) so a genuine 0 is never confused with absent data.
Metric metadata (canonical bilingual titles, dimensions, drill-down path) is served
from ``analytics.metric_registry`` via ``/analytics/catalog``.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import distinct as sqla_distinct
from sqlalchemy.orm import Session

import models
from database import get_db
from dependencies import require_admin, get_current_user
from api.analytics.scope_domain import can_view_child_detail
from cache_service import dashboard_cache

from analytics import metric_calculators as mc
from analytics import metric_registry as mr

router = APIRouter(prefix="/analytics", tags=["Advanced Analytics"])


@router.get(
    "/catalog",
    summary="Canonical metric catalog (registry metadata, not values)",
)
async def get_metric_catalog(
    locale: str = Query("ar", description="Response locale for dimension labels: 'ar' or 'en'"),
    layer: Optional[str] = Query(None, description="Filter by layer"),
    dimension: Optional[str] = Query(None, description="Filter by supported dimension"),
    _: dict = Depends(require_admin),
) -> dict:
    """Serve the metric registry so the UI has one source for titles, dimension
    labels, the drill-down path, and the data-state contract."""
    keys = mr.list_metrics(layer=layer, dimension=dimension)
    return {
        "meta": mr.meta(),
        "drilldown_path": mr.DRILLDOWN_PATH,
        "dimension_labels": {k: v for k, v in mr.DIMENSION_LABELS.items()},
        "metrics": [mr.get_metric(k) for k in keys],
    }


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
        lambda: mc.compute_network(db, locale).model_dump(mode="json"),
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
    Returns 7 governorate-level metrics: inter-nursery variance, chronic
    absenteeism, NPS, incident density, report submission rate,
    enrollment growth, and average GQI.
    """
    cache_key = f"adv_analytics:governorate:{gov_name}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_geographic(db, "GOVERNORATE", gov_name, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/district/{district_name}",
    response_model=dict,
    summary="District-level analytics (Metrics 8–14)",
)
async def get_district_analytics(
    district_name: str = Path(..., description="District name string (e.g. 'الجامعة')"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """Returns 7 district-level metrics (same family as governorate, scoped to district)."""
    cache_key = f"adv_analytics:district:{district_name}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_geographic(db, "DISTRICT", district_name, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/area/{area_name}",
    response_model=dict,
    summary="Area/City-level analytics (Metrics 8–14)",
)
async def get_area_analytics(
    area_name: str = Path(..., description="Area (City) name string (e.g. 'صويلح')"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """Returns 7 area-level metrics. The AREA dimension is surfaced to users as
    the 'City' drill-down level (no separate City model exists)."""
    cache_key = f"adv_analytics:area:{area_name}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_geographic(db, "AREA", area_name, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/kg/{kg_id}",
    response_model=dict,
    summary="Nursery-level analytics (Metrics 15–22)",
)
async def get_kg_analytics(
    kg_id: int = Path(..., description="Nursery numeric ID (kindergarten_id)"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """
    Returns 8 nursery-level metrics: child risk composite, parent engagement,
    teacher timeliness, meal compliance, health alert density,
    data quality, age appropriateness, and safeguarding resolution rate.
    """
    cache_key = f"adv_analytics:kg:{kg_id}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_kindergarten(db, kg_id, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )


@router.get(
    "/child/{child_id}",
    response_model=dict,
    summary="Child-level analytics (Metrics 23–27) — restricted (PII)",
)
async def get_child_analytics(
    child_id: int = Path(..., description="Child numeric ID"),
    locale: str = Query("ar"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    """
    Returns 5 child-level metrics: attendance pattern, development
    profile (radar), engagement score, incident history, and health alerts.

    These metrics are ``privacy_level=restricted`` (individual-child PII). Access is
    governed by the ``analytics:child_detail`` capability (ADMIN-only). Authenticated
    callers without it receive the metric shapes with ``data_state=suppressed`` and no
    underlying values, rather than a hard 403 — so the UI degrades gracefully.
    """
    authorized = can_view_child_detail(current_user)
    cache_key = f"adv_analytics:child:{child_id}:{locale}:{int(authorized)}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_child(db, child_id, locale, authorized=authorized).model_dump(mode="json"),
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
    Returns 4 predictive metrics: dropout risk per nursery, performance
    trajectory classification, 3-month enrollment forecast, and
    attendance–incident cross-correlation.
    """
    cache_key = f"adv_analytics:predictive:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: mc.compute_predictive(db, locale).model_dump(mode="json"),
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
        lambda: mc.compute_governance(db, locale).model_dump(mode="json"),
        ttl_seconds=3600
    )


# ─────────────────────────────────────────────────────────────────────────────
# Drill-down filter option lists (governorate -> district -> area(City) -> nursery)
# ─────────────────────────────────────────────────────────────────────────────

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


@router.get(
    "/districts",
    summary="List all distinct district names available for analytics",
)
async def list_districts(
    governorate: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """Returns the distinct district name strings, optionally filtered by governorate."""
    query = db.query(sqla_distinct(models.Kindergarten.district)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if governorate:
        query = query.filter(models.Kindergarten.governorate == governorate)
    rows = query.all()
    return {"districts": sorted(r[0] for r in rows if r[0])}


@router.get(
    "/areas",
    summary="List all distinct area (City) names available for analytics",
)
async def list_areas(
    governorate: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    """Returns the distinct area (City) name strings, optionally filtered by governorate and/or district."""
    query = db.query(sqla_distinct(models.Kindergarten.area)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if governorate:
        query = query.filter(models.Kindergarten.governorate == governorate)
    if district:
        query = query.filter(models.Kindergarten.district == district)
    rows = query.all()
    return {"areas": sorted(r[0] for r in rows if r[0])}
