"""routers/ai.py — narrowly-scoped AI endpoints.

This module intentionally keeps the legacy, general-purpose AI endpoints out of the
application mount surface. The only route set mounted by the app is the
Supervisor Daily Report draft/confirm workflow, which is the approved,
feature-flagged exception to the otherwise read-only default.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from api.daily_reports_routes import DailyReportCreateRequest, _authorize_report_for_child
from config import settings
from database import get_db
from dependencies import get_current_user
import models

router = APIRouter(prefix="/ai/supervisor", tags=["AI Supervisor"])
legacy_router = APIRouter(prefix="/ai", tags=["AI Legacy"])


def _require_ai_enabled(current_user: models.User, *, supervisor_only: bool = False) -> None:
    """Fail closed unless AI-capable features are explicitly enabled."""
    if not settings.AI_ASSISTANT_ENABLED:
        raise HTTPException(status_code=403, detail="AI assistant is disabled")
    if supervisor_only and current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Supervisor access required")


def _require_ai_supervisor_daily_report_enabled(current_user: models.User) -> None:
    """Fail closed unless the AI supervisor daily-report workflow is explicitly enabled."""
    _require_ai_enabled(current_user, supervisor_only=True)
    if not settings.AI_ASSISTANT_SUPERVISOR_ENABLED:
        raise HTTPException(status_code=403, detail="AI supervisor workflow is disabled")
    if not settings.AI_ASSISTANT_SUPERVISOR_DAILY_REPORT_ENABLED:
        raise HTTPException(status_code=403, detail="AI supervisor daily report workflow is disabled")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    approved: bool
    review_note: Optional[str] = None


class FeedbackRequest(BaseModel):
    source_table: str
    source_id: int
    feedback_type: str
    feedback_note: Optional[str] = None


class ConfirmSupervisorDailyReportDraftRequest(BaseModel):
    confirmed: bool

    model_config = ConfigDict(extra="forbid")


class SimilarResult(BaseModel):
    source_table: str
    source_id: int
    chunk_index: int
    score: float


class ActivityRecommendation(BaseModel):
    indicator_code: str
    description: str
    score: float


class IncidentSearchResult(BaseModel):
    incident_id: int
    score: float


class SupervisorDailyReportDraftRequest(DailyReportCreateRequest):
    """AI-generated supervisor draft. The final persisted record remains the regular DailyReport model."""


@router.post("/daily-reports/draft", status_code=status.HTTP_201_CREATED)
def create_supervisor_daily_report_draft(
    payload: SupervisorDailyReportDraftRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an AI-assisted daily-report draft for an assigned child.

    This is intentionally a draft-only path: the supervisor must review and
    confirm the generated content before any final save is accepted. The final
    persisted object still uses the normal DailyReport model and the canonical
    authorization checks from api.daily_reports_routes._authorize_report_for_child.
    """
    _require_ai_supervisor_daily_report_enabled(current_user)

    report_date = date.fromisoformat(payload.date)
    active_enrollment = _authorize_report_for_child(db, current_user, payload.child_id, report_date)

    # Keep the final write path canonical: the generated data is stored as a
    # regular daily report draft, subject to the same uniqueness and scope checks
    # as any manual supervisor entry.
    report = models.DailyReport(
        child_id=payload.child_id,
        kindergarten_id=active_enrollment.kindergarten_id,
        class_id=active_enrollment.class_id,
        date=report_date,
        status=models.DailyReportStatus.DRAFT,
        submitted_by=current_user.id,
        arrival_time=payload.arrival_time,
        leave_time=payload.leave_time,
        mood=payload.mood,
        health_notes=payload.health_notes,
        breakfast=payload.breakfast,
        snack=payload.snack,
        milk=payload.milk,
        lunch=payload.lunch,
        breakfast_time=payload.breakfast_time,
        snack_time=payload.snack_time,
        milk_time=payload.milk_time,
        lunch_time=payload.lunch_time,
        nap_start=payload.nap_start,
        nap_end=payload.nap_end,
        nap_duration_minutes=payload.nap_duration_minutes,
        bathroom_count=payload.bathroom_count,
        diaper_wet=payload.diaper_wet,
        diaper_soiled=payload.diaper_soiled,
        activities=payload.activities,
        notes=payload.notes,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "draft_id": report.id,
        "child_id": report.child_id,
        "date": report.date.isoformat(),
        "status": report.status.value.lower(),
        "requires_confirmation": True,
    }


