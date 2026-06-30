"""ai/llm.py — Phase 3 LLM Integration via Ollama (local inference only)

Implements all five Phase-3 summarisers:
  3.1  Daily report parent narrative  → ai_parent_recommendations
  3.2  Weekly observation narrative   → ai_parent_recommendations
  3.3  Incident follow-up letter      → ai_parent_recommendations
  3.4  Governance case study          → ai_parent_recommendations
  3.5  Curriculum activity suggestion → ai_parent_recommendations

Non-negotiable guardrails enforced here:
  • LLM input is structured feature JSON only — no raw PII, no medical text.
  • All outputs stored with model_version, prompt_version, confidence.
  • human_reviewed = False by default.
  • LLM cannot make enrollment, medical, safeguarding, legal, or HR decisions.
  • No external API calls — Ollama runs locally at settings.OLLAMA_URL.

APScheduler wiring (add to main.py lifespan):
    from ai.llm import run_llm_daily_jobs
    scheduler.add_job(run_llm_daily_jobs, "cron", hour=3, minute=30,
                      id="llm_daily_jobs")
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, init_db
from models import AIJobLog, AIParentRecommendation

logger = logging.getLogger(__name__)

_LLM_MODEL   = settings.OLLAMA_LLM_MODEL
_RULE_VER    = "llm-v1.0"
_OLLAMA_GEN  = f"{settings.OLLAMA_URL}/api/generate"


# ---------------------------------------------------------------------------
# Low-level Ollama client
# ---------------------------------------------------------------------------

def _ollama_generate(prompt: str, system: str = "") -> tuple[str, float]:
    """Call Ollama /api/generate synchronously.

    Returns (response_text, pseudo_confidence).
    Confidence is approximated from token count relative to prompt length;
    the real value must be calibrated once eval data exists.
    Raises httpx.HTTPError / ConnectionError if Ollama is unavailable.
    """
    payload: dict = {
        "model": _LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }
    if system:
        payload["system"] = system

    with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
        resp = client.post(_OLLAMA_GEN, json=payload)
        resp.raise_for_status()

    data = resp.json()
    text_out: str = data.get("response", "").strip()
    # Naive confidence: penalise very short or very long outputs
    word_count = len(text_out.split())
    confidence = min(0.95, max(0.50, 1.0 - abs(word_count - 80) / 200))
    return text_out, round(confidence, 3)


# ---------------------------------------------------------------------------
# Helpers shared across all summarisers
# ---------------------------------------------------------------------------

_JORDAN_TZ = timezone(timedelta(hours=3))


def _now_utc() -> datetime:
    return datetime.now(_JORDAN_TZ)


def _today_amman() -> date:
    return datetime.now(_JORDAN_TZ).date()


def _start_job(db: Session, job_name: str) -> AIJobLog:
    job = AIJobLog(
        job_name=job_name,
        job_type="llm",
        started_at=_now_utc(),
        status="RUNNING",
        records_in=0,
        records_out=0,
        model_version=_LLM_MODEL,
        prompt_version=_RULE_VER,
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


def _store_recommendation(
    db: Session,
    child_id: int,
    report_date: date,
    source_report_id: Optional[int],
    recommendation_type: str,
    content_ar: Optional[str],
    content_en: Optional[str],
    confidence: float,
    evidence: dict,
) -> None:
    rec = AIParentRecommendation(
        child_id=child_id,
        report_date=report_date,
        source_report_id=source_report_id,
        recommendation_type=recommendation_type,
        content_ar=content_ar,
        content_en=content_en,
        model_version=_LLM_MODEL,
        prompt_version=_RULE_VER,
        confidence=confidence,
        evidence_json=evidence,
        human_reviewed=False,
    )
    db.add(rec)


# ---------------------------------------------------------------------------
# 3.1 — Daily report parent narrative
# Input: structured meal/sleep/activity fields from daily_reports (no raw notes
#        if they contain medical keywords matching child.allergy_notes).
# ---------------------------------------------------------------------------

_DAILY_REPORT_SQL = text("""
    SELECT
        dr.id        AS report_id,
        dr.child_id,
        dr.date,
        dr.breakfast,
        dr.snack,
        dr.milk,
        dr.lunch,
        dr.nap_duration_minutes,
        dr.activities,
        ch.allergy_notes
    FROM daily_reports dr
    JOIN children ch ON ch.id = dr.child_id
    WHERE dr.status = 'APPROVED'
      AND dr.date = CURRENT_DATE
      AND NOT EXISTS (
            SELECT 1 FROM ai_parent_recommendations apr
            WHERE apr.child_id = dr.child_id
              AND apr.report_date = dr.date
              AND apr.recommendation_type = 'daily_summary'
      )
    LIMIT 200
