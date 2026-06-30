"""ai/embeddings.py — Phase 5 Semantic Search

Implements:
  5.3  Nightly embedding job for observations.observation_text
  5.4  Nightly embedding job for daily_reports.activities / notes
  5.5  Similarity search helper used by the supervisor API endpoint

Embeddings are produced by Ollama nomic-embed-text (768-dim) and stored in
ai_embeddings.  On SQLite the table exists but similarity search is skipped
(returns empty list); the embedding jobs still run so the table stays
populated for testing.

APScheduler wiring (add to main.py lifespan):
    from ai.embeddings import run_embedding_daily_jobs
    scheduler.add_job(run_embedding_daily_jobs, "cron", hour=5, minute=0,
                      id="embedding_daily_jobs")
"""
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import List, Optional, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, init_db
from models import AIEmbedding, AIJobLog

logger = logging.getLogger(__name__)

_MODEL     = settings.OLLAMA_EMBED_MODEL   # "nomic-embed-text"
_DIM       = settings.OLLAMA_EMBED_DIM     # 768
_RULE_VER  = "embed-v1.0"
_BATCH     = 50   # rows per Ollama call batch


def _now_utc() -> datetime:
    return datetime.now(_JORDAN_TZ)


# ---------------------------------------------------------------------------
# Ollama embedding call
# ---------------------------------------------------------------------------

def _embed(text_input: str) -> Optional[List[float]]:
    """Return a 768-dim embedding list, or None on failure."""
    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{settings.OLLAMA_URL}/api/embeddings",
                json={"model": _MODEL, "prompt": text_input},
            )
        resp.raise_for_status()
        vec = resp.json().get("embedding", [])
        if len(vec) != _DIM:
            logger.warning("embed: unexpected dim %d (expected %d)", len(vec), _DIM)
            return None
        return vec
    except Exception as exc:
        logger.warning("embed: ollama error: %s", exc)
        return None


def _ollama_reachable() -> bool:
    try:
        with httpx.Client(timeout=5) as client:
            client.get(f"{settings.OLLAMA_URL}/api/tags")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Job log helpers
# ---------------------------------------------------------------------------

def _start_job(db: Session, job_name: str) -> AIJobLog:
    job = AIJobLog(
        job_name=job_name,
        job_type="embedding",
        started_at=_now_utc(),
        status="RUNNING",
        records_in=0,
        records_out=0,
        model_version=_RULE_VER,
        prompt_version="n/a",
    )
    db.add(job)
    db.flush()
    return job


def _finish_job(db: Session, job: AIJobLog, out: int, error: Optional[str] = None) -> None:
    job.finished_at = _now_utc()
    job.records_out = out
    job.status = "SUCCESS" if error is None else "FAILED"
    if error:
        job.error_message = error[:500]
    db.commit()


# ---------------------------------------------------------------------------
# Upsert helper
# ---------------------------------------------------------------------------

def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:64]


def _upsert_embedding(
    db: Session,
    source_table: str,
    source_id: int,
    chunk_index: int,
    content: str,
    vec: List[float],
) -> bool:
    """Store or replace a single embedding row.

    Returns True if the row was new or updated, False if content unchanged.
    """
    chash = _content_hash(content)
    existing = (
        db.query(AIEmbedding)
        .filter(
            AIEmbedding.source_table == source_table,
            AIEmbedding.source_id   == source_id,
            AIEmbedding.chunk_index == chunk_index,
            AIEmbedding.model_name  == _MODEL,
        )
        .first()
    )
    if existing:
        if existing.content_hash == chash:
            return False  # content unchanged — skip
        existing.embedding    = json.dumps(vec)
        existing.content_hash = chash
        existing.computed_at  = _now_utc()
    else:
        db.add(AIEmbedding(
            source_table = source_table,
            source_id    = source_id,
            chunk_index  = chunk_index,
            embedding    = json.dumps(vec),
            model_name   = _MODEL,
            content_hash = chash,
            computed_at  = _now_utc(),
        ))
    return True


# ---------------------------------------------------------------------------
# 5.3 — Embed observations.observation_text
# ---------------------------------------------------------------------------

_OBSERVATION_SQL = text("""
    SELECT id, observation_text
    FROM   observations
    WHERE  observation_text IS NOT NULL
      AND  deleted_at IS NULL
    ORDER  BY id
""")


