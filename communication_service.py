import logging
import enum
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, aliased
from sqlalchemy import or_, and_, desc, func, select, exists
from typing import List, Optional, Dict, Literal, Union, Any
from datetime import datetime, date, timezone, timedelta
from utils.time_utils import today_amman as _today
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, model_validator

import models
import validators
from admin_security import forbidden_error, not_found_error, validation_error, log_audit_event, model_to_dict
from config import settings
from database import get_db, SessionLocal
from dependencies import get_current_user
from notification_service import create_message_notifications
from rate_limiter import limiter
from storage_service import save_attachment, resolve_attachment_path
from cache_service import cache_service
from messaging_permissions import (
    normalize_message_type,
    normalize_roles,
    resolve_announcement_scope,
    validate_announcement_permissions,
    build_audience_recipients,
    resolve_direct_recipient,
    resolve_direct_kindergarten_id,
    validate_direct_permissions,
    resolve_recipients,
    ACTIVE_ENROLLMENT_STATUSES,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class FilterOperator(str, enum.Enum):
    EQ = "EQ"
    IN = "IN"
    NEQ = "NEQ"
    NOT_IN = "NOT_IN"
    LIKE = "LIKE"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"


class FilterClause(BaseModel):
    field: str
    op: FilterOperator
    value: Union[str, int, float, List[Union[str, int, float]], None] = None

    model_config = ConfigDict(extra="ignore")


class AudienceScope(str, enum.Enum):
    GLOBAL = "GLOBAL"
    GOVERNORATE = "GOVERNORATE"
    KINDERGARTEN = "KINDERGARTEN"
    CLASS = "CLASS"
    CUSTOM = "CUSTOM"


class AudienceDefinition(BaseModel):
    include_roles: Optional[List[str]] = None
    exclude_roles: Optional[List[str]] = None
    scope: AudienceScope = AudienceScope.GLOBAL
    filters: List[FilterClause] = []
    include_user_ids: Optional[List[int]] = None
    exclude_user_ids: Optional[List[int]] = None
    # Legacy compatibility fields
    roles: Optional[List[str]] = None
    users: Optional[List[int]] = None
    kindergarten_ids: Optional[List[int]] = None
    governorate_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data):
        if not isinstance(data, dict):
            return data
        scope = data.get("scope")
        if isinstance(scope, str) and scope:
            data["scope"] = scope.strip().upper()
        if not data.get("include_roles") and data.get("roles"):
            data["include_roles"] = data.get("roles")
        if not data.get("include_user_ids") and data.get("users"):
            data["include_user_ids"] = data.get("users")
        if not data.get("scope"):
            if data.get("kindergarten_ids"):
                data["scope"] = "KINDERGARTEN"
            elif data.get("governorate_id"):
                data["scope"] = "GOVERNORATE"
        return data

    model_config = ConfigDict(extra="ignore")


class AudienceSpec(BaseModel):  # Legacy compatibility
    roles: List[str] = []
    users: List[int] = []
    kindergarten_ids: Optional[List[int]] = None
    class_ids: Optional[List[int]] = None
    scope: Optional[str] = None  # "global", "governorate", "kindergarten"
    governorate_id: Optional[int] = None  # For governorate-scoped messages

    model_config = ConfigDict(extra="ignore")


class MessageCreate(BaseModel):
    mode: str = "direct"  # "direct" or "audience"
    message_type: Optional[str] = None  # legacy direct/announcement/broadcast
    recipient_id: Optional[int] = None  # For direct messages only
    audience: Optional[AudienceDefinition] = None  # For audience messages
    subject: Optional[str] = None
    message_body: str
    allow_replies: bool = True
    kindergarten_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def validate_mode(cls, data):
        if isinstance(data, dict):
            mode = data.get("mode")
            message_type = data.get("message_type")
            if message_type:
                normalized = (str(message_type).strip().lower() or "")
                if normalized == "broadcast":
                    normalized = "announcement"
                if normalized not in {"announcement", "direct"}:
                    raise ValueError("message_type must be direct or announcement")
                derived_mode = "audience" if normalized == "announcement" else "direct"
                if mode and mode != derived_mode:
                    raise ValueError("mode does not match message_type")
                mode = derived_mode
                data["mode"] = mode
            if not mode:
                mode = "direct"
                data["mode"] = mode
            if mode == "direct":
                if data.get("audience"):
                    raise ValueError("audience should not be provided for direct messages")
            elif mode == "audience":
                if data.get("recipient_id"):
                    raise ValueError("recipient_id should not be provided for audience messages")
                if not data.get("audience"):
                    raise ValueError("audience is required for audience messages")
        return data

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "mode": "audience",
            "subject": "Holiday Notice",
            "message_body": "School will be closed tomorrow for holiday.",
            "audience": {
                "include_roles": ["PARENT"],
                "scope": "GOVERNORATE",
                "filters": [{"field": "kindergarten.governorate", "op": "EQ", "value": "Amman"}]
            },
            "allow_replies": False
        }
    })


class UserSummary(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "id": 7,
            "username": "manager1",
            "role": "MANAGER"
        }
    })


class MessageListItem(BaseModel):
    id: int
    thread_type: models.MessageThreadType
    sender_id: int
    recipient_id: Optional[int]
    thread_id: Optional[int]
    reply_to_id: Optional[int]
    subject: Optional[str]
    message_body: str
    allow_replies: bool
    created_at: datetime
    is_read: bool
    read_at: Optional[datetime]
    archived_at: Optional[datetime]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 101,
            "thread_type": "DIRECT",
            "sender_id": 7,
            "recipient_id": 42,
            "thread_id": 101,
            "reply_to_id": None,
            "subject": "Pickup reminder",
            "message_body": "Please pick up before 3 PM today.",
            "created_at": "2026-01-21T10:20:00Z",
            "is_read": False,
            "read_at": None,
            "archived_at": None
        }
    })


class MessageDetail(MessageListItem):
    sender: Optional[UserSummary] = None
    recipient: Optional[UserSummary] = None
    attachments: List["AttachmentResponse"] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 101,
            "thread_type": "DIRECT",
            "sender_id": 7,
            "recipient_id": 42,
            "thread_id": 101,
            "reply_to_id": None,
            "subject": "Pickup reminder",
            "message_body": "Please pick up before 3 PM today.",
            "created_at": "2026-01-21T10:20:00Z",
            "is_read": False,
            "read_at": None,
            "archived_at": None,
            "sender": {"id": 7, "username": "manager1", "role": "MANAGER"},
            "recipient": {"id": 42, "username": "parent1", "role": "PARENT"},
            "attachments": [
                {
                    "id": 9,
                    "file_name": "schedule.pdf",
                    "content_type": "application/pdf",
                    "file_size": 23456,
                    "url": "/comm/messages/attachments/9",
                    "created_at": "2026-01-21T10:30:00Z"
                }
            ]
        }
    })