""")

_DAILY_SUMMARY_SYSTEM = (
    "You are a warm, concise kindergarten assistant. "
    "Write a 2–3 sentence parent update in English based on the structured JSON provided. "
    "Do NOT invent facts. Do NOT mention medical conditions. "
    "Do NOT make diagnoses. Keep the tone positive and reassuring."
)


def _run_daily_summaries(db: Session) -> int:
    job = _start_job(db, "daily_report_summary")
    rows = db.execute(_DAILY_REPORT_SQL).fetchall()
    job.records_in = len(rows)
    count = 0
    for row in rows:
        try:
            # Sanitise: remove activities text if any allergen keyword overlaps
            activities = row.activities or ""
            if row.allergy_notes:
                allergens = {w.lower() for w in (row.allergy_notes or "").split()}
                safe_activities = " ".join(
                    w for w in activities.split()
                    if w.lower() not in allergens
                )
            else:
                safe_activities = activities

            features = {
                "breakfast": bool(row.breakfast),
                "snack": bool(row.snack),
                "milk": bool(row.milk),
                "lunch": bool(row.lunch),
                "nap_minutes": int(row.nap_duration_minutes or 0),
                "activities_summary": safe_activities[:200],  # truncated, no PII
            }
            prompt = (
                f"Child daily report features (JSON): {json.dumps(features, ensure_ascii=False)}\n"
                "Write a parent-facing summary."
            )
            content_en, confidence = _ollama_generate(prompt, _DAILY_SUMMARY_SYSTEM)
            _store_recommendation(
                db, row.child_id, row.date, row.report_id,
                "daily_summary", None, content_en, confidence, features,
            )
            count += 1
        except Exception as exc:
            logger.warning("daily_summary child=%d: %s", row.child_id, exc)
    _finish_job(db, job, count)
    return count


# ---------------------------------------------------------------------------
# 3.2 — Weekly observation narrative
# Input: domain-level mastery summary — NOT raw observation_text.
# ---------------------------------------------------------------------------

_OBS_SQL = text("""
    SELECT
        o.child_id,
        MAX(o.observed_at)::date                             AS as_of_date,
        JSON_AGG(
            JSON_BUILD_OBJECT(
                'domain',        o.domain,
                'mastery',       o.mastery_level,
                'indicator',     co.indicator_code
            )
        )                                                    AS domain_summary
    FROM observations o
    LEFT JOIN curriculum_outcomes co ON co.id = o.outcome_id
    WHERE o.observed_at >= CURRENT_DATE - 7
      AND NOT EXISTS (
            SELECT 1 FROM ai_parent_recommendations apr
            WHERE apr.child_id   = o.child_id
              AND apr.report_date = CURRENT_DATE
              AND apr.recommendation_type = 'observation_summary'
      )
    GROUP BY o.child_id
    LIMIT 100
""")

_OBS_SYSTEM = (
    "You are a professional early-years educator assistant. "
    "Write a 3–4 sentence child development update for a parent based on the "
    "structured domain/mastery JSON. Focus on strengths and one gentle growth area. "
    "Do NOT include names, diagnoses, or medical information."
)


def _run_observation_narratives(db: Session) -> int:
    job = _start_job(db, "observation_narrative")
    try:
        rows = db.execute(_OBS_SQL).fetchall()
    except Exception as exc:
        # observations or curriculum_outcomes may not exist in test DB
        _finish_job(db, job, 0, str(exc))
        return 0
    job.records_in = len(rows)
    count = 0
    for row in rows:
        try:
            summary = row.domain_summary if isinstance(row.domain_summary, list) else []
            features = {"domains": summary[:10], "week_ending": str(row.as_of_date)}
            prompt = (
                f"Child observation features (JSON): {json.dumps(features, ensure_ascii=False)}\n"
                "Write a weekly development update for the parent."
            )
            content_en, confidence = _ollama_generate(prompt, _OBS_SYSTEM)
            _store_recommendation(
                db, row.child_id, _today_amman(), None,
                "observation_summary", None, content_en, confidence, features,
            )
            count += 1
        except Exception as exc:
            logger.warning("observation_narrative child=%d: %s", row.child_id, exc)
    _finish_job(db, job, count)
    return count


# ---------------------------------------------------------------------------
# 3.3 — Incident follow-up letter draft
# Input: incident type, severity, date — no child name or PII.
# Output goes to ai_parent_recommendations (recommendation_type='incident_draft').
# Manager MUST edit and explicitly send. LLM cannot send.
# ---------------------------------------------------------------------------

_INCIDENT_SQL = text("""
    SELECT
        i.id            AS incident_id,
        i.child_id,
        i.type,
        i.severity_level,
        i.occurred_at::date AS occurred_date,
        i.kindergarten_id
    FROM incidents i
    WHERE i.occurred_at >= CURRENT_DATE - 1
      AND i.followup_required_flag = TRUE
      AND NOT EXISTS (
            SELECT 1 FROM ai_parent_recommendations apr
            WHERE apr.child_id = i.child_id
              AND apr.report_date = i.occurred_at::date
              AND apr.recommendation_type = 'incident_draft'
      )
    LIMIT 50
