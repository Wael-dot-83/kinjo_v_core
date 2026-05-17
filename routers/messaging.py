"""
Role-safe messaging endpoints.

GET  /api/messages/recipients          — list allowed recipients for the current user
POST /api/messages                     — send a message (role-safe, with auto-resolve)
GET  /api/messages                     — inbox + sent (consolidated)
POST /api/messages/{id}/read           — mark message as read (updates MessageRecipient)
GET  /api/messages/recipients/search   — manager: search recipients by name
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import (
    Child,
    EnrollmentApplication,
    EnrollmentStatus,
    Kindergarten,
    Message,
    MessageQueueStatus,
    MessageRecipient,
    MessageThreadType,
    ParentProfile,
    SupervisorAssignment,
    User,
    UserRole,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MessageSendRequest(BaseModel):
    subject: Optional[str] = None
    message_body: str
    # For roles where recipient is auto-resolved, omit recipient_id.
    # Manager/Admin must supply it (or use thread_type=BROADCAST).
    recipient_id: Optional[int] = None
    thread_type: str = "DIRECT"
    scheduled_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Recipient resolution helpers
# ---------------------------------------------------------------------------

def _resolve_manager_for_supervisor(supervisor_id: int, db: Session) -> Optional[User]:
    """Return the manager of the kindergarten the supervisor belongs to."""
    supervisor = db.query(User).filter(User.id == supervisor_id).first()
    if not supervisor or not supervisor.kindergarten_id:
        return None
    return (
        db.query(User)
        .filter(
            User.role == UserRole.MANAGER,
            User.kindergarten_id == supervisor.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .first()
    )


def _resolve_manager_for_parent(parent_user_id: int, db: Session) -> Optional[User]:
    """Return the manager of the kindergarten where the parent's child is enrolled."""
    profile = db.query(ParentProfile).filter(ParentProfile.user_id == parent_user_id).first()
    if not profile:
        return None
    enrollment = (
        db.query(EnrollmentApplication)
        .join(Child, Child.id == EnrollmentApplication.child_id)
        .filter(
            Child.parent_id == profile.id,
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .first()
    )
    if not enrollment or not enrollment.kindergarten_id:
        return None
    return (
        db.query(User)
        .filter(
            User.role == UserRole.MANAGER,
            User.kindergarten_id == enrollment.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .first()
    )


def _allowed_recipient_ids_for_manager(manager: User, db: Session) -> List[int]:
    """Return IDs the manager can message: supervisors + parents in their KG only."""
    if not manager.kindergarten_id:
        return []
    # Supervisors in same KG
    supervisors = (
        db.query(User.id)
        .filter(
            User.role == UserRole.SUPERVISOR,
            User.kindergarten_id == manager.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .all()
    )
    # Parents of enrolled children in this KG
    parent_ids = (
        db.query(ParentProfile.user_id)
        .join(Child, Child.parent_id == ParentProfile.id)
        .join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id)
        .filter(
            EnrollmentApplication.kindergarten_id == manager.kindergarten_id,
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .distinct()
        .all()
    )
    return [r.id for r in supervisors] + [r.user_id for r in parent_ids]


# ---------------------------------------------------------------------------
# GET /api/messages/recipients
# ---------------------------------------------------------------------------

@router.get("/messages/recipients")
def get_allowed_recipients(
    q: Optional[str] = Query(default=None, description="Search query (name/username)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the recipients the current user is allowed to message.
    - SUPERVISOR: returns single auto-resolved manager (no choice)
    - PARENT:     returns single auto-resolved manager (no choice)
    - MANAGER:    returns all supervisors + parents in their KG
    - ADMIN:      returns all users
    """
    if current_user.role == UserRole.SUPERVISOR:
        mgr = _resolve_manager_for_supervisor(current_user.id, db)
        if not mgr:
            return {"recipients": [], "auto_resolved": True}
        return {
            "recipients": [_user_brief(mgr)],
            "auto_resolved": True,
        }

    if current_user.role == UserRole.PARENT:
        mgr = _resolve_manager_for_parent(current_user.id, db)
        if not mgr:
            return {"recipients": [], "auto_resolved": True}
        return {
            "recipients": [_user_brief(mgr)],
            "auto_resolved": True,
        }

    if current_user.role == UserRole.MANAGER:
        allowed_ids = _allowed_recipient_ids_for_manager(current_user, db)
        users = db.query(User).filter(User.id.in_(allowed_ids), User.deleted_at.is_(None)).all()
        if q:
            q_lower = q.lower()
            users = [u for u in users if q_lower in (u.full_name or "").lower() or q_lower in u.username.lower()]
        return {"recipients": [_user_brief(u) for u in users], "auto_resolved": False}

    # ADMIN — can message anyone
    query = db.query(User).filter(User.id != current_user.id, User.deleted_at.is_(None))
    if q:
        q_like = f"%{q}%"
        query = query.filter(
            (User.full_name.ilike(q_like)) | (User.username.ilike(q_like))
        )
    users = query.limit(50).all()
    return {"recipients": [_user_brief(u) for u in users], "auto_resolved": False}


# ---------------------------------------------------------------------------
# POST /api/messages  — send with role-safe resolution
# ---------------------------------------------------------------------------

@router.post("/messages", status_code=status.HTTP_201_CREATED)
def send_message_safe(
    body: MessageSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread_type = MessageThreadType(body.thread_type.upper())

    # ── Auto-resolve recipient for SUPERVISOR ──────────────────────────────
    recipient_id = body.recipient_id
    if current_user.role == UserRole.SUPERVISOR:
        mgr = _resolve_manager_for_supervisor(current_user.id, db)
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No manager found for your kindergarten.",
            )
        recipient_id = mgr.id
        thread_type = MessageThreadType.DIRECT

    # ── Auto-resolve recipient for PARENT ─────────────────────────────────
    elif current_user.role == UserRole.PARENT:
        mgr = _resolve_manager_for_parent(current_user.id, db)
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No manager found for your child's kindergarten.",
            )
        recipient_id = mgr.id
        thread_type = MessageThreadType.DIRECT

    # ── Manager / Admin: validate supplied recipient ───────────────────────
    elif current_user.role == UserRole.MANAGER:
        if thread_type == MessageThreadType.DIRECT:
            if not recipient_id:
                raise HTTPException(status_code=400, detail="recipient_id is required for direct messages.")
            allowed_ids = _allowed_recipient_ids_for_manager(current_user, db)
            if recipient_id not in allowed_ids:
                raise HTTPException(status_code=403, detail="Recipient is outside your allowed contact list.")
        # BROADCAST is allowed for managers (to all KG parents)
        elif thread_type == MessageThreadType.BROADCAST:
            recipient_id = None

    elif current_user.role == UserRole.ADMIN:
        if thread_type == MessageThreadType.DIRECT and not recipient_id:
            raise HTTPException(status_code=400, detail="recipient_id is required for direct messages.")

    # ── Persist ────────────────────────────────────────────────────────────
    queue_status = MessageQueueStatus.SENT
    if body.scheduled_at and body.scheduled_at > datetime.now(timezone.utc):
        queue_status = MessageQueueStatus.SCHEDULED

    msg = Message(
        thread_type=thread_type,
        sender_id=current_user.id,
        recipient_id=recipient_id,
        kindergarten_id=current_user.kindergarten_id,
        subject=body.subject,
        message_body=body.message_body,
        scheduled_at=body.scheduled_at,
        queue_status=queue_status,
    )
    db.add(msg)
    db.flush()  # get msg.id before creating recipients

    # Create MessageRecipient record for tracking
    if recipient_id:
        db.add(MessageRecipient(message_id=msg.id, recipient_user_id=recipient_id))
    elif thread_type == MessageThreadType.BROADCAST and current_user.kindergarten_id:
        # Fan out to all active parents in the KG
        parent_ids = (
            db.query(ParentProfile.user_id)
            .join(Child, Child.parent_id == ParentProfile.id)
            .join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id)
            .filter(
                EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
            )
            .distinct()
            .all()
        )
        for (pid,) in parent_ids:
            db.add(MessageRecipient(message_id=msg.id, recipient_user_id=pid))

    db.commit()
    db.refresh(msg)

    return {
        "id": msg.id,
        "thread_type": msg.thread_type.value,
        "recipient_id": msg.recipient_id,
        "subject": msg.subject,
        "queue_status": msg.queue_status.value if msg.queue_status else None,
        "scheduled_at": msg.scheduled_at.isoformat() if msg.scheduled_at else None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/messages — inbox + sent
# ---------------------------------------------------------------------------

@router.get("/messages")
def list_messages(
    folder: str = Query(default="inbox", pattern="^(inbox|sent|all)$"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_

    base = db.query(Message).filter(Message.kindergarten_id == current_user.kindergarten_id)

    if folder == "inbox":
        # Direct messages to me OR I'm in message_recipients
        recipient_msg_ids = (
            db.query(MessageRecipient.message_id)
            .filter(MessageRecipient.recipient_user_id == current_user.id)
            .subquery()
        )
        base = base.filter(
            or_(
                Message.recipient_id == current_user.id,
                Message.id.in_(recipient_msg_ids),
                Message.thread_type == MessageThreadType.BROADCAST,
            )
        ).filter(Message.sender_id != current_user.id)
    elif folder == "sent":
        base = base.filter(Message.sender_id == current_user.id)
    else:
        recipient_msg_ids = (
            db.query(MessageRecipient.message_id)
            .filter(MessageRecipient.recipient_user_id == current_user.id)
            .subquery()
        )
        base = base.filter(
            or_(
                Message.sender_id == current_user.id,
                Message.recipient_id == current_user.id,
                Message.id.in_(recipient_msg_ids),
                Message.thread_type == MessageThreadType.BROADCAST,
            )
        )

    total = base.count()
    messages = base.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()

    sender_ids = {m.sender_id for m in messages}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(sender_ids)).all()} if sender_ids else {}

    return {
        "total": total,
        "messages": [_message_brief(m, users) for m in messages],
    }


# ---------------------------------------------------------------------------
# POST /api/messages/{id}/read — mark as read
# ---------------------------------------------------------------------------

@router.post("/messages/{message_id}/read", status_code=status.HTTP_200_OK)
def mark_message_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recipient_row = (
        db.query(MessageRecipient)
        .filter(
            MessageRecipient.message_id == message_id,
            MessageRecipient.recipient_user_id == current_user.id,
        )
        .first()
    )
    if recipient_row:
        if not recipient_row.read_at:
            recipient_row.read_at = datetime.now(timezone.utc)
            if not recipient_row.delivered_at:
                recipient_row.delivered_at = recipient_row.read_at
            db.commit()
        return {"read_at": recipient_row.read_at.isoformat()}

    # Direct message with no recipient row — create one on first read
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.recipient_id == current_user.id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404)

    now = datetime.now(timezone.utc)
    row = MessageRecipient(message_id=msg.id, recipient_user_id=current_user.id, delivered_at=now, read_at=now)
    db.add(row)
    db.commit()
    return {"read_at": now.isoformat()}


# ---------------------------------------------------------------------------
# POST /api/messages/broadcast — manager multi-recipient send
# ---------------------------------------------------------------------------


class BroadcastRecipient(BaseModel):
    role: str  # "supervisor" | "parents_class" | "all_parents" | "all_supervisors"
    id: Optional[int] = None        # for role=supervisor
    class_id: Optional[int] = None  # for role=parents_class


class BroadcastRequest(BaseModel):
    subject: Optional[str] = None
    body: str
    recipients: List[BroadcastRecipient]
    scheduled_at: Optional[datetime] = None


@router.post("/messages/broadcast", status_code=status.HTTP_201_CREATED)
def broadcast_message(
    payload: BroadcastRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Role-safe broadcast: manager sends to one or more validated recipient groups."""
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only managers and admins can broadcast.")

    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty.")

    allowed_ids = _allowed_recipient_ids_for_manager(current_user, db) if current_user.role == UserRole.MANAGER else None

    queue_status = MessageQueueStatus.SENT
    if payload.scheduled_at and payload.scheduled_at > datetime.now(timezone.utc):
        queue_status = MessageQueueStatus.SCHEDULED

    created_ids = []
    for rec in payload.recipients:
        recipient_ids_to_send: List[int] = []

        if rec.role == "supervisor":
            if not rec.id:
                continue
            # Validate
            if allowed_ids is not None and rec.id not in allowed_ids:
                raise HTTPException(status_code=403, detail=f"Recipient {rec.id} is outside your allowed contact list.")
            recipient_ids_to_send = [rec.id]

        elif rec.role == "all_supervisors":
            sups = (
                db.query(User.id)
                .filter(
                    User.role == UserRole.SUPERVISOR,
                    User.kindergarten_id == current_user.kindergarten_id,
                    User.deleted_at.is_(None),
                )
                .all()
            )
            recipient_ids_to_send = [r.id for r in sups]

        elif rec.role == "parents_class":
            if not rec.class_id:
                continue
            from models import Class as ClassModel
            cls = db.query(ClassModel).filter(
                ClassModel.id == rec.class_id,
                ClassModel.kindergarten_id == current_user.kindergarten_id,
                ClassModel.deleted_at.is_(None),
            ).first()
            if not cls:
                raise HTTPException(status_code=403, detail="Class not in your kindergarten.")
            parent_ids = (
                db.query(ParentProfile.user_id)
                .join(Child, Child.parent_id == ParentProfile.id)
                .join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id)
                .filter(
                    EnrollmentApplication.class_id == rec.class_id,
                    EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
                )
                .distinct()
                .all()
            )
            recipient_ids_to_send = [r.user_id for r in parent_ids]

        elif rec.role == "all_parents":
            parent_ids = (
                db.query(ParentProfile.user_id)
                .join(Child, Child.parent_id == ParentProfile.id)
                .join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id)
                .filter(
                    EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                    EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
                )
                .distinct()
                .all()
            )
            recipient_ids_to_send = [r.user_id for r in parent_ids]

        for rid in recipient_ids_to_send:
            msg = Message(
                thread_type=MessageThreadType.DIRECT,
                sender_id=current_user.id,
                recipient_id=rid,
                kindergarten_id=current_user.kindergarten_id,
                subject=payload.subject,
                message_body=payload.body,
                scheduled_at=payload.scheduled_at,
                queue_status=queue_status,
            )
            db.add(msg)
            db.flush()
            db.add(MessageRecipient(message_id=msg.id, recipient_user_id=rid))
            created_ids.append(msg.id)

    db.commit()
    return {"created": len(created_ids), "message_ids": created_ids}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _user_brief(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.full_name or u.username,
        "role": u.role.value,
        "kindergarten_id": u.kindergarten_id,
    }


def _message_brief(m: Message, users: dict) -> dict:
    sender = users.get(m.sender_id)
    return {
        "id": m.id,
        "thread_type": m.thread_type.value,
        "sender_id": m.sender_id,
        "sender_name": (sender.full_name or sender.username) if sender else "",
        "recipient_id": m.recipient_id,
        "subject": m.subject,
        "message_body": m.message_body,
        "queue_status": m.queue_status.value if m.queue_status else None,
        "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