class MessageReadResponse(BaseModel):
    message_id: int
    read_at: datetime

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message_id": 101,
            "read_at": "2026-01-21T10:21:00Z"
        }
    })


class MessageDeleteResponse(BaseModel):
    message_id: int
    deleted_at: datetime

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message_id": 101,
            "deleted_at": "2026-01-21T10:35:00Z"
        }
    })


class UnreadCountResponse(BaseModel):
    unread_count: int

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "unread_count": 3
        }
    })


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "page": 1,
            "page_size": 25,
            "total": 120,
            "total_pages": 5,
            "has_next": True,
            "has_prev": False
        }
    })


class MessageListResponse(BaseModel):
    items: List[MessageListItem]
    pagination: PaginationMeta

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [
                {
                    "id": 101,
                    "thread_type": "DIRECT",
                    "sender_id": 7,
                    "recipient_id": 42,
                    "thread_id": 101,
                    "reply_to_id": None,
                    "subject": "Pickup reminder",
                    "message_body": "Please pick up before 3 PM today.",
                    "created_at": "2026-01-21T10:20:00Z",
                    "is_read": False,
                    "read_at": None,
                    "archived_at": None
                }
            ],
            "pagination": {
                "page": 1,
                "page_size": 25,
                "total": 120,
                "total_pages": 5,
                "has_next": True,
                "has_prev": False
            }
        }
    })


class MessageReplyCreate(BaseModel):
    subject: Optional[str] = None
    message_body: str


class AudienceOptionsResponse(BaseModel):
    roles: List[Dict[str, str]]
    governorates: List[str]
    kindergartens: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "roles": [
                {"value": "PARENT", "label": "Parents"},
                {"value": "SUPERVISOR", "label": "Teachers"}
            ],
            "governorates": ["Amman", "Irbid", "Zarqa"],
            "kindergartens": [
                {"id": 1, "name": "Little Stars Kindergarten", "governorate": "Amman"}
            ],
            "classes": [
                {"id": 10, "name": "Class A", "kindergarten_id": 1, "kindergarten_name": "Little Stars"}
            ]
        }
    })


class AudienceRecipientPreview(BaseModel):
    id: int
    name: str
    role: str
    kindergarten_name: Optional[str] = None


class AudiencePreviewResponse(BaseModel):
    total_count: int
    recipients: List[AudienceRecipientPreview]
    has_more: bool

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total_count": 150,
            "recipients": [
                {"id": 42, "name": "Ahmed Al-Rashid", "role": "PARENT", "kindergarten_name": "Little Stars"},
                {"id": 43, "name": "Fatima Hassan", "role": "TEACHER", "kindergarten_name": "Little Stars"}
            ],
            "has_more": True
        }
    })

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "subject": "Re: Pickup reminder",
            "message_body": "Thanks for the reminder."
        }
    })


class MessageThreadResponse(BaseModel):
    root: MessageDetail
    replies: List[MessageDetail]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "root": {
                "id": 101,
                "thread_type": "DIRECT",
                "sender_id": 7,
                "recipient_id": 42,
                "thread_id": 101,
                "reply_to_id": None,
                "subject": "Pickup reminder",
                "message_body": "Please pick up before 3 PM today.",
                "created_at": "2026-01-21T10:20:00Z",
                "is_read": False,
                "read_at": None,
                "archived_at": None,
                "sender": {"id": 7, "username": "manager1", "role": "MANAGER"},
                "recipient": {"id": 42, "username": "parent1", "role": "PARENT"},
                "attachments": []
            },
            "replies": [
                {
                    "id": 102,
                    "thread_type": "DIRECT",
                    "sender_id": 42,
                    "recipient_id": 7,
                    "thread_id": 101,
                    "reply_to_id": 101,
                    "subject": "Re: Pickup reminder",
                    "message_body": "Thanks for the reminder.",
                    "created_at": "2026-01-21T10:25:00Z",
                    "is_read": True,
                    "read_at": "2026-01-21T10:26:00Z",
                    "archived_at": None,
                    "sender": {"id": 42, "username": "parent1", "role": "PARENT"},
                    "recipient": {"id": 7, "username": "manager1", "role": "MANAGER"},
                    "attachments": []
                }
            ]
        }
    })


class MessageArchiveResponse(BaseModel):
    message_id: int
    archived_at: Optional[datetime]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message_id": 101,
            "archived_at": "2026-01-21T10:35:00Z"
        }
    })


class BulkMessageActionRequest(BaseModel):
    message_ids: List[int]
    action: Literal["read", "archive", "unarchive", "delete"]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message_ids": [101, 102],
            "action": "archive"
        }
    })


class BulkMessageActionResult(BaseModel):
    action: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    succeeded_ids: List[int]
    failed_ids: List[int]
    errors: List[Dict[str, str]]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "action": "archive",
            "requested_count": 2,
            "succeeded_count": 2,
            "failed_count": 0,
            "succeeded_ids": [101, 102],
            "failed_ids": [],
            "errors": []
        }
    })


class AttachmentResponse(BaseModel):
    id: int
    file_name: str
    content_type: str
    file_size: int
    url: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "id": 9,
            "file_name": "schedule.pdf",
            "content_type": "application/pdf",
            "file_size": 23456,
            "url": "/comm/messages/attachments/9",
            "created_at": "2026-01-21T10:30:00Z"
        }
    })


class DeviceTokenCreate(BaseModel):
    token: str
    platform: models.DevicePlatform
    device_name: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "token": "device-token-1",
            "platform": "WEB",
            "device_name": "Chrome"
        }
    })


class DeviceTokenResponse(BaseModel):
    id: int
    token: str
    platform: models.DevicePlatform
    device_name: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "id": 5,
            "token": "device-token-1",
            "platform": "WEB",
            "device_name": "Chrome",
            "is_active": True,
            "created_at": "2026-01-21T10:31:00Z"
        }
    })


class AvailableRecipientResponse(BaseModel):
    id: int
    name: str
    role: str
    kindergarten_name: Optional[str]
    children_count: Optional[int]  # For parents - number of active children

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "id": 123,
            "name": "أحمد محمد",
            "role": "PARENT",
            "kindergarten_name": "روضة الأمل",
            "children_count": 2
        }
    })