@router.post("/daily-reports/{draft_id}/confirm", status_code=status.HTTP_200_OK)
def confirm_supervisor_daily_report_draft(
    draft_id: int,
    body: ConfirmSupervisorDailyReportDraftRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm an AI-generated daily report draft after human review.

    Confirmation is intentionally explicit and server-side reauthorized; there is
    no silent auto-save or permission grant without the typed confirmation.

    This is intentionally performed inside a single transaction and row lock so a
    draft cannot be confirmed twice by concurrent requests.
    """
    _require_ai_supervisor_daily_report_enabled(current_user)
    if body.confirmed is not True:
        raise HTTPException(status_code=400, detail="Supervisor confirmation required")

    report = (
        db.query(models.DailyReport)
        .filter(models.DailyReport.id == draft_id)
        .with_for_update()
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Draft not found")
    if report.submitted_by != current_user.id:
        raise HTTPException(status_code=403, detail="Draft belongs to another supervisor")
    if report.status != models.DailyReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Draft has already been finalized")

    ttl_minutes = getattr(settings, "AI_SUPERVISOR_REPORT_DRAFT_TTL_MINUTES", 30)
    if ttl_minutes is not None and ttl_minutes >= 0:
        created_at = report.created_at or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=ttl_minutes):
            raise HTTPException(status_code=410, detail="Draft expired")

    _authorize_report_for_child(db, current_user, report.child_id, report.date, require_no_existing_report=False)

    updated = (
        db.query(models.DailyReport)
        .filter(
            models.DailyReport.id == draft_id,
            models.DailyReport.submitted_by == current_user.id,
            models.DailyReport.status == models.DailyReportStatus.DRAFT,
        )
        .update(
            {
                models.DailyReport.status: models.DailyReportStatus.SUBMITTED,
                models.DailyReport.submitted_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        raise HTTPException(status_code=409, detail="Draft has already been finalized")

    db.commit()
    report = db.query(models.DailyReport).filter(models.DailyReport.id == draft_id).one()

    return {
        "draft_id": report.id,
        "child_id": report.child_id,
        "date": report.date.isoformat(),
        "status": report.status.value.lower(),
        "confirmed": True,
    }


# ---------------------------------------------------------------------------
# PUT /api/ai/recommendations/{id}/review
# ---------------------------------------------------------------------------

@legacy_router.put("/recommendations/{rec_id}/review", status_code=status.HTTP_200_OK)
def review_recommendation(
    rec_id: int,
    body: ReviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supervisor approves or rejects an AI-generated recommendation.

    Sets human_reviewed=True and stores reviewer identity and optional note.
    Requires SUPERVISOR or MANAGER role.
    """
    _require_ai_enabled(current_user)
    if current_user.role not in (
        models.UserRole.SUPERVISOR,
        models.UserRole.MANAGER,
        models.UserRole.ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Supervisor role required")

    rec = db.query(models.AIParentRecommendation).filter(
        models.AIParentRecommendation.id == rec_id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.human_reviewed = body.approved
    rec.reviewed_by = current_user.id
    rec.review_note = body.review_note
    db.commit()
    return {"id": rec_id, "human_reviewed": rec.human_reviewed}


# ---------------------------------------------------------------------------
# POST /api/ai/feedback
# ---------------------------------------------------------------------------

@legacy_router.post("/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store user feedback on any AI-generated content row."""
    _require_ai_enabled(current_user)
    allowed = {"correct", "incorrect", "helpful", "harmful"}
    if body.feedback_type not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"feedback_type must be one of {allowed}",
        )

    fb = models.AIFeedback(
        source_table=body.source_table,
        source_id=body.source_id,
        user_id=current_user.id,
        user_role=current_user.role.value,
        feedback_type=body.feedback_type,
        feedback_note=body.feedback_note,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"id": fb.id, "feedback_type": fb.feedback_type}


# ---------------------------------------------------------------------------
# GET /api/ai/search/similar
# ---------------------------------------------------------------------------

@legacy_router.get("/search/similar", response_model=List[SimilarResult])
def search_similar(
    q: str = Query(..., min_length=3, description="Query text"),
    source_table: str = Query("observations"),
    top_k: int = Query(10, ge=1, le=50),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Semantic similarity search over embedded content.

    PostgreSQL + pgvector only; returns empty list on SQLite.
    """
    _require_ai_enabled(current_user)
    if current_user.role not in (
        models.UserRole.SUPERVISOR,
        models.UserRole.MANAGER,
        models.UserRole.ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Supervisor role required")

    from ai.embeddings import find_similar
    results = find_similar(db, q, source_table=source_table, top_k=top_k)
    return [
        SimilarResult(source_table=r[0], source_id=r[1], chunk_index=r[2], score=r[3])
        for r in results
    ]


# ---------------------------------------------------------------------------
# GET /api/ai/recommendations/activities/{child_id}  (Phase 5.6)
# ---------------------------------------------------------------------------

@legacy_router.get(
    "/recommendations/activities/{child_id}",
    response_model=List[ActivityRecommendation],
)
def recommend_activities(
    child_id: int,
    limit: int = Query(5, ge=1, le=20),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return activity recommendations for a child based on similar past EXCEEDS-mastery activities.

    PostgreSQL + pgvector only; returns empty list on SQLite or when Ollama is unreachable.
    """
    _require_ai_enabled(current_user)
    if current_user.role not in (
        models.UserRole.SUPERVISOR,
        models.UserRole.MANAGER,
        models.UserRole.ADMIN,
        models.UserRole.TEACHER,
    ):
        raise HTTPException(status_code=403, detail="Staff role required")

    from ai.embeddings import recommend_activities as _recommend
    return _recommend(db, child_id, limit=limit)


# ---------------------------------------------------------------------------
# GET /api/ai/incidents/search  (Phase 5.7)
# ---------------------------------------------------------------------------

@legacy_router.get("/incidents/search", response_model=List[IncidentSearchResult])
def search_incidents(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Semantic incident description search. Requires SUPERVISOR or above."""
    _require_ai_enabled(current_user)
    if current_user.role not in (
        models.UserRole.SUPERVISOR,
        models.UserRole.MANAGER,
        models.UserRole.ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Supervisor role required")

    from ai.embeddings import search_incidents as _search
    return _search(db, q, limit=limit)