def _run_observation_embeddings(db: Session) -> int:
    job = _start_job(db, "embed_observations")
    try:
        rows = db.execute(_OBSERVATION_SQL).fetchall()
        count = 0
        for row in rows:
            text_val = (row.observation_text or "").strip()
            if not text_val:
                continue
            vec = _embed(text_val)
            if vec is None:
                continue
            updated = _upsert_embedding(db, "observations", row.id, 0, text_val, vec)
            if updated:
                count += 1
            if count % _BATCH == 0:
                db.flush()

        db.flush()
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("embed_observations failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# 5.4 — Embed daily_reports.activities and daily_reports.notes
# ---------------------------------------------------------------------------

_DAILY_REPORT_SQL = text("""
    SELECT id, activities, notes
    FROM   daily_reports
    WHERE  (activities IS NOT NULL OR notes IS NOT NULL)
      AND  deleted_at IS NULL
    ORDER  BY id
""")


def _run_daily_report_embeddings(db: Session) -> int:
    job = _start_job(db, "embed_daily_reports")
    try:
        rows = db.execute(_DAILY_REPORT_SQL).fetchall()
        count = 0
        for row in rows:
            # chunk_index=0 → activities, chunk_index=1 → notes
            for chunk_idx, raw in enumerate([row.activities, row.notes]):
                text_val = (raw or "").strip()
                if not text_val:
                    continue
                vec = _embed(text_val)
                if vec is None:
                    continue
                updated = _upsert_embedding(
                    db, "daily_reports", row.id, chunk_idx, text_val, vec
                )
                if updated:
                    count += 1
            if count % _BATCH == 0:
                db.flush()

        db.flush()
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("embed_daily_reports failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# 5.5 — Similarity search (PostgreSQL only)
# ---------------------------------------------------------------------------

_SIMILARITY_SQL = text("""
    SELECT
        ae.source_table,
        ae.source_id,
        ae.chunk_index,
        1 - (ae.embedding::vector <=> CAST(:query_vec AS vector)) AS cosine_similarity
    FROM ai_embeddings ae
    WHERE ae.source_table = :source_table
      AND ae.model_name   = :model
    ORDER BY ae.embedding::vector <=> CAST(:query_vec AS vector)
    LIMIT  :top_k
""")


def find_similar(
    db: Session,
    query: str,
    source_table: str = "observations",
    top_k: int = 10,
) -> List[Tuple[str, int, int, float]]:
    """Return top-k similar rows as (source_table, source_id, chunk_index, score).

    Returns an empty list on SQLite or when Ollama is unreachable.
    """
    from database import engine as _engine
    if _engine.dialect.name != "postgresql":
        return []

    vec = _embed(query)
    if vec is None:
        return []

    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    rows = db.execute(
        _SIMILARITY_SQL,
        {
            "query_vec":    vec_str,
            "source_table": source_table,
            "model":        _MODEL,
            "top_k":        top_k,
        },
    ).fetchall()
    return [
        (r.source_table, r.source_id, r.chunk_index, float(r.cosine_similarity))
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 5.7 — Embed incidents.description (nightly job + search)
# ---------------------------------------------------------------------------

_INCIDENT_SQL = text("""
    SELECT id, description
    FROM   incidents
    WHERE  description IS NOT NULL
      AND  deleted_at IS NULL
    ORDER  BY id
""")

_INCIDENT_SIMILARITY_SQL = text("""
    SELECT
        ae.source_id AS incident_id,
        1 - (ae.embedding::vector <=> CAST(:query_vec AS vector)) AS score
    FROM ai_embeddings ae
    WHERE ae.source_table = 'incidents'
      AND ae.model_name   = :model
    ORDER BY ae.embedding::vector <=> CAST(:query_vec AS vector)
    LIMIT  :top_k
""")


def _run_incident_embeddings(db: Session) -> int:
    job = _start_job(db, "embed_incidents")
    try:
        rows = db.execute(_INCIDENT_SQL).fetchall()
        count = 0
        for row in rows:
            text_val = (row.description or "").strip()
            if not text_val:
                continue
            vec = _embed(text_val)
            if vec is None:
                continue
            updated = _upsert_embedding(db, "incidents", row.id, 0, text_val, vec)
            if updated:
                count += 1
            if count % _BATCH == 0:
                db.flush()

        db.flush()
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("embed_incidents failed: %s", exc)
        return 0


def search_incidents(
    db: Session,
    query: str,
    limit: int = 10,
) -> List[dict]:
    """Return top-k incidents by semantic similarity. PostgreSQL + pgvector only."""
    from database import engine as _engine
    if _engine.dialect.name != "postgresql":
        return []

    vec = _embed(query)
    if vec is None:
        return []

    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    rows = db.execute(
        _INCIDENT_SIMILARITY_SQL,
        {"query_vec": vec_str, "model": _MODEL, "top_k": limit},
    ).fetchall()
    return [{"incident_id": r.incident_id, "score": float(r.score)} for r in rows]


# ---------------------------------------------------------------------------
# 5.6 — Activity recommendation engine (cosine sim to EXCEEDS-mastery activities)
# ---------------------------------------------------------------------------

_EXCEEDS_ACTIVITIES_SQL = text("""
    SELECT DISTINCT dr.activities
    FROM   daily_reports dr
    JOIN   observations obs ON obs.child_id = dr.child_id
                            AND DATE(obs.observed_at) = dr.date
    WHERE  obs.child_id  = :child_id
      AND  obs.mastery_level = 'EXCEEDS'
      AND  dr.activities IS NOT NULL
      AND  dr.deleted_at IS NULL
    LIMIT  50
""")

_ACTIVITY_OUTCOME_SQL = text("""
    SELECT indicator_code, description
    FROM   curriculum_outcomes
""")

_ALREADY_DONE_SQL = text("""
    SELECT DISTINCT activities
    FROM   daily_reports
    WHERE  child_id = :child_id
      AND  activities IS NOT NULL
      AND  deleted_at IS NULL
""")


def recommend_activities(
    db: Session,
    child_id: int,
    limit: int = 5,
) -> List[dict]:
    """Return activity recommendations for a child using cosine similarity.

    Finds activities that preceded EXCEEDS-mastery observations for this child,
    then ranks curriculum outcomes by similarity. Returns empty list on SQLite
    or when Ollama is unreachable.
    """
    from database import engine as _engine
    if _engine.dialect.name != "postgresql":
        return []

    # Build query embedding from activities that led to EXCEEDS mastery
    exceeds_rows = db.execute(_EXCEEDS_ACTIVITIES_SQL, {"child_id": child_id}).fetchall()
    if not exceeds_rows:
        return []

    combined_text = " ".join(r.activities for r in exceeds_rows if r.activities)[:2000]
    query_vec = _embed(combined_text)
    if query_vec is None:
        return []

    # Rank curriculum outcomes by cosine similarity to that combined text
    outcomes = db.execute(_ACTIVITY_OUTCOME_SQL).fetchall()
    if not outcomes:
        return []

    results = []
    for outcome in outcomes:
        desc_vec = _embed(outcome.description)
        if desc_vec is None:
            continue
        # Cosine similarity
        import numpy as np
        a = np.array(query_vec, dtype=float)
        b = np.array(desc_vec, dtype=float)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        score = float(np.dot(a, b) / norm) if norm > 0 else 0.0
        results.append({
            "indicator_code": outcome.indicator_code,
            "description":    outcome.description,
            "score":          round(score, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

_EMBED_JOBS = [
    ("embed_observations",    _run_observation_embeddings),
    ("embed_daily_reports",   _run_daily_report_embeddings),
    ("embed_incidents",       _run_incident_embeddings),
]


async def run_embedding_daily_jobs() -> None:
    """Run all Phase-5 embedding jobs.

    Skips entirely if Ollama is unreachable; each job is isolated so one
    failure does not abort the others.

    APScheduler configuration (main.py lifespan):
        from ai.embeddings import run_embedding_daily_jobs
        scheduler.add_job(run_embedding_daily_jobs, "cron", hour=5, minute=0,
                          id="embedding_daily_jobs")
    """
    try:
        init_db()
    except Exception as exc:
        logger.warning("run_embedding_daily_jobs: init_db: %s", exc)

    if not _ollama_reachable():
        logger.info("embedding_jobs: Ollama not reachable — skipping all jobs")
        return

    db: Session = SessionLocal()
    try:
        for name, fn in _EMBED_JOBS:
            try:
                n = fn(db)
                logger.info("embedding_jobs: %s → %d records", name, n)
            except Exception as exc:
                db.rollback()
                logger.warning("embedding_jobs: %s failed: %s", name, exc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("run_embedding_daily_jobs fatal: %s", exc)
    finally:
        db.close()
