"""Account self-service endpoints for the signed-in user, whatever their role.

`admin_endpoints.py` already exposes `PUT /api/admin/profile` and
`POST /api/admin/profile/password`, but both sit behind `require_admin`. That
left every other role — manager, supervisor, parent — with no audited way to
change its own name, phone, password or notification preferences: the shared
settings page (`templates/user/settings.html`) had save buttons that only
raised a success toast and wrote nothing.

These endpoints are the role-neutral counterpart. They act on
`current_user` only, so there is no object-level authorisation to get wrong:
a caller can never name someone else's record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

import models
import validators
from admin_security import log_audit_event, unauthenticated_error, validation_error
from audit_actions import AuditAction
from auth import get_password_hash, verify_password
from database import get_db
from dependencies import get_current_user
from rate_limiter import limiter

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas (Pydantic v2)
# ---------------------------------------------------------------------------


class MeProfileUpdateSchema(BaseModel):
    """Self-editable profile fields.

    `username` and `email` are deliberately absent: both are identity keys used
    for sign-in, and the settings UI renders them disabled with "contact
    support". Accepting them here would let a user silently take over an
    address the admin console treats as unique.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)


class MePasswordChangeSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class MeNotificationPrefsSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    in_app: bool = True
    email: bool = True


_DEFAULT_PREFS: Dict[str, bool] = {"in_app": True, "email": True}


def _read_prefs(user: models.User) -> Dict[str, bool]:
    """Read the two channel toggles this page owns, defaulting to on.

    `User.notification_preferences` is a shared JSON column that
    `routers/supervisor.py` also writes richer per-event keys into, so this
    reads only the keys it understands and `_write_prefs` preserves the rest.
    """
    raw = user.notification_preferences if isinstance(user.notification_preferences, dict) else {}
    prefs = dict(_DEFAULT_PREFS)
    for key in prefs:
        if isinstance(raw.get(key), bool):
            prefs[key] = raw[key]
    return prefs


def _write_prefs(user: models.User, prefs: Dict[str, bool]) -> None:
    """Merge the channel toggles back without dropping other writers' keys."""
    raw = user.notification_preferences if isinstance(user.notification_preferences, dict) else {}
    merged: Dict[str, Any] = {**raw, **prefs}
    # Reassign rather than mutate: a plain JSON column is not change-tracked, so
    # an in-place update would not be flushed.
    user.notification_preferences = merged


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/profile")
@limiter.limit("30/minute")
def get_my_profile(
    request: Request,
    current_user: models.User = Depends(get_current_user),
):
    """Return the signed-in user's own editable profile fields."""
    return {
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
        "role": current_user.role.value if current_user.role else None,
    }


@router.put("/profile")
@limiter.limit("10/minute")
def update_my_profile(
    request: Request,
    payload: MeProfileUpdateSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the signed-in user's own name and phone number."""
    if payload.phone_number:
        if not validators.validate_jordan_phone(payload.phone_number):
            raise validation_error(
                "رقم هاتف أردني غير صالح / Invalid Jordanian phone number",
                fields={"phone_number": "invalid"},
            )

    before = {
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
    }

    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone_number is not None:
        # An empty string clears the field rather than storing "".
        current_user.phone_number = payload.phone_number or None

    after = {
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
    }

    if before == after:
        return {
            "message_ar": "لا توجد تغييرات لحفظها",
            "message_en": "No changes to save",
            "changed": False,
            **after,
        }

    db.commit()
    db.refresh(current_user)

    log_audit_event(
        db,
        AuditAction.USER_PROFILE_UPDATED,
        current_user,
        "User",
        target_ids=current_user.id,
        before_state=before,
        after_state=after,
        sensitivity_level=2,
    )
    # log_audit_event only flushes; without this commit get_db()'s close()
    # rolls the audit row back. See tests/test_audit_durability.py.
    db.commit()

    return {
        "message_ar": "تم حفظ التغييرات بنجاح",
        "message_en": "Changes saved successfully",
        "changed": True,
        **after,
    }


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------


@router.post("/password")
@limiter.limit("5/minute")
def change_my_password(
    request: Request,
    payload: MePasswordChangeSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the signed-in user's own password."""
    if payload.new_password != payload.confirm_password:
        raise validation_error(
            "كلمتا المرور غير متطابقتين / New passwords do not match",
            fields={"confirm_password": "mismatch"},
        )

    if not verify_password(payload.current_password, current_user.hashed_password):
        log_audit_event(
            db,
            AuditAction.USER_PASSWORD_CHANGE_FAILED,
            current_user,
            "User",
            target_ids=current_user.id,
            metadata={"reason": "Current password incorrect"},
            sensitivity_level=3,
        )
        db.commit()
        raise unauthenticated_error(
            "كلمة المرور الحالية غير صحيحة / Current password is incorrect"
        )

    # Full configured policy, not just the schema's min_length — otherwise
    # self-service would accept passwords the admin-created path rejects.
    try:
        validators.validate_password_policy(payload.new_password)
    except validators.ValidationError as exc:
        raise validation_error(exc.message, fields={"new_password": "policy"})

    if verify_password(payload.new_password, current_user.hashed_password):
        raise validation_error(
            "كلمة المرور الجديدة مطابقة للحالية / New password matches the current one",
            fields={"new_password": "reused"},
        )

    from auth import change_user_password

    change_user_password(db, current_user, payload.new_password)

    log_audit_event(
        db,
        AuditAction.USER_PASSWORD_CHANGED,
        current_user,
        "User",
        target_ids=current_user.id,
        sensitivity_level=3,
    )
    db.commit()

    return {
        "message_ar": "تم تحديث كلمة المرور بنجاح",
        "message_en": "Password updated successfully",
    }


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------


@router.get("/notification-preferences")
@limiter.limit("30/minute")
def get_my_notification_preferences(
    request: Request,
    current_user: models.User = Depends(get_current_user),
):
    """Return the signed-in user's notification channel toggles."""
    return _read_prefs(current_user)


@router.put("/notification-preferences")
@limiter.limit("10/minute")
def update_my_notification_preferences(
    request: Request,
    payload: MeNotificationPrefsSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the signed-in user's notification channel toggles."""
    before = _read_prefs(current_user)
    after = {"in_app": payload.in_app, "email": payload.email}

    if before == after:
        return {
            "message_ar": "لا توجد تغييرات لحفظها",
            "message_en": "No changes to save",
            "changed": False,
            **after,
        }

    _write_prefs(current_user, after)
    db.commit()

    log_audit_event(
        db,
        AuditAction.USER_NOTIFICATION_PREFS_UPDATED,
        current_user,
        "User",
        target_ids=current_user.id,
        before_state=before,
        after_state=after,
        sensitivity_level=1,
    )
    db.commit()

    return {
        "message_ar": "تم حفظ التفضيلات بنجاح",
        "message_en": "Preferences saved successfully",
        "changed": True,
        **after,
    }