class AvailableRecipientsResponse(BaseModel):
    parents: List[AvailableRecipientResponse]
    supervisors: List[AvailableRecipientResponse]

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "parents": [
                {
                    "id": 123,
                    "name": "أحمد محمد",
                    "role": "PARENT",
                    "kindergarten_name": "روضة الأمل",
                    "children_count": 2
                }
            ],
            "supervisors": [
                {
                    "id": 456,
                    "name": "فاطمة علي",
                    "role": "SUPERVISOR",
                    "kindergarten_name": "روضة الأمل",
                    "children_count": None
                }
            ]
        }
    })


MessageDetail.model_rebuild()


def _normalize_thread_type(thread_type: str) -> models.MessageThreadType:
    if not thread_type:
        raise validation_error(
            "thread_type is required",
            fields={"thread_type": "required"}
        )
    normalized = thread_type.strip().upper()
    if normalized == "BROADCAST":
        normalized = "ANNOUNCEMENT"
    if normalized in {"DIRECT", "ANNOUNCEMENT"}:
        return models.MessageThreadType(normalized)
    raise validation_error(
        "Invalid thread_type. Must be DIRECT or ANNOUNCEMENT",
        fields={"thread_type": "invalid"}
    )


def _can_access_message(db: Session, current_user: models.User, message: models.Message) -> bool:
    if current_user.role == models.UserRole.ADMIN:
        return True
    if message.thread_type == models.MessageThreadType.DIRECT:
        return current_user.id in {message.sender_id, message.recipient_id}
    if message.thread_type == models.MessageThreadType.ANNOUNCEMENT:
        if current_user.id == message.sender_id:
            return True
        return db.query(models.MessageRecipient.id).filter(
            models.MessageRecipient.message_id == message.id,
            models.MessageRecipient.recipient_user_id == current_user.id
        ).first() is not None
    return False


def _serialize_message(
    message: models.Message,
    read_at: Optional[datetime],
    archived_at: Optional[datetime],
    current_user: models.User
) -> MessageListItem:
    is_read = message.sender_id == current_user.id or bool(read_at)
    return MessageListItem(
        id=message.id,
        thread_type=message.thread_type,
        sender_id=message.sender_id,
        recipient_id=message.recipient_id,
        thread_id=message.thread_id,
        reply_to_id=message.reply_to_id,
        subject=message.subject,
        message_body=message.message_body,
        allow_replies=message.allow_replies,
        created_at=message.created_at,
        is_read=is_read,
        read_at=read_at,
        archived_at=archived_at
    )


def _serialize_message_detail(
    message: models.Message,
    read_at: Optional[datetime],
    archived_at: Optional[datetime],
    current_user: models.User
) -> MessageDetail:
    base = _serialize_message(message, read_at, archived_at, current_user).model_dump()
    return MessageDetail(
        **base,
        sender=UserSummary.model_validate(message.sender) if message.sender else None,
        recipient=UserSummary.model_validate(message.recipient) if message.recipient else None,
        attachments=_serialize_attachments(message)
    )


def _get_notification_recipients(
    db: Session,
    message: models.Message,
    sender: models.User
) -> List[models.User]:
    if message.thread_type == models.MessageThreadType.DIRECT and message.recipient_id:
        recipient = db.query(models.User).filter(models.User.id == message.recipient_id).first()
        if recipient and recipient.id != sender.id:
            return [recipient]
        return []

    if message.thread_type == models.MessageThreadType.ANNOUNCEMENT:
        # Get recipients from MessageRecipient table
        recipient_ids = db.query(models.MessageRecipient.recipient_user_id).filter(
            models.MessageRecipient.message_id == message.id
        ).all()
        if recipient_ids:
            return db.query(models.User).filter(
                models.User.id.in_([r[0] for r in recipient_ids]),
                models.User.status == models.UserStatus.ACTIVE
            ).all()
        return []

    return []


def _serialize_attachments(message: models.Message) -> List[AttachmentResponse]:
    attachments: List[AttachmentResponse] = []
    for attachment in message.attachments or []:
        if attachment.deleted_at:
            continue
        url = attachment.url or f"/comm/messages/attachments/{attachment.id}"
        attachments.append(AttachmentResponse(
            id=attachment.id,
            file_name=attachment.file_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            url=url,
            created_at=attachment.created_at
        ))
    return attachments


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

def _extract_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]
    return request.cookies.get("kinjo_token")


def _resolve_rate_limit_by_role(
    request: Request,
    admin_limit: str,
    manager_limit: str,
    supervisor_limit: str,
    parent_limit: str,
    fallback_limit: str
) -> str:
    token = _extract_token_from_request(request)
    if not token:
        return fallback_limit
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if not username:
            return fallback_limit
    except JWTError:
        return fallback_limit

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
    finally:
        db.close()

    if not user or user.status != models.UserStatus.ACTIVE:
        return fallback_limit

    if user.role == models.UserRole.ADMIN:
        return admin_limit
    if user.role == models.UserRole.MANAGER:
        return manager_limit
    if user.role == models.UserRole.SUPERVISOR:
        return supervisor_limit
    if user.role == models.UserRole.PARENT:
        return parent_limit
    return fallback_limit


def _messages_send_rate_limit(request: Request) -> str:
    return _resolve_rate_limit_by_role(
        request,
        settings.RATE_LIMIT_MESSAGES_SEND_ADMIN,
        settings.RATE_LIMIT_MESSAGES_SEND_MANAGER,
        settings.RATE_LIMIT_MESSAGES_SEND_SUPERVISOR,
        settings.RATE_LIMIT_MESSAGES_SEND_PARENT,
        settings.RATE_LIMIT_MESSAGES_SEND
    )


def _messages_reply_rate_limit(request: Request) -> str:
    return _resolve_rate_limit_by_role(
        request,
        settings.RATE_LIMIT_MESSAGES_REPLY_ADMIN,
        settings.RATE_LIMIT_MESSAGES_REPLY_MANAGER,
        settings.RATE_LIMIT_MESSAGES_REPLY_SUPERVISOR,
        settings.RATE_LIMIT_MESSAGES_REPLY_PARENT,
        settings.RATE_LIMIT_MESSAGES_REPLY
    )


@router.post("/messages", status_code=status.HTTP_201_CREATED, response_model=MessageDetail)
@limiter.limit(_messages_send_rate_limit)
def send_message(
    request: Request,
    msg_data: MessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message (Direct or Audience-based)"""

    # Validate message content
    message_body = (msg_data.message_body or "").strip()
    if not message_body:
        raise validation_error("Message body is required", fields={"message_body": "required"})

    # Validate message length
    max_message_length = getattr(settings, 'MAX_MESSAGE_LENGTH', 5000)
    max_subject_length = getattr(settings, 'MAX_SUBJECT_LENGTH', 255)
    
    if len(message_body) > max_message_length:
        raise validation_error(
            f"Message body too long. Maximum {max_message_length} characters allowed.",
            fields={"message_body": "too_long"}
        )

    subject = msg_data.subject.strip() if msg_data.subject else None
    if subject and len(subject) > max_subject_length:
        raise validation_error(
            f"Subject too long. Maximum {max_subject_length} characters allowed.",
            fields={"subject": "too_long"}
        )

    subject = validators.sanitize_input(subject) if subject else None
    message_body = validators.sanitize_input(message_body)

    # Determine message mode
    mode = getattr(msg_data, 'mode', 'direct')
    if mode not in ['direct', 'audience']:
        raise validation_error("Invalid message mode", fields={"mode": "must be 'direct' or 'audience'"})

    # Check for duplicate messages (prevent spam)
    duplicate_check_window = timedelta(minutes=settings.DUPLICATE_MESSAGE_CHECK_MINUTES or 5)
    recent_message = db.query(models.Message).filter(
        models.Message.sender_id == current_user.id,
        models.Message.message_body == message_body,
        models.Message.subject == subject,
        models.Message.created_at >= datetime.now(timezone.utc) - duplicate_check_window
    ).first()

    if recent_message:
        raise validation_error(
            f"تم إرسال رسالة مشابهة مؤخراً. يرجى الانتظار {settings.DUPLICATE_MESSAGE_CHECK_MINUTES or 5} دقائق قبل إعادة الإرسال.",
            fields={"message_body": "duplicate_message"}
        )

    # Validate manager role constraints
    if current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            raise validation_error(
                "Manager must be assigned to a kindergarten to send messages",
                fields={"kindergarten_id": "required"}
            )
        # Additional manager-specific validations can be added here

    if mode == 'direct':
        # Direct message - existing logic
        recipient, target_kindergarten_id = resolve_direct_recipient(
            db,
            current_user,
            msg_data.recipient_id,
            msg_data.kindergarten_id
        )
        validate_direct_permissions(db, current_user, recipient)

        msg = models.Message(
            thread_type=models.MessageThreadType.DIRECT,
            sender_id=current_user.id,
            kindergarten_id=target_kindergarten_id,
            subject=subject,
            message_body=message_body,
            recipient_id=recipient.id,
            allow_replies=True
        )

        db.add(msg)
        db.flush()
        msg.thread_id = msg.id
        db.commit()
        db.refresh(msg)

        log_audit_event(
            db=db,
            action="MESSAGE_SENT",
            actor=current_user,
            target_type="Message",
            target_ids=msg.id,
            metadata={
                "thread_type": msg.thread_type.value,
                "recipient_role": recipient.role.value,
                "recipient_id": recipient.id,
                "kindergarten_id": target_kindergarten_id,
                "sender_role": current_user.role.value
            },
            sensitivity_level=2
        )

    else:
        # Audience-based message - new dynamic system
        if not msg_data.audience:
            raise validation_error("Audience definition is required for audience messages", fields={"audience": "required"})

        # Resolve recipients using the new dynamic system
        recipient_ids = resolve_recipients(
            db=db,
            audience=msg_data.audience,
            sender=current_user
        )

        if not recipient_ids:
            raise validation_error(
                "لا يوجد مستلمون مطابقون للمعايير المحددة.",
                fields={"audience": "empty"}
            )

        # Check recipient limit
        if len(recipient_ids) > settings.MAX_MESSAGE_RECIPIENTS:
            raise validation_error(
                f"عدد المستلمين كبير جداً. الحد الأقصى المسموح هو {settings.MAX_MESSAGE_RECIPIENTS} مستلم.",
                fields={"audience": "too_many_recipients"}
            )

        # Determine target kindergarten (for single kindergarten scope)
        target_kindergarten_id = None
        scope_value = msg_data.audience.scope.value if hasattr(msg_data.audience.scope, "value") else str(msg_data.audience.scope)
        if scope_value.upper() == "KINDERGARTEN" and msg_data.audience.kindergarten_ids:
            if len(msg_data.audience.kindergarten_ids) == 1:
                target_kindergarten_id = msg_data.audience.kindergarten_ids[0]
        # Auto-scope managers to their own kindergarten
        if current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id:
            target_kindergarten_id = current_user.kindergarten_id

        # Build targeting metadata for audit/display
        target_mode = scope_value.upper()
        target_roles_json = msg_data.audience.include_roles or None
        target_governorates_json = None
        target_kg_ids_json = None
        if scope_value.upper() == "GOVERNORATE":
            from messaging_permissions import _resolve_governorate_filter_values
            target_governorates_json = _resolve_governorate_filter_values(msg_data.audience) or None
        if msg_data.audience.kindergarten_ids:
            target_kg_ids_json = list(msg_data.audience.kindergarten_ids)

        msg = models.Message(
            thread_type=models.MessageThreadType.ANNOUNCEMENT,
            sender_id=current_user.id,
            kindergarten_id=target_kindergarten_id,
            subject=subject,
            message_body=message_body,
            recipient_id=None,
            allow_replies=bool(getattr(msg_data, 'allow_replies', True)),
            target_mode=target_mode,
            target_roles=target_roles_json,
            target_governorates=target_governorates_json,
            target_kindergarten_ids=target_kg_ids_json,
            recipient_count=len(recipient_ids),
        )

        db.add(msg)
        db.flush()
        msg.thread_id = msg.id
        db.commit()
        db.refresh(msg)

        # Create message recipients
        for recipient_user_id in recipient_ids:
            db.add(models.MessageRecipient(
                message_id=msg.id,
                recipient_user_id=recipient_user_id,
                status="queued"
            ))

        db.commit()

        log_audit_event(
            db=db,
            action="MESSAGE_ANNOUNCEMENT_SENT",
            actor=current_user,
            target_type="Message",
            target_ids=msg.id,
            metadata={
                "thread_type": msg.thread_type.value,
                "recipient_count": len(recipient_ids),
                "audience_scope": msg_data.audience.scope.value if hasattr(msg_data.audience.scope, 'value') else str(msg_data.audience.scope),
                "kindergarten_id": target_kindergarten_id,
                "sender_role": current_user.role.value,
                "audience_summary": {
                    "include_roles": msg_data.audience.include_roles,
                    "kindergarten_ids": msg_data.audience.kindergarten_ids
                }
            },
            sensitivity_level=2
        )

    # Send notifications (existing logic)
    try:
        recipients = _get_notification_recipients(db, msg, current_user)
        create_message_notifications(db, msg, recipients)
        if recipients:
            log_audit_event(
                db=db,
                action="MESSAGE_NOTIFICATIONS_QUEUED",
                actor=current_user,
                target_type="Message",
                target_ids=msg.id,
                metadata={"recipient_count": len(recipients)},
                sensitivity_level=1
            )
    except (RuntimeError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Failed to enqueue notifications for message %s: %s", msg.id, exc)

    return _serialize_message_detail(msg, read_at=None, archived_at=None, current_user=current_user)


@router.get("/audience/options", response_model=AudienceOptionsResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_LIST)
def get_audience_options(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available options for building audience filters"""
    from messaging_permissions import get_audience_options

    options = get_audience_options(db, current_user)
    return AudienceOptionsResponse(**options)


@router.post("/audience/preview", response_model=AudiencePreviewResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_LIST)
def preview_audience(
    request: Request,
    audience: AudienceDefinition,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Preview recipients for an audience definition"""

    recipient_ids = resolve_recipients(db=db, audience=audience, sender=current_user)

    # Get basic info about recipients (without sensitive data)
    recipients = []
    if recipient_ids:
        users = db.query(models.User).filter(models.User.id.in_(recipient_ids[:10])).all()  # Limit preview
        recipients = []
        for user in users:
            # Get name based on role
            if user.role == models.UserRole.PARENT and user.parent_profile:
                name = f"{user.parent_profile.first_name} {user.parent_profile.last_name or ''}".strip()
            else:
                name = user.username
            
            recipients.append({
                "id": user.id,
                "name": name,
                "role": user.role.value,
                "kindergarten_name": user.kindergarten.name_ar if user.kindergarten else None
            })

    return AudiencePreviewResponse(
        total_count=len(recipient_ids),
        recipients=recipients,
        has_more=len(recipient_ids) > 10
    )


@router.get("/messages", response_model=MessageListResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_LIST)
def list_my_messages(
    request: Request,
    thread_type: Optional[str] = Query(None),
    sender_id: Optional[int] = Query(None),
    recipient_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    unread_only: bool = Query(False),
    include_archived: bool = Query(False),
    archived_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List messages relevant to the current user"""
    state_alias = aliased(models.MessageUserState)
    query = db.query(models.Message, state_alias.read_at, state_alias.archived_at, state_alias.deleted_at).outerjoin(
        state_alias,
        and_(
            state_alias.message_id == models.Message.id,
            state_alias.user_id == current_user.id
        )
    )

    query = query.filter(
        models.Message.thread_type.in_(
            [models.MessageThreadType.DIRECT, models.MessageThreadType.ANNOUNCEMENT]
        )
    )

    if current_user.role != models.UserRole.ADMIN:
        announcement_recipient_exists = exists(
            select(models.MessageRecipient.id).where(
                models.MessageRecipient.message_id == models.Message.id,
                models.MessageRecipient.recipient_user_id == current_user.id,
            )
        )

        query = query.filter(
            or_(
                models.Message.sender_id == current_user.id,
                models.Message.recipient_id == current_user.id,
                and_(
                    models.Message.thread_type == models.MessageThreadType.ANNOUNCEMENT,
                    announcement_recipient_exists
                )
            )
        )

    query = query.filter(state_alias.deleted_at.is_(None))
    if archived_only:
        query = query.filter(state_alias.archived_at.isnot(None))
    elif not include_archived:
        query = query.filter(state_alias.archived_at.is_(None))

    if thread_type:
        query = query.filter(models.Message.thread_type == _normalize_thread_type(thread_type))

    if sender_id:
        query = query.filter(models.Message.sender_id == sender_id)

    if recipient_id:
        query = query.filter(models.Message.recipient_id == recipient_id)

    if search:
        like_term = f"%{search}%"
        query = query.filter(
            or_(
                models.Message.subject.ilike(like_term),
                models.Message.message_body.ilike(like_term)
            )
        )

    if unread_only:
        query = query.filter(
            state_alias.read_at.is_(None),
            models.Message.sender_id != current_user.id
        )

    total = query.order_by(None).count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    rows = query.order_by(desc(models.Message.created_at), desc(models.Message.id)).offset(offset).limit(page_size).all()

    items = [_serialize_message(msg, read_at, archived_at, current_user) for msg, read_at, archived_at, _ in rows]
    return MessageListResponse(
        items=items,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )
    )


@router.get("/messages/unread/count", response_model=UnreadCountResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_READ)
def get_unread_count(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return unread message count for the current user"""
    cache_key = f"comm:unread_count:user_{current_user.id}"
    if not settings.TESTING:
        cached_count = cache_service.get(cache_key)
        if cached_count is not None:
            try:
                return UnreadCountResponse(unread_count=int(cached_count))
            except (TypeError, ValueError):
                # Ignore malformed cache payloads and refresh from DB.
                pass

    state_alias = aliased(models.MessageUserState)
    query = db.query(models.Message.id).outerjoin(
        state_alias,
        and_(
            state_alias.message_id == models.Message.id,
            state_alias.user_id == current_user.id
        )
    )

    query = query.filter(
        models.Message.thread_type.in_(
            [models.MessageThreadType.DIRECT, models.MessageThreadType.ANNOUNCEMENT]
        )
    )

    if current_user.role != models.UserRole.ADMIN:
        announcement_recipient_exists = exists(
            select(models.MessageRecipient.id).where(
                models.MessageRecipient.message_id == models.Message.id,
                models.MessageRecipient.recipient_user_id == current_user.id,
            )
        )
        query = query.filter(
            or_(
                models.Message.recipient_id == current_user.id,
                and_(
                    models.Message.thread_type == models.MessageThreadType.ANNOUNCEMENT,
                    announcement_recipient_exists
                )
            )
        )

    query = query.filter(
        state_alias.deleted_at.is_(None),
        state_alias.archived_at.is_(None),
        state_alias.read_at.is_(None),
        models.Message.sender_id != current_user.id
    )

    unread_count = query.count()
    if not settings.TESTING:
        cache_service.set(cache_key, unread_count, ttl_seconds=15)
    return UnreadCountResponse(unread_count=unread_count)


@router.get("/messages/available-recipients", response_model=AvailableRecipientsResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_READ)
def get_available_recipients(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available recipients for messaging (managers only)"""
    if current_user.role != models.UserRole.MANAGER:
        raise forbidden_error("Only managers can access available recipients")

    if not current_user.kindergarten_id:
        raise validation_error("Manager must be assigned to a kindergarten")

    # Get parents with active enrollments in manager's kindergarten
    parents_query = db.query(
        models.User.id,
        func.concat(
            models.ParentProfile.first_name,
            ' ',
            func.coalesce(models.ParentProfile.last_name, '')
        ).label("name"),
        models.Kindergarten.name_ar.label("kindergarten_name"),
        func.count(models.Child.id).label("children_count")
    ).join(
        models.ParentProfile,
        models.ParentProfile.user_id == models.User.id
    ).join(
        models.Child,
        models.Child.parent_id == models.ParentProfile.id
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.Kindergarten,
        models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id
    ).filter(
        models.User.status == models.UserStatus.ACTIVE,
        models.User.role == models.UserRole.PARENT,
        models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).group_by(
        models.User.id,
        models.ParentProfile.first_name,
        models.ParentProfile.last_name,
        models.Kindergarten.name_ar
    ).order_by(models.ParentProfile.first_name)

    parents = [
        AvailableRecipientResponse(
            id=row[0],
            name=row[1].strip(),
            role="PARENT",
            kindergarten_name=row[2],
            children_count=row[3]
        )
        for row in parents_query.all()
    ]

    # Get supervisors in manager's kindergarten
    supervisors_query = db.query(
        models.User.id,
        models.User.username.label("name"),
        models.Kindergarten.name_ar.label("kindergarten_name")
    ).join(
        models.Kindergarten,
        models.Kindergarten.id == models.User.kindergarten_id
    ).filter(
        models.User.status == models.UserStatus.ACTIVE,
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.kindergarten_id == current_user.kindergarten_id,
        models.User.id != current_user.id  # Exclude self
    ).order_by(models.User.username)

    supervisors = [
        AvailableRecipientResponse(
            id=row[0],
            name=row[1],
            role="SUPERVISOR",
            kindergarten_name=row[2],
            children_count=None
        )
        for row in supervisors_query.all()
    ]

    return AvailableRecipientsResponse(
        parents=parents,
        supervisors=supervisors
    )


@router.get("/messages/{message_id:int}", response_model=MessageDetail)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_GET)
def get_message(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch a single message with access control"""
    state_alias = aliased(models.MessageUserState)
    row = (
        db.query(models.Message, state_alias.read_at, state_alias.archived_at, state_alias.deleted_at)
        .outerjoin(
            state_alias,
            and_(
                state_alias.message_id == models.Message.id,
                state_alias.user_id == current_user.id
            )
        )
        .filter(models.Message.id == message_id)
        .first()
    )

    if not row:
        raise not_found_error("Message not found")

    message, read_at, archived_at, deleted_at = row

    if deleted_at:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    log_audit_event(
        db=db,
        action="MESSAGE_VIEWED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        after_state=model_to_dict(message),
        metadata={"thread_type": message.thread_type.value},
        sensitivity_level=1
    )

    return _serialize_message_detail(message, read_at, archived_at=archived_at, current_user=current_user)


@router.post("/messages/{message_id:int}/read", response_model=MessageReadResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_READ)
def mark_message_read(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a message as read for the current user"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    if message.sender_id == current_user.id:
        return MessageReadResponse(message_id=message.id, read_at=message.created_at)

    state = db.query(models.MessageUserState).filter(
        models.MessageUserState.message_id == message.id,
        models.MessageUserState.user_id == current_user.id
    ).first()

    if state and state.deleted_at:
        raise not_found_error("Message not found")

    read_timestamp = datetime.now(timezone.utc)
    if message.thread_type == models.MessageThreadType.ANNOUNCEMENT:
        recipient_state = db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == message.id,
            models.MessageRecipient.recipient_user_id == current_user.id
        ).first()
        if recipient_state and not recipient_state.read_at:
            recipient_state.read_at = read_timestamp

    if not state:
        state = models.MessageUserState(
            message_id=message.id,
            user_id=current_user.id,
            read_at=read_timestamp
        )
        db.add(state)
    elif not state.read_at:
        state.read_at = read_timestamp

    db.commit()

    log_audit_event(
        db=db,
        action="MESSAGE_READ",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        before_state=None,
        after_state=model_to_dict(message),
        metadata={"read_at": state.read_at.isoformat() if state.read_at else None},
        sensitivity_level=1
    )

    return MessageReadResponse(message_id=message.id, read_at=state.read_at)


@router.delete("/messages/{message_id:int}", response_model=MessageDeleteResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_DELETE)
def delete_message(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete a message for the current user"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    state = db.query(models.MessageUserState).filter(
        models.MessageUserState.message_id == message.id,
        models.MessageUserState.user_id == current_user.id
    ).first()

    if not state:
        state = models.MessageUserState(
            message_id=message.id,
            user_id=current_user.id
        )
        db.add(state)

    if not state.deleted_at:
        state.deleted_at = datetime.now(timezone.utc)

    db.commit()

    log_audit_event(
        db=db,
        action="MESSAGE_DELETED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        after_state=model_to_dict(message),
        metadata={"deleted_at": state.deleted_at.isoformat() if state.deleted_at else None},
        sensitivity_level=2
    )

    return MessageDeleteResponse(message_id=message.id, deleted_at=state.deleted_at)


@router.post("/messages/{message_id:int}/archive", response_model=MessageArchiveResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_ARCHIVE)
def archive_message(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive a message for the current user"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    state = db.query(models.MessageUserState).filter(
        models.MessageUserState.message_id == message.id,
        models.MessageUserState.user_id == current_user.id
    ).first()

    if not state:
        state = models.MessageUserState(
            message_id=message.id,
            user_id=current_user.id
        )
        db.add(state)

    state.archived_at = datetime.now(timezone.utc)
    db.commit()

    log_audit_event(
        db=db,
        action="MESSAGE_ARCHIVED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        metadata={"archived_at": state.archived_at.isoformat()},
        sensitivity_level=1
    )

    return MessageArchiveResponse(message_id=message.id, archived_at=state.archived_at)


@router.post("/messages/{message_id:int}/unarchive", response_model=MessageArchiveResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_ARCHIVE)
def unarchive_message(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unarchive a message for the current user"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    state = db.query(models.MessageUserState).filter(
        models.MessageUserState.message_id == message.id,
        models.MessageUserState.user_id == current_user.id
    ).first()

    if not state:
        state = models.MessageUserState(
            message_id=message.id,
            user_id=current_user.id
        )
        db.add(state)

    state.archived_at = None
    db.commit()

    log_audit_event(
        db=db,
        action="MESSAGE_UNARCHIVED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        sensitivity_level=1
    )

    return MessageArchiveResponse(message_id=message.id, archived_at=None)


@router.post("/messages/bulk", response_model=BulkMessageActionResult)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_BULK)
def bulk_message_action(
    request: Request,
    payload: BulkMessageActionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk update message state (read, archive, unarchive, delete)"""
    message_ids = list(dict.fromkeys(payload.message_ids or []))
    if not message_ids:
        raise validation_error("message_ids is required", fields={"message_ids": "required"})
    if len(message_ids) > settings.MAX_BULK_MESSAGES:
        raise validation_error(
            f"Bulk limit exceeded (max {settings.MAX_BULK_MESSAGES})",
            fields={"message_ids": "too_many"}
        )

    succeeded_ids: List[int] = []
    failed_ids: List[int] = []
    errors: List[Dict[str, str]] = []

    # Batch-load all messages to avoid N+1 queries
    messages_by_id = {
        m.id: m for m in
        db.query(models.Message).filter(models.Message.id.in_(message_ids)).all()
    } if message_ids else {}

    for message_id in message_ids:
        message = messages_by_id.get(message_id)
        if not message:
            failed_ids.append(message_id)
            errors.append({"id": str(message_id), "error": "not_found"})
            continue

        if not _can_access_message(db, current_user, message):
            failed_ids.append(message_id)
            errors.append({"id": str(message_id), "error": "forbidden"})
            continue

        state = db.query(models.MessageUserState).filter(
            models.MessageUserState.message_id == message.id,
            models.MessageUserState.user_id == current_user.id
        ).first()

        if not state:
            state = models.MessageUserState(
                message_id=message.id,
                user_id=current_user.id
            )
            db.add(state)

        if payload.action == "read":
            if message.sender_id != current_user.id:
                read_timestamp = state.read_at or datetime.now(timezone.utc)
                state.read_at = read_timestamp
                if message.thread_type == models.MessageThreadType.ANNOUNCEMENT:
                    recipient_state = db.query(models.MessageRecipient).filter(
                        models.MessageRecipient.message_id == message.id,
                        models.MessageRecipient.recipient_user_id == current_user.id
                    ).first()
                    if recipient_state and not recipient_state.read_at:
                        recipient_state.read_at = read_timestamp
        elif payload.action == "archive":
            state.archived_at = datetime.now(timezone.utc)
        elif payload.action == "unarchive":
            state.archived_at = None
        elif payload.action == "delete":
            state.deleted_at = datetime.now(timezone.utc)
        else:
            failed_ids.append(message_id)
            errors.append({"id": str(message_id), "error": "invalid_action"})
            continue

        succeeded_ids.append(message_id)

    db.commit()

    if succeeded_ids:
        log_audit_event(
            db=db,
            action=f"MESSAGE_BULK_{payload.action.upper()}",
            actor=current_user,
            target_type="Message",
            target_ids=succeeded_ids,
            metadata={"requested": len(message_ids), "succeeded": len(succeeded_ids)},
            sensitivity_level=2
        )

    return BulkMessageActionResult(
        action=payload.action,
        requested_count=len(message_ids),
        succeeded_count=len(succeeded_ids),
        failed_count=len(failed_ids),
        succeeded_ids=succeeded_ids,
        failed_ids=failed_ids,
        errors=errors
    )


@router.post("/messages/{message_id:int}/replies", response_model=MessageDetail)
@limiter.limit(_messages_reply_rate_limit)
def reply_to_message(
    request: Request,
    message_id: int,
    reply_data: MessageReplyCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reply to a message"""
    parent = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not parent:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, parent):
        raise forbidden_error("You do not have access to this message")

    if not parent.allow_replies:
        raise forbidden_error("Replies are not allowed for this message")

    message_body = (reply_data.message_body or "").strip()
    if not message_body:
        raise validation_error("Message body is required", fields={"message_body": "required"})

    subject = reply_data.subject.strip() if reply_data.subject else parent.subject
    subject = validators.sanitize_input(subject) if subject else None
    message_body = validators.sanitize_input(message_body)

    if parent.thread_type == models.MessageThreadType.DIRECT:
        if not parent.thread_id:
            parent.thread_id = parent.id
            db.commit()

        recipient_id = parent.sender_id if current_user.id == parent.recipient_id else parent.recipient_id
        if not recipient_id:
            raise validation_error("Direct replies require a valid recipient")

        recipient = db.query(models.User).filter(models.User.id == recipient_id).first()
        if not recipient:
            raise not_found_error("Recipient not found")

        validate_direct_permissions(db, current_user, recipient)
        target_kindergarten_id = resolve_direct_kindergarten_id(
            current_user,
            recipient,
            parent.kindergarten_id
        )

        reply_msg = models.Message(
            thread_type=models.MessageThreadType.DIRECT,
            sender_id=current_user.id,
            recipient_id=recipient.id,
            kindergarten_id=target_kindergarten_id,
            subject=subject,
            message_body=message_body,
            reply_to_id=parent.id,
            thread_id=parent.thread_id,
            allow_replies=True
        )

        db.add(reply_msg)
        db.commit()
        db.refresh(reply_msg)
    elif parent.thread_type == models.MessageThreadType.ANNOUNCEMENT:
        if current_user.id == parent.sender_id:
            raise forbidden_error("Announcement sender cannot reply to their own message")

        recipient = db.query(models.User).filter(models.User.id == parent.sender_id).first()
        if not recipient:
            raise not_found_error("Recipient not found")

        validate_direct_permissions(db, current_user, recipient)
        target_kindergarten_id = resolve_direct_kindergarten_id(
            current_user,
            recipient,
            parent.kindergarten_id
        )

        reply_msg = models.Message(
            thread_type=models.MessageThreadType.DIRECT,
            sender_id=current_user.id,
            recipient_id=recipient.id,
            kindergarten_id=target_kindergarten_id,
            subject=subject,
            message_body=message_body,
            reply_to_id=parent.id,
            allow_replies=True
        )
        db.add(reply_msg)
        db.flush()
        reply_msg.thread_id = reply_msg.id
        db.commit()
        db.refresh(reply_msg)
    else:
        raise validation_error("Replies are only supported for direct messages")

    log_audit_event(
        db=db,
        action="MESSAGE_REPLIED",
        actor=current_user,
        target_type="Message",
        target_ids=reply_msg.id,
        after_state=model_to_dict(reply_msg),
        metadata={
            "reply_to_id": parent.id,
            "reply_to_type": parent.thread_type.value,
            "thread_id": reply_msg.thread_id
        },
        sensitivity_level=2
    )

    try:
        recipients = _get_notification_recipients(db, reply_msg, current_user)
        create_message_notifications(db, reply_msg, recipients)
        if recipients:
            log_audit_event(
                db=db,
                action="MESSAGE_NOTIFICATIONS_QUEUED",
                actor=current_user,
                target_type="Message",
                target_ids=reply_msg.id,
                metadata={"recipient_count": len(recipients)},
                sensitivity_level=1
            )
    except (RuntimeError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Failed to enqueue notifications for message %s: %s", reply_msg.id, exc)

    return _serialize_message_detail(reply_msg, read_at=None, archived_at=None, current_user=current_user)


@router.get("/messages/{message_id:int}/replies", response_model=MessageThreadResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_GET)
def list_message_replies(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List replies for a message thread"""
    root = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not root:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, root):
        raise forbidden_error("You do not have access to this message")

    thread_id = root.thread_id or root.id
    root_state = db.query(models.MessageUserState).filter(
        models.MessageUserState.message_id == root.id,
        models.MessageUserState.user_id == current_user.id
    ).first()
    state_alias = aliased(models.MessageUserState)
    rows = (
        db.query(models.Message, state_alias.read_at, state_alias.archived_at, state_alias.deleted_at)
        .outerjoin(
            state_alias,
            and_(
                state_alias.message_id == models.Message.id,
                state_alias.user_id == current_user.id
            )
        )
        .filter(models.Message.thread_id == thread_id)
        .filter(models.Message.id != root.id)
        .filter(state_alias.deleted_at.is_(None))
        .order_by(models.Message.created_at.asc(), models.Message.id.asc())
        .all()
    )

    replies = [_serialize_message_detail(msg, read_at, archived_at, current_user=current_user) for msg, read_at, archived_at, _ in rows]
    return MessageThreadResponse(
        root=_serialize_message_detail(
            root,
            read_at=root_state.read_at if root_state else None,
            archived_at=root_state.archived_at if root_state else None,
            current_user=current_user
        ),
        replies=replies
    )


@router.post("/messages/{message_id:int}/attachments", response_model=AttachmentResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_UPLOAD)
def upload_message_attachment(
    request: Request,
    message_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a file attachment for a message"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")
    if current_user.id != message.sender_id:
        raise forbidden_error("Only the sender can add attachments")
    if current_user.role not in {models.UserRole.ADMIN, models.UserRole.MANAGER}:
        raise forbidden_error("Attachments are only allowed for admins and managers")

    try:
        storage_provider, storage_key, file_size = save_attachment(file)
    except ValueError as exc:
        raise validation_error(str(exc))
    attachment = models.MessageAttachment(
        message_id=message.id,
        uploaded_by_id=current_user.id,
        file_name=file.filename or "attachment",
        content_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        storage_provider=storage_provider,
        storage_key=storage_key
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    log_audit_event(
        db=db,
        action="MESSAGE_ATTACHMENT_ADDED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        metadata={"attachment_id": attachment.id, "file_name": attachment.file_name},
        sensitivity_level=2
    )

    return AttachmentResponse(
        id=attachment.id,
        file_name=attachment.file_name,
        content_type=attachment.content_type,
        file_size=attachment.file_size,
        url=attachment.url or f"/comm/messages/attachments/{attachment.id}",
        created_at=attachment.created_at
    )


@router.get("/messages/{message_id:int}/attachments", response_model=List[AttachmentResponse])
@limiter.limit(settings.RATE_LIMIT_MESSAGES_GET)
def list_message_attachments(
    request: Request,
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List attachments for a message"""
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise not_found_error("Message not found")

    if not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this message")

    attachments = []
    for attachment in message.attachments or []:
        if attachment.deleted_at:
            continue
        attachments.append(AttachmentResponse(
            id=attachment.id,
            file_name=attachment.file_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            url=attachment.url or f"/comm/messages/attachments/{attachment.id}",
            created_at=attachment.created_at
        ))

    return attachments


@router.get("/messages/attachments/{attachment_id}")
@limiter.limit(settings.RATE_LIMIT_MESSAGES_GET)
def download_message_attachment(
    request: Request,
    attachment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download a message attachment"""
    attachment = db.query(models.MessageAttachment).filter(
        models.MessageAttachment.id == attachment_id,
        models.MessageAttachment.deleted_at.is_(None)
    ).first()
    if not attachment:
        raise not_found_error("Attachment not found")

    message = db.query(models.Message).filter(models.Message.id == attachment.message_id).first()
    if not message or not _can_access_message(db, current_user, message):
        raise forbidden_error("You do not have access to this attachment")

    log_audit_event(
        db=db,
        action="MESSAGE_ATTACHMENT_DOWNLOADED",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        metadata={"attachment_id": attachment.id},
        sensitivity_level=1
    )

    if attachment.storage_provider == "s3":
        import boto3
        session = boto3.session.Session(
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION
        )
        client = session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL or None)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": attachment.storage_key},
            ExpiresIn=300
        )
        return RedirectResponse(url=url)

    file_path = resolve_attachment_path(attachment.storage_key)
    return FileResponse(
        path=file_path,
        media_type=attachment.content_type,
        filename=attachment.file_name
    )


@router.post("/notifications/devices", response_model=DeviceTokenResponse)
@limiter.limit(settings.RATE_LIMIT_MESSAGES_READ)
def register_device_token(
    request: Request,
    payload: DeviceTokenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register or refresh a device token for push notifications"""
    token = payload.token.strip()
    if not token:
        raise validation_error("Device token is required", fields={"token": "required"})

    existing = db.query(models.UserDeviceToken).filter(models.UserDeviceToken.token == token).first()
    if existing and existing.user_id != current_user.id:
        raise forbidden_error("Device token already registered to another user")

    if existing:
        existing.platform = payload.platform
        existing.device_name = payload.device_name
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return DeviceTokenResponse.model_validate(existing)

    device = models.UserDeviceToken(
        user_id=current_user.id,
        token=token,
        platform=payload.platform,
        device_name=payload.device_name,
        is_active=True
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceTokenResponse.model_validate(device)


@router.delete("/notifications/devices/{token}")
@limiter.limit(settings.RATE_LIMIT_MESSAGES_READ)
def unregister_device_token(
    request: Request,
    token: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate a device token"""
    device = db.query(models.UserDeviceToken).filter(
        models.UserDeviceToken.token == token,
        models.UserDeviceToken.user_id == current_user.id
    ).first()
    if not device:
        raise not_found_error("Device token not found")
    device.is_active = False
    db.commit()
    return {"status": "removed"}

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
        today = _today()
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

    # Kindergarten scope check
    if current_user.role == models.UserRole.PARENT:
        # Parent must have a child enrolled in the survey's kindergarten
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if parent_profile:
            active_statuses = [models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.ACCEPTED]
            has_child_in_kg = db.query(models.EnrollmentApplication).join(
                models.Child, models.Child.id == models.EnrollmentApplication.child_id
            ).filter(
                models.Child.parent_id == parent_profile.id,
                models.EnrollmentApplication.kindergarten_id == survey.kindergarten_id,
                models.EnrollmentApplication.status.in_(active_statuses)
            ).first()
            if not has_child_in_kg:
                raise HTTPException(status_code=403, detail="No children enrolled in this survey's kindergarten")
        else:
            raise HTTPException(status_code=403, detail="Parent profile not found")
    elif current_user.role != models.UserRole.ADMIN:
        validators.validate_kindergarten_scope(current_user, survey.kindergarten_id)

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
