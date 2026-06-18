"""
FastAPI router for the Jordan Heatmap API.
Mount at /api/heatmap in main.py:
    from heatmap.backend.api.router import router as heatmap_router
    app.include_router(heatmap_router, prefix="/api/heatmap")
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
import io

from .models import (
    DailyPayloadIn, IndicatorResponse, CorrelationRow,
    AlertOut, PipelineResult,
)
from ..etl.ingest import ingest_records
from ..etl.compute import compute_dataframe, impute_missing, INDICATOR_MAP
from ..analytics.stats import compute_full_stats, stats_to_csv, rolling_health_alert_hotspot
from ..alerts.engine import get_alerts, acknowledge_alert, evaluate_alerts
from ..etl.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["heatmap"])

DATA_DIR   = Path(__file__).parent.parent.parent / "data"
STATIC_DIR = Path("static/heatmap")

# ---------------------------------------------------------------------------
# Shared in-memory cache (refresh on ingest)
# ---------------------------------------------------------------------------
_computed_cache: pd.DataFrame = pd.DataFrame()
_stats_cache:    pd.DataFrame = pd.DataFrame()


def _load_test_data() -> pd.DataFrame:
    csv = DATA_DIR / "test_data.csv"
    if csv.exists():
        df = pd.read_csv(csv)
        return impute_missing(df)
    return pd.DataFrame()


def _get_computed() -> pd.DataFrame:
    global _computed_cache
    if _computed_cache.empty:
        raw = _load_test_data()
        if not raw.empty:
            _computed_cache = compute_dataframe(raw)
    return _computed_cache


def _get_stats() -> pd.DataFrame:
    global _stats_cache
    if _stats_cache.empty:
        comp = _get_computed()
        if not comp.empty:
            _stats_cache = compute_full_stats(comp, INDICATOR_MAP)
    return _stats_cache


# ---------------------------------------------------------------------------
# GeoJSON endpoints
# ---------------------------------------------------------------------------

@router.get("/geojson", summary="Latest Jordan GeoJSON with indicator overlays")
async def get_geojson(date: Optional[str] = Query(None)):
    gj_path = DATA_DIR / "jordan_admin.geojson"
    if not gj_path.exists():
        raise HTTPException(404, "GeoJSON not found")

    with open(gj_path, encoding="utf-8") as f:
        gj = json.load(f)

    comp = _get_computed()
    if not comp.empty:
        if date:
            latest = comp[comp["date"] == date]
        else:
            latest = comp.sort_values("date").groupby("admin_id").last().reset_index()
        lookup = {r["admin_id"]: r for r in latest.to_dict("records")}

        indicator_cols = [
            "kindergarten_status","children_enrollment","staff_classrooms",
            "safety_incidents","reports_attendance","tasks_governance",
        ]
        for feat in gj["features"]:
            aid = feat["properties"].get("admin_code") or feat["properties"].get("id")
            if aid in lookup:
                row = lookup[aid]
                for col in indicator_cols:
                    if col in row:
                        feat["properties"][col] = round(float(row[col]), 2)

    return JSONResponse(content=gj)


@router.get("/geojson/intensity-points", summary="Intensity point array [lat, lng, intensity] for the Jordan Heat Map")
async def get_intensity_points(
    indicator: str = Query("safety_incidents"),
    date: Optional[str] = Query(None),
):
    comp = _get_computed()
    if comp.empty:
        return []
    if date:
        comp = comp[comp["date"] == date]
    else:
        comp = comp.sort_values("date").groupby("admin_id").last().reset_index()

    if indicator not in comp.columns:
        raise HTTPException(400, f"Unknown indicator: {indicator}")

    # centroids from GeoJSON
    gj_path = DATA_DIR / "jordan_admin.geojson"
    if not gj_path.exists():
        return []
    with open(gj_path, encoding="utf-8") as f:
        gj = json.load(f)

    centroids = {}
    for feat in gj["features"]:
        aid = feat["properties"].get("admin_code") or feat["properties"].get("id")
        coords = feat["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        centroids[aid] = [sum(lats)/len(lats), sum(lons)/len(lons)]

    points = []
    max_val = comp[indicator].max() or 1.0
    for _, row in comp.iterrows():
        aid = row["admin_id"]
        if aid in centroids:
            lat, lng = centroids[aid]
            intensity = float(row[indicator]) / float(max_val)
            points.append([lat, lng, round(intensity, 3)])

    return points


# ---------------------------------------------------------------------------
# Indicators endpoints
# ---------------------------------------------------------------------------

@router.get("/indicators", response_model=list[IndicatorResponse])
async def get_indicators(
    admin_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
):
    comp = _get_computed()
    if comp.empty:
        return []
    if admin_id:
        comp = comp[comp["admin_id"] == admin_id]
    if date_from:
        comp = comp[comp["date"] >= date_from]
    if date_to:
        comp = comp[comp["date"] <= date_to]

    out_cols = ["date","admin_id","kindergarten_status","children_enrollment",
                "staff_classrooms","safety_incidents","reports_attendance","tasks_governance"]
    result_df = comp[[c for c in out_cols if c in comp.columns]]
    return result_df.to_dict("records")


@router.post("/indicators/ingest", response_model=PipelineResult)
async def ingest_indicators(
    records: list[DailyPayloadIn],
    background_tasks: BackgroundTasks,
):
    global _computed_cache, _stats_cache
    raw_records = [r.model_dump() for r in records]
    valid, errors = ingest_records(raw_records)

    if valid:
        raw_df = pd.DataFrame(valid)
        raw_df = impute_missing(raw_df)
        new_comp = compute_dataframe(raw_df)
        _computed_cache = pd.concat([_computed_cache, new_comp], ignore_index=True).drop_duplicates(
            subset=["date", "admin_id"], keep="last"
        )
        _stats_cache = pd.DataFrame()  # invalidate

    return {
        "date": (pd.Timestamp.now().strftime("%Y%m%d")),
        "rows_processed": len(valid),
        "errors": errors,
        "alerts": [],
        "hotspots": [],
    }


@router.post("/pipeline/run", response_model=PipelineResult)
async def trigger_pipeline(csv_path: str = Query(str(DATA_DIR / "test_data.csv"))):
    """Manually trigger the full ETL pipeline (for testing/admin use)."""
    global _computed_cache, _stats_cache
    result = run_pipeline(csv_path, source_type="csv")
    _computed_cache = pd.DataFrame()  # force reload
    _stats_cache    = pd.DataFrame()
    return result


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

@router.get("/analytics/correlations", response_model=list[CorrelationRow])
async def get_correlations(main_indicator: Optional[str] = Query(None)):
    stats = _get_stats()
    if stats.empty:
        return []
    if main_indicator:
        stats = stats[stats["main_indicator"] == main_indicator]
    return stats.fillna(0).to_dict("records")


@router.get("/analytics/correlations/csv")
async def get_correlations_csv():
    stats = _get_stats()
    if stats.empty:
        raise HTTPException(404, "No stats available")
    csv_str = stats_to_csv(stats)
    return StreamingResponse(
        io.StringIO(csv_str),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=correlations.csv"},
    )


@router.get("/analytics/regression/{main_indicator}")
async def get_regression(main_indicator: str):
    from ..analytics.ols import run_all_regressions
    comp = _get_computed()
    if comp.empty:
        return []
    results = run_all_regressions(comp, INDICATOR_MAP)
    if main_indicator not in results:
        raise HTTPException(404, f"No regression results for {main_indicator!r}")
    return results[main_indicator].to_dict("records")


@router.get("/analytics/timeseries/{admin_id}")
async def get_timeseries(admin_id: str, indicator: str = Query("safety_incidents")):
    comp = _get_computed()
    if comp.empty:
        return []
    subset = comp[comp["admin_id"] == admin_id].sort_values("date")
    if subset.empty:
        raise HTTPException(404, f"No data for admin_id={admin_id!r}")
    if indicator not in subset.columns:
        raise HTTPException(400, f"Unknown indicator: {indicator}")
    return subset[["date", indicator]].to_dict("records")


@router.get("/analytics/hotspots")
async def get_hotspots():
    comp = _get_computed()
    if comp.empty:
        return []
    return rolling_health_alert_hotspot(comp)


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(unacknowledged_only: bool = Query(False)):
    alerts = get_alerts(unacknowledged_only)
    return [
        AlertOut(
            id=a.id,
            severity=a.severity,
            admin_id=a.admin_id,
            rule=a.rule,
            message=a.message,
            meta=a.meta,
            created_at=a.created_at,
            acknowledged=a.acknowledged,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: str):
    if not acknowledge_alert(alert_id):
        raise HTTPException(404, f"Alert {alert_id!r} not found")
    return {"status": "acknowledged"}
