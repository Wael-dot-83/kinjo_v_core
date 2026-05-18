"""routers/ai.py — AI feature API endpoints.

Exposes:
  PUT  /api/ai/recommendations/{id}/review  — supervisor approves LLM output
  POST /api/ai/feedback                     — user feedback on AI content
  GET  /api/ai/search/similar               — semantic similarity search
  GET  /api/ai/recommendations/activities/{child_id} — activity recommendations
  GET  /api/ai/incidents/search             — semantic incident search
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
import models

router = APIRouter(tags=["AI"])


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


# ---------------------------------------------------------------------------
# PUT /api/ai/recommendations/{id}/review
# ---------------------------------------------------------------------------

@router.put("/ai/recommendations/{rec_id}/review", status_code=status.HTTP_200_OK)
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

@router.post("/ai/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store user feedback on any AI-generated content row."""
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

@router.get("/ai/search/similar", response_model=List[SimilarResult])
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

@router.get(
    "/ai/recommendations/activities/{child_id}",
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

@router.get("/ai/incidents/search", response_model=List[IncidentSearchResult])
def search_incidents(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Semantic incident description search. Requires SUPERVISOR or above."""
    if current_user.role not in (
        models.UserRole.SUPERVISOR,
        models.UserRole.MANAGER,
        models.UserRole.ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Supervisor role required")

    from ai.embeddings import search_incidents as _search
    return _search(db, q, limit=limit)