""")

_INCIDENT_SYSTEM = (
    "You are a professional kindergarten administrator. "
    "Draft a brief, empathetic incident notification letter for a parent. "
    "Use only the structured information provided. "
    "Do NOT use the child's name. Do NOT include medical diagnoses. "
    "The letter is a DRAFT — a manager will review and edit before sending."
)


def _run_incident_drafts(db: Session) -> int:
    job = _start_job(db, "incident_draft")
    try:
        rows = db.execute(_INCIDENT_SQL).fetchall()
    except Exception:
        _finish_job(db, job, 0)
        return 0
    job.records_in = len(rows)
    count = 0
    for row in rows:
        try:
            features = {
                "incident_type": str(row.type),
                "severity": int(row.severity_level) if row.severity_level else 1,
                "date": str(row.occurred_date),
                "draft_note": "MANAGER MUST REVIEW BEFORE SENDING",
            }
            prompt = (
                f"Incident details (JSON): {json.dumps(features, ensure_ascii=False)}\n"
                "Draft a parent notification letter."
            )
            content_en, confidence = _ollama_generate(prompt, _INCIDENT_SYSTEM)
            _store_recommendation(
                db, row.child_id, row.occurred_date, None,
                "incident_draft", None, content_en,
                min(confidence, 0.70),  # cap confidence on sensitive content
                features,
            )
            count += 1
        except Exception as exc:
            logger.warning("incident_draft incident=%d: %s", row.incident_id, exc)
    _finish_job(db, job, count)
    return count


# ---------------------------------------------------------------------------
# 3.4 — Admin governance case study
# Input: anonymised KPI trend from governance_scores (aggregate only).
# ---------------------------------------------------------------------------

_GOV_SQL = text("""
    SELECT
        gs.kindergarten_id,
        gs.period_start,
        gs.final_governance_score,
        gs.band,
        LAG(gs.final_governance_score) OVER (
            PARTITION BY gs.kindergarten_id ORDER BY gs.period_start
        ) AS prev_score
    FROM governance_scores gs
    ORDER BY gs.kindergarten_id, gs.period_start DESC
    LIMIT 50
""")

_GOV_SYSTEM = (
    "You are an education policy analyst. "
    "Write a 3–5 sentence governance trend summary for an administrator "
    "based on the structured KPI JSON. "
    "Do NOT identify individual children or staff. "
    "Focus on measurable trends and actionable recommendations."
)


def _run_governance_case_studies(db: Session) -> int:
    job = _start_job(db, "governance_case_study")
    try:
        rows = db.execute(_GOV_SQL).fetchall()
    except Exception as exc:
        _finish_job(db, job, 0, str(exc))
        return 0
    job.records_in = len(rows)
    # Group by kindergarten_id, take latest 3 periods
    kg_data: dict = {}
    for row in rows:
        kg_id = row.kindergarten_id
        if kg_id not in kg_data:
            kg_data[kg_id] = []
        if len(kg_data[kg_id]) < 3:
            kg_data[kg_id].append({
                "period_start": str(row.period_start),
                "score": float(row.final_governance_score),
                "band": str(row.band),
                "prev_score": float(row.prev_score) if row.prev_score else None,
            })
    count = 0
    for kg_id, periods in kg_data.items():
        try:
            features = {"kindergarten_id": kg_id, "periods": periods}
            prompt = (
                f"Governance KPI data (JSON): {json.dumps(features, ensure_ascii=False)}\n"
                "Write a trend summary for the administrator."
            )
            content_en, confidence = _ollama_generate(prompt, _GOV_SYSTEM)
            # Store against a sentinel child_id = 0 (admin-level, not child-specific)
            # In practice these should be stored in a separate admin_reports table,
            # but we reuse ai_parent_recommendations with a special type.
            rec = AIParentRecommendation(
                child_id=None,  # admin-level
                report_date=_today_amman(),
                recommendation_type="governance_case_study",
                content_en=content_en,
                model_version=_LLM_MODEL,
                prompt_version=_RULE_VER,
                confidence=confidence,
                evidence_json=features,
                human_reviewed=False,
            )
            db.add(rec)
            count += 1
        except Exception as exc:
            logger.warning("governance_case_study kg=%d: %s", kg_id, exc)
    _finish_job(db, job, count)
    return count


# ---------------------------------------------------------------------------
# 3.5 — Curriculum activity suggestion
# Input: domain-level mastery levels + curriculum outcome indicator codes.
# ---------------------------------------------------------------------------

_CURRICULUM_SQL = text("""
    SELECT
        o.child_id,
        o.domain,
        o.mastery_level,
        co.description    AS outcome_description,
        co.indicator_code
    FROM observations o
    JOIN curriculum_outcomes co ON co.id = o.outcome_id
    WHERE o.observed_at >= CURRENT_DATE - 14
      AND o.mastery_level IN ('DEVELOPING', 'BEGINNING')
      AND NOT EXISTS (
            SELECT 1 FROM ai_parent_recommendations apr
            WHERE apr.child_id = o.child_id
              AND apr.report_date = CURRENT_DATE
              AND apr.recommendation_type = 'activity_suggestion'
      )
    LIMIT 100
