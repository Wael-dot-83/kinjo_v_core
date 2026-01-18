from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel

import models
import validators
from database import get_db
from dependencies import get_current_user

router = APIRouter()

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class MessageCreate(BaseModel):
    recipient_id: Optional[int] = None # If direct
    subject: Optional[str] = None
    message_body: str
    thread_type: str = "direct" # direct, class, broadcast

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: str = "meeting"
    start_at: datetime
    end_at: datetime
    requires_consent_flag: bool = False

# -----------------------------------------------------------------------------
# Messages
# -----------------------------------------------------------------------------

@router.post("/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    msg_data: MessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message (Direct, Class Broadcast, or Kindergarten Broadcast)"""
    
    # Validation logic based on thread type
    thread_type_str = msg_data.thread_type.upper()
    
    if thread_type_str == "DIRECT":
        if not msg_data.recipient_id:
             raise HTTPException(status_code=400, detail="Recipient required for direct messages")
        # Validate recipient exists
        recipient = db.query(models.User).filter(models.User.id == msg_data.recipient_id).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient not found")
            
    elif thread_type_str == "BROADCAST":
        # Only Admin/Manager can broadcast
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Only managers can send broadcasts")

    msg = models.Message(
        thread_type=models.MessageThreadType(thread_type_str),
        sender_id=current_user.id,
        kindergarten_id=current_user.kindergarten_id, # Scoped to current KG
        subject=msg_data.subject,
        message_body=msg_data.message_body,
        recipient_id=msg_data.recipient_id if thread_type_str == "DIRECT" else None
    )
    
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

@router.get("/messages")
def list_my_messages(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List messages relevant to the current user"""
    # Simply return messages sent by user for now (Inbox logic requires recipient mapping table which might be missing in simple design)
    # Looking at Model: Message has sender_id but no explicit recipient_id column!
    # It seems the model implies a broadcast or is incomplete for Direct messaging without a join table or array.
    # For now, we list messages sent by the user or broadcasts to their kindergarten.
    
    query = db.query(models.Message).filter(
        models.Message.kindergarten_id == current_user.kindergarten_id,
        or_(
            models.Message.sender_id == current_user.id,
            models.Message.recipient_id == current_user.id,
            models.Message.thread_type == models.MessageThreadType.BROADCAST
        )
    )
    
    return query.all()

# -----------------------------------------------------------------------------
# Events
# -----------------------------------------------------------------------------

@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    event_data: EventCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a calendar event"""
    validators.validate_manager_role(current_user)
    
    event = models.Event(
        kindergarten_id=current_user.kindergarten_id,
        title=event_data.title,
        description=event_data.description,
        type=models.EventType(event_data.type),
        start_at=event_data.start_at,
        end_at=event_data.end_at,
        requires_consent_flag=event_data.requires_consent_flag
    )
    
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

@router.get("/events")
def list_events(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.Event).filter(models.Event.kindergarten_id == current_user.kindergarten_id)
    
    if start_date:
        query = query.filter(models.Event.start_at >= start_date)
    if end_date:
        query = query.filter(models.Event.end_at <= end_date)
        
    return query.all()

# -----------------------------------------------------------------------------
# Surveys
# -----------------------------------------------------------------------------

class SurveyCreate(BaseModel):
    title: str
    description: Optional[str] = None
    nps_question_enabled: bool = True
    start_date: date
    end_date: date

@router.post("/surveys", status_code=status.HTTP_201_CREATED)
def create_survey(
    survey_data: SurveyCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a satisfaction survey"""
    validators.validate_manager_role(current_user)
    
    survey = models.Survey(
        kindergarten_id=current_user.kindergarten_id,
        title=survey_data.title,
        description=survey_data.description,
        nps_question_enabled=survey_data.nps_question_enabled,
        start_date=survey_data.start_date,
        end_date=survey_data.end_date
    )
    
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return survey

@router.get("/surveys")
def list_surveys(
    active_only: bool = True,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.Survey).filter(models.Survey.kindergarten_id == current_user.kindergarten_id)
    
    if active_only:
        today = date.today()
        query = query.filter(models.Survey.start_date <= today, models.Survey.end_date >= today)
        
    return query.all()


class SurveyResponseCreate(BaseModel):
    nps_score: Optional[int] = None
    feedback_text: Optional[str] = None

@router.post("/surveys/{survey_id}/submit", status_code=status.HTTP_201_CREATED)
def submit_survey_response(
    survey_id: int,
    response_data: SurveyResponseCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit a response to a survey"""
    survey = db.query(models.Survey).filter(models.Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
        
    # Check if already responded
    existing = db.query(models.SurveyResponse).filter(
        models.SurveyResponse.survey_id == survey_id,
        models.SurveyResponse.parent_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already responded to this survey")
        
    resp = models.SurveyResponse(
        survey_id=survey_id,
        parent_id=current_user.id,
        nps_score=response_data.nps_score,
        feedback_text=response_data.feedback_text
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp

