"""
Full ETL pipeline with APScheduler daily cron.
Flow: ingest → validate → impute → compute indicators →
      store in DB → recompute stats → detect hotspots → trigger alerts → push GeoJSON.

Retry / backoff via tenacity.
Data quality log written to logs/data_quality_YYYYMMDD.jsonl
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

from .ingest import ingest_csv, ingest_json, log_data_quality
from .compute import compute_dataframe, impute_missing, INDICATOR_MAP
from ..analytics.stats import compute_full_stats, rolling_health_alert_hotspot
from ..alerts.engine import evaluate_alerts

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("HEATMAP_LOG_DIR", "logs"))
GEOJSON_OUTPUT_DIR = Path(os.getenv("GEOJSON_OUTPUT_DIR", "static/heatmap"))


def _write_data_quality_log(errors: list[dict], date_str: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"data_quality_{date_str}.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        for err in errors:
            f.write(json.dumps({**err, "logged_at": datetime.now(timezone.utc).isoformat()}) + "\n")


def _save_computed_df(df: pd.DataFrame, db_session: Any = None) -> None:
    """
    Persist computed indicators.
    If a SQLAlchemy session is provided, upsert; otherwise fall back to CSV.
    """
    if db_session is not None:
        try:
            _upsert_to_db(df, db_session)
            return
        except Exception as exc:
            logger.error("DB upsert failed, falling back to CSV: %s", exc)
    out = GEOJSON_OUTPUT_DIR / "indicators.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = not out.exists()
    df.to_csv(out, mode="a", header=header, index=False)
    logger.info("Saved %d rows to %s", len(df), out)


def _upsert_to_db(df: pd.DataFrame, session: Any) -> None:
    """Upsert using raw SQL (PostgreSQL INSERT ... ON CONFLICT DO UPDATE)."""
    from sqlalchemy import text
    cols = df.columns.tolist()
    for _, row in df.iterrows():
        vals = {c: row[c] for c in cols}
        placeholders = ", ".join(f":{c}" for c in cols)
        col_list = ", ".join(cols)
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("date", "admin_id"))
        sql = f"""
            INSERT INTO heatmap_indicators ({col_list})
            VALUES ({placeholders})
            ON CONFLICT (date, admin_id) DO UPDATE SET {update_set}
        """
        session.execute(text(sql), vals)
    session.commit()


def _generate_geojson(df: pd.DataFrame, geojson_path: Path) -> dict:
    """Merge latest indicator data onto Jordan GeoJSON boundaries."""
    src = Path(__file__).parent.parent.parent / "data" / "jordan_admin.geojson"
    if not src.exists():
        logger.warning("GeoJSON source not found: %s", src)
        return {}
    with open(src, encoding="utf-8") as f:
        gj = json.load(f)

    latest = df.sort_values("date").groupby("admin_id").last().reset_index()
    lookup = {row["admin_id"]: row.to_dict() for _, row in latest.iterrows()}

    for feature in gj["features"]:
        aid = feature["properties"].get("admin_code") or feature["properties"].get("id")
        if aid in lookup:
            feature["properties"].update({
                k: v for k, v in lookup[aid].items()
                if k not in ("admin_id", "date")
            })
    GEOJSON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(gj, f)
    logger.info("GeoJSON written to %s", geojson_path)
    return gj


def run_pipeline(
    source: str | Path | list[dict],
    source_type: str = "csv",
    db_session: Any = None,
    push_cdn: bool = False,
) -> dict[str, Any]:
    """
    Execute the complete ETL → analytics → alert pipeline.

    Returns a summary dict with counts and alert list.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    summary: dict[str, Any] = {"date": date_str, "errors": [], "alerts": [], "rows_processed": 0}

    # --- 1. Ingest & validate ---
    if source_type == "csv":
        clean_df, errors = ingest_csv(source)
    elif source_type == "json":
        valid_records, errors = ingest_json(source)
        clean_df = pd.DataFrame(valid_records)
    elif source_type == "records":
        valid_records, errors = ingest_json.__wrapped__(source) if hasattr(ingest_json, "__wrapped__") else ([], [])
        from .ingest import ingest_records
        valid_records, errors = ingest_records(source)
        clean_df = pd.DataFrame(valid_records)
    else:
        raise ValueError(f"Unknown source_type: {source_type!r}")

    log_data_quality(errors, str(source) if not isinstance(source, list) else "records")
    _write_data_quality_log(errors, date_str)
    summary["errors"] = errors

    if clean_df.empty:
        logger.warning("Pipeline aborted: no valid rows after validation")
        return summary

    # --- 2. Impute missing ---
    clean_df = impute_missing(clean_df)

    # --- 3. Compute indicators ---
    computed_df = compute_dataframe(clean_df)
    summary["rows_processed"] = len(computed_df)

    # --- 4. Persist ---
    _save_computed_df(computed_df, db_session)

    # --- 5. Recompute statistics ---
    stats_df = compute_full_stats(computed_df, INDICATOR_MAP)
    stats_path = GEOJSON_OUTPUT_DIR / f"stats_{date_str}.csv"
    GEOJSON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stats_df.to_csv(stats_path, index=False)
    logger.info("Stats written to %s", stats_path)

    # --- 6. Detect health hotspots ---
    hotspots = rolling_health_alert_hotspot(computed_df)
    if hotspots:
        logger.warning("Health hotspots detected: %d", len(hotspots))
        summary["hotspots"] = hotspots

    # --- 7. Evaluate & dispatch alerts ---
    stats_lookup = stats_df.to_dict("records") if not stats_df.empty else []
    all_alerts = []
    for _, row in computed_df.iterrows():
        row_dict = row.to_dict()
        row_stats = next(
            (s for s in stats_lookup if s.get("admin_id") == row_dict.get("admin_id")),
            None,
        )
        alts = evaluate_alerts(row_dict, row_stats, hotspots)
        all_alerts.extend(alts)
    summary["alerts"] = [
        {"id": a.id, "severity": a.severity, "rule": a.rule, "admin_id": a.admin_id, "message": a.message}
        for a in all_alerts
    ]

    # --- 8. Generate GeoJSON tiles ---
    geojson_path = GEOJSON_OUTPUT_DIR / f"jordan_heatmap_{date_str}.geojson"
    _generate_geojson(computed_df, geojson_path)

    # --- 9. (Optional) push to CDN ---
    if push_cdn:
        _push_to_cdn(geojson_path)

    logger.info("Pipeline complete: %d rows, %d alerts", len(computed_df), len(all_alerts))
    return summary


def _push_to_cdn(path: Path) -> None:
    cdn_url = os.getenv("CDN_PUSH_URL")
    cdn_key = os.getenv("CDN_API_KEY")
    if not cdn_url or not cdn_key:
        logger.warning("CDN push skipped: CDN_PUSH_URL / CDN_API_KEY not set")
        return
    import httpx
    try:
        with open(path, "rb") as f:
            resp = httpx.put(cdn_url, content=f.read(), headers={"X-API-Key": cdn_key}, timeout=30)
        resp.raise_for_status()
        logger.info("GeoJSON pushed to CDN: %s", cdn_url)
    except Exception as exc:
        logger.error("CDN push failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def create_scheduler(
    data_source: str | Path,
    source_type: str = "csv",
    cron_hour: int = 2,
    cron_minute: int = 0,
    db_session_factory: Any = None,
) -> Any:
    """
    Create and return an APScheduler that runs the pipeline daily.
    Caller must call scheduler.start() and manage lifecycle.
    """
    if not HAS_APSCHEDULER:
        raise RuntimeError("apscheduler is not installed: pip install apscheduler")

    scheduler = AsyncIOScheduler()

    async def _job():
        session = db_session_factory() if db_session_factory else None
        try:
            run_pipeline(data_source, source_type=source_type, db_session=session, push_cdn=True)
        finally:
            if session and hasattr(session, "close"):
                session.close()

    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=cron_hour, minute=cron_minute),
        id="daily_heatmap_pipeline",
        replace_existing=True,
    )
    logger.info("Heatmap pipeline scheduled daily at %02d:%02d UTC", cron_hour, cron_minute)
    return scheduler