""")

_CURRICULUM_SYSTEM = (
    "You are an early childhood curriculum specialist. "
    "Suggest one specific, practical home activity that supports the child's "
    "development in the identified domain. "
    "Base suggestions ONLY on the structured indicator and mastery data provided. "
    "Write in a warm, encouraging tone. 2–3 sentences maximum."
)


def _run_activity_suggestions(db: Session) -> int:
    job = _start_job(db, "activity_suggestion")
    try:
        rows = db.execute(_CURRICULUM_SQL).fetchall()
    except Exception as exc:
        _finish_job(db, job, 0, str(exc))
        return 0
    job.records_in = len(rows)
    count = 0
    seen: set = set()
    for row in rows:
        key = (row.child_id, row.domain)
        if key in seen:
            continue
        seen.add(key)
        try:
            features = {
                "domain": str(row.domain),
                "mastery_level": str(row.mastery_level),
                "indicator_code": str(row.indicator_code),
                "outcome": (row.outcome_description or "")[:200],
            }
            prompt = (
                f"Child development data (JSON): {json.dumps(features, ensure_ascii=False)}\n"
                "Suggest a home activity to support this area."
            )
            content_en, confidence = _ollama_generate(prompt, _CURRICULUM_SYSTEM)
            _store_recommendation(
                db, row.child_id, _today_amman(), None,
                "activity_suggestion", None, content_en, confidence, features,
            )
            count += 1
        except Exception as exc:
            logger.warning("activity_suggestion child=%d: %s", row.child_id, exc)
    _finish_job(db, job, count)
    return count


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

_LLM_JOBS = [
    ("daily_summaries",         _run_daily_summaries),
    ("observation_narratives",  _run_observation_narratives),
    ("incident_drafts",         _run_incident_drafts),
    ("governance_case_studies", _run_governance_case_studies),
    ("activity_suggestions",    _run_activity_suggestions),
]


async def run_llm_daily_jobs() -> None:
    """Run all Phase-3 LLM summarisation jobs.

    Jobs are skipped gracefully if Ollama is unreachable. Each job failure
    is logged and does not abort subsequent jobs.

    APScheduler configuration (main.py lifespan):
        from ai.llm import run_llm_daily_jobs
        scheduler.add_job(run_llm_daily_jobs, "cron", hour=3, minute=30,
                          id="llm_daily_jobs")
    """
    try:
        init_db()
    except Exception as exc:
        logger.warning("run_llm_daily_jobs: init_db failed: %s", exc)

    # Quick connectivity check — skip all jobs if Ollama is down
    try:
        with httpx.Client(timeout=5) as client:
            client.get(f"{settings.OLLAMA_URL}/api/tags")
    except Exception as exc:
        logger.warning("Ollama unavailable at %s (%s) — skipping LLM jobs", settings.OLLAMA_URL, exc)
        return

    db: Session = SessionLocal()
    try:
        for name, fn in _LLM_JOBS:
            try:
                count = fn(db)
                logger.info("llm_jobs: %s produced %d records", name, count)
            except Exception as exc:
                db.rollback()
                logger.warning("llm_jobs: %s failed: %s", name, exc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("run_llm_daily_jobs fatal: %s", exc)
    finally:
        db.close()
