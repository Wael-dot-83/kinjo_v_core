from typing import List, Optional, Tuple, Set, Union
import enum
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, text

import models
import validators
from admin_security import forbidden_error, not_found_error, validation_error
from config import settings


class FilterOperator(str, enum.Enum):
    EQ = "EQ"
    IN = "IN"
    NEQ = "NEQ"
    NOT_IN = "NOT_IN"
    LIKE = "LIKE"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"


class AudienceScope(str, enum.Enum):
    GLOBAL = "GLOBAL"
    GOVERNORATE = "GOVERNORATE"
    KINDERGARTEN = "KINDERGARTEN"
    CLASS = "CLASS"
    CUSTOM = "CUSTOM"


class FilterClause:
    def __init__(self, field: str, op: FilterOperator, value: Union[str, int, float, List[Union[str, int, float]], None] = None):
        self.field = field
        self.op = op
        self.value = value


class AudienceDefinition:
    def __init__(
        self,
        include_roles: Optional[List[str]] = None,
        exclude_roles: Optional[List[str]] = None,
        scope: str = "GLOBAL",
        filters: List[FilterClause] = None,
        include_user_ids: Optional[List[int]] = None,
        exclude_user_ids: Optional[List[int]] = None,
        # Legacy fields for backward compatibility
        kindergarten_ids: Optional[List[int]] = None,
        governorate_id: Optional[int] = None
    ):
        self.include_roles = include_roles or []
        self.exclude_roles = exclude_roles or []
        self.scope = scope
        self.filters = filters or []
        self.include_user_ids = include_user_ids or []
        self.exclude_user_ids = exclude_user_ids or []
        # Legacy fields
        self.kindergarten_ids = kindergarten_ids or []
        self.governorate_id = governorate_id


ACTIVE_ENROLLMENT_STATUSES = (
    models.EnrollmentStatus.ACCEPTED,
    models.EnrollmentStatus.ACTIVE
)


def normalize_message_type(message_type: Optional[str]) -> str:
    normalized = (message_type or "").strip().lower()
    if normalized == "broadcast":
        normalized = "announcement"
    if normalized not in {"announcement", "direct"}:
        raise validation_error(
            "Invalid message_type. Must be announcement or direct",
            fields={"message_type": "invalid"}
        )
    return normalized


def normalize_roles(roles: Optional[List[str]]) -> List[models.UserRole]:
    normalized: List[models.UserRole] = []
    for role in roles or []:
        if not role:
            continue
        role_str = str(role).strip().upper()
        if role_str in {"ALL", "ALL_USERS"}:
            normalized.extend([
                models.UserRole.ADMIN,
                models.UserRole.MANAGER,
                models.UserRole.SUPERVISOR,
                models.UserRole.PARENT
            ])
            continue
        try:
            normalized.append(models.UserRole(role_str))
        except ValueError:
            raise validation_error("Invalid role", fields={"roles": "invalid"})
    seen = set()
    deduped: List[models.UserRole] = []
    for role in normalized:
        if role in seen:
            continue
        seen.add(role)
        deduped.append(role)
    return deduped


def ensure_kindergartens_exist(db: Session, kindergarten_ids: List[int]) -> None:
    if not kindergarten_ids:
        return
    found_ids = {
        row[0] for row in db.query(models.Kindergarten.id).filter(
            models.Kindergarten.id.in_(kindergarten_ids)
        ).all()
    }
    missing = set(kindergarten_ids) - found_ids
    if missing:
        raise validation_error(
            "Invalid kindergarten_ids",
            fields={"kindergarten_ids": "not_found"}
        )


def ensure_classes_exist(db: Session, class_ids: List[int]) -> None:
    if not class_ids:
        return
    found_ids = {
        row[0] for row in db.query(models.Class.id).filter(
            models.Class.id.in_(class_ids)
        ).all()
    }
    missing = set(class_ids) - found_ids
    if missing:
        raise validation_error(
            "Invalid class_ids",
            fields={"class_ids": "not_found"}
        )


def resolve_announcement_scope(
    msg_kindergarten_ids: Optional[List[int]],
    msg_kindergarten_id: Optional[int],
    audience_kindergarten_ids: Optional[List[int]],
    current_user: models.User,
    db: Session,
    governorate: Optional[str] = None,
    audience_scope: Optional[str] = None,
    audience_governorate_id: Optional[int] = None
) -> Optional[List[int]]:
    scope_ids: List[int] = []
    if msg_kindergarten_ids:
        scope_ids = list(msg_kindergarten_ids)
    elif msg_kindergarten_id:
        scope_ids = [msg_kindergarten_id]
    elif audience_kindergarten_ids:
        scope_ids = list(audience_kindergarten_ids)
    elif audience_scope == "governorate" and audience_governorate_id and current_user.role == models.UserRole.ADMIN:
        # Get governorate name from ID
        governorate_row = db.query(models.Kindergarten.governorate).filter(
            models.Kindergarten.id == audience_governorate_id
        ).first()
        if not governorate_row:
            raise validation_error("Invalid governorate_id", fields={"governorate_id": "not_found"})
        governorate_name = governorate_row[0]
        try:
            governorate_name = validators.validate_jordan_governorate(governorate_name)
        except validators.ValidationError:
            raise validation_error(
                "المحافظة المختارة غير صالحة.",
                fields={"governorate_id": "invalid"}
            )
        kg_rows = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate == governorate_name,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
        scope_ids = [row[0] for row in kg_rows]
        if not scope_ids:
            raise validation_error(
                "لا توجد روضات نشطة في هذه المحافظة.",
                fields={"governorate_id": "empty"}
            )
    elif audience_scope == "kindergarten" and audience_kindergarten_ids:
        scope_ids = list(audience_kindergarten_ids)
    elif governorate and current_user.role == models.UserRole.ADMIN:
        governorate_trimmed = governorate.strip()
        try:
            governorate_trimmed = validators.validate_jordan_governorate(governorate_trimmed)
        except validators.ValidationError:
            raise validation_error(
                "المحافظة المختارة غير صالحة.",
                fields={"governorate": "invalid"}
            )
        kg_rows = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate == governorate_trimmed,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
        scope_ids = [row[0] for row in kg_rows]
        if not scope_ids:
            raise validation_error(
                "لا توجد روضات نشطة في هذه المحافظة.",
                fields={"governorate": "empty"}
            )
    scope_ids = [int(x) for x in scope_ids if x]
    scope_ids = list(dict.fromkeys(scope_ids))

    if current_user.role == models.UserRole.ADMIN:
        if scope_ids:
            ensure_kindergartens_exist(db, scope_ids)
            return scope_ids
        return None

    if current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            raise validation_error(
                "Manager must be assigned to a kindergarten",
                fields={"kindergarten_id": "required"}
            )
        if scope_ids and scope_ids != [current_user.kindergarten_id]:
            raise forbidden_error("Managers can only send announcements to their own kindergarten")
        return [current_user.kindergarten_id]

    raise forbidden_error("Only admins and managers can send announcements")


def parent_active_kindergarten_ids(db: Session, parent_user_id: int) -> List[int]:
    rows = db.query(models.EnrollmentApplication.kindergarten_id).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id
    ).join(
        models.ParentProfile,
        models.ParentProfile.id == models.Child.parent_id
    ).filter(
        models.ParentProfile.user_id == parent_user_id,
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).distinct().all()
    return [row[0] for row in rows if row and row[0]]


def parent_has_active_enrollment(db: Session, parent_user_id: int, kindergarten_id: int) -> bool:
    return db.query(models.EnrollmentApplication.id).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id
    ).join(
        models.ParentProfile,
        models.ParentProfile.id == models.Child.parent_id
    ).filter(
        models.ParentProfile.user_id == parent_user_id,
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).first() is not None


def parent_has_active_enrollment_in_scope(
    db: Session,
    parent_user_id: int,
    kindergarten_ids: List[int]
) -> bool:
    if not kindergarten_ids:
        return False
    return db.query(models.EnrollmentApplication.id).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id
    ).join(
        models.ParentProfile,
        models.ParentProfile.id == models.Child.parent_id
    ).filter(
        models.ParentProfile.user_id == parent_user_id,
        models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids),
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).first() is not None


def get_manager_for_kindergarten(db: Session, kindergarten_id: int) -> models.User:
    managers = db.query(models.User).filter(
        models.User.role == models.UserRole.MANAGER,
        models.User.kindergarten_id == kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE
    ).all()
    if not managers:
        raise not_found_error("Manager not found for kindergarten")
    if len(managers) > 1:
        raise validation_error("Multiple managers found for kindergarten", fields={"kindergarten_id": "multiple"})
    return managers[0]


def resolve_direct_kindergarten_id(
    current_user: models.User,
    recipient: models.User,
    requested_kindergarten_id: Optional[int]
) -> Optional[int]:
    if requested_kindergarten_id and recipient.kindergarten_id:
        if requested_kindergarten_id != recipient.kindergarten_id:
            raise validation_error(
                "kindergarten_id does not match recipient",
                fields={"kindergarten_id": "invalid"}
            )
        return requested_kindergarten_id
    if requested_kindergarten_id:
        return requested_kindergarten_id
    if recipient.kindergarten_id:
        return recipient.kindergarten_id
    if current_user.kindergarten_id:
        return current_user.kindergarten_id
    return None


def resolve_direct_recipient(
    db: Session,
    current_user: models.User,
    recipient_id: Optional[int],
    kindergarten_id: Optional[int]
) -> Tuple[models.User, Optional[int]]:
    if recipient_id:
        recipient = db.query(models.User).filter(models.User.id == recipient_id).first()
        if not recipient:
            raise not_found_error("Recipient not found")
        target_kindergarten_id = resolve_direct_kindergarten_id(
            current_user,
            recipient,
            kindergarten_id
        )
        return recipient, target_kindergarten_id

    if current_user.role == models.UserRole.PARENT:
        active_kindergartens = parent_active_kindergarten_ids(db, current_user.id)
        if not active_kindergartens:
            raise forbidden_error("Parents can only message managers where they have active enrollments")
        target_kindergarten_id = kindergarten_id
        if target_kindergarten_id is None:
            if len(active_kindergartens) == 1:
                target_kindergarten_id = active_kindergartens[0]
            else:
                raise validation_error(
                    "kindergarten_id is required for parents with multiple enrollments",
                    fields={"kindergarten_id": "required"}
                )
        if target_kindergarten_id not in active_kindergartens:
            raise forbidden_error("Parents can only message managers where they have active enrollments")
        recipient = get_manager_for_kindergarten(db, target_kindergarten_id)
        return recipient, target_kindergarten_id

    if current_user.role == models.UserRole.SUPERVISOR:
        target_kindergarten_id = current_user.kindergarten_id or kindergarten_id
        if not target_kindergarten_id:
            raise validation_error("kindergarten_id is required", fields={"kindergarten_id": "required"})
        if current_user.kindergarten_id and kindergarten_id and kindergarten_id != current_user.kindergarten_id:
            raise forbidden_error("Supervisors can only message their kindergarten manager")
        recipient = get_manager_for_kindergarten(db, target_kindergarten_id)
        return recipient, target_kindergarten_id

    raise validation_error("Recipient required for direct messages", fields={"recipient_id": "required"})


def validate_announcement_permissions(
    db: Session,
    current_user: models.User,
    audience_roles: List[models.UserRole],
    audience_users: List[int],
    audience_class_ids: List[int],
    kindergarten_ids: Optional[List[int]]
) -> None:
    if not audience_roles and not audience_users:
        raise validation_error("Audience is required", fields={"audience": "required"})

    if current_user.role == models.UserRole.MANAGER:
        allowed_roles = {models.UserRole.PARENT, models.UserRole.SUPERVISOR}
        if any(role not in allowed_roles for role in audience_roles):
            raise forbidden_error("Managers can only send announcements to parents and supervisors")

    if audience_class_ids:
        if models.UserRole.PARENT not in audience_roles:
            raise validation_error("class_ids requires PARENT role", fields={"class_ids": "invalid"})
        ensure_classes_exist(db, audience_class_ids)
        if kindergarten_ids:
            class_scope = db.query(models.Class.id).filter(
                models.Class.id.in_(audience_class_ids),
                models.Class.kindergarten_id.in_(kindergarten_ids)
            ).count()
            if class_scope != len(set(audience_class_ids)):
                raise validation_error("class_ids must belong to selected kindergartens", fields={"class_ids": "invalid"})
        if current_user.role == models.UserRole.MANAGER:
            class_scope = db.query(models.Class.id).filter(
                models.Class.id.in_(audience_class_ids),
                models.Class.kindergarten_id == current_user.kindergarten_id
            ).count()
            if class_scope != len(set(audience_class_ids)):
                raise forbidden_error("Managers can only target classes in their kindergarten")

    if audience_users:
        user_ids = list(dict.fromkeys(audience_users))
        users = db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        if len(users) != len(user_ids):
            raise not_found_error("Recipient not found")

        for user in users:
            if user.status != models.UserStatus.ACTIVE:
                raise validation_error("Recipient is not active", fields={"recipient_id": "inactive"})
            if current_user.role == models.UserRole.MANAGER:
                if user.role == models.UserRole.SUPERVISOR:
                    if user.kindergarten_id != current_user.kindergarten_id:
                        raise forbidden_error("Managers can only message supervisors in their kindergarten")
                elif user.role == models.UserRole.PARENT:
                    if not parent_has_active_enrollment(db, user.id, current_user.kindergarten_id):
                        raise forbidden_error("Managers can only message parents with active enrollment")
                else:
                    raise forbidden_error("Managers can only message supervisors and parents")
            if kindergarten_ids:
                if user.role == models.UserRole.PARENT:
                    if not parent_has_active_enrollment_in_scope(db, user.id, kindergarten_ids):
                        raise validation_error("Recipient not in scope", fields={"audience": "scope"})
                elif user.kindergarten_id and user.kindergarten_id not in kindergarten_ids:
                    raise validation_error("Recipient not in scope", fields={"audience": "scope"})


def build_audience_recipients(
    db: Session,
    audience_roles: List[models.UserRole],
    audience_users: List[int],
    audience_class_ids: List[int],
    kindergarten_ids: Optional[List[int]]
) -> List[int]:
    recipient_ids = set()

    if audience_users:
        recipient_ids.update(audience_users)

    class_ids = [int(x) for x in audience_class_ids if x]

    for role in audience_roles:
        if role == models.UserRole.PARENT:
            query = db.query(models.ParentProfile.user_id).join(
                models.Child,
                models.Child.parent_id == models.ParentProfile.id
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).join(
                models.User,
                models.User.id == models.ParentProfile.user_id
            ).filter(
                models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
                models.User.status == models.UserStatus.ACTIVE
            )
            if kindergarten_ids:
                query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids))
            if class_ids:
                query = query.filter(models.EnrollmentApplication.class_id.in_(class_ids))
            recipient_ids.update(row[0] for row in query.distinct().all())
            continue

        query = db.query(models.User.id).filter(
            models.User.role == role,
            models.User.status == models.UserStatus.ACTIVE
        )
        if kindergarten_ids:
            query = query.filter(models.User.kindergarten_id.in_(kindergarten_ids))
        recipient_ids.update(row[0] for row in query.all())

    return list(recipient_ids)


def validate_direct_permissions(
    db: Session,
    current_user: models.User,
    recipient: models.User
) -> None:
    if current_user.role == models.UserRole.ADMIN:
        return
    if current_user.role == models.UserRole.MANAGER:
        if recipient.role == models.UserRole.MANAGER:
            if not settings.MANAGER_TO_MANAGER_ENABLED:
                raise forbidden_error("Managers cannot message other managers")
            if settings.MANAGER_TO_MANAGER_SCOPE == "same_kg":
                if recipient.kindergarten_id != current_user.kindergarten_id:
                    raise forbidden_error("Managers can only message managers in their kindergarten")
            return
        if recipient.role == models.UserRole.SUPERVISOR:
            if recipient.kindergarten_id != current_user.kindergarten_id:
                raise forbidden_error("Managers can only message supervisors in their kindergarten")
            return
        if recipient.role == models.UserRole.PARENT:
            if not parent_has_active_enrollment(db, recipient.id, current_user.kindergarten_id):
                raise forbidden_error("Managers can only message parents with active enrollment")
            return
        raise forbidden_error("Managers can only message supervisors and parents")
    if current_user.role == models.UserRole.SUPERVISOR:
        if recipient.role != models.UserRole.MANAGER or recipient.kindergarten_id != current_user.kindergarten_id:
            raise forbidden_error("Supervisors can only message their kindergarten manager")
        return
    if current_user.role == models.UserRole.PARENT:
        if recipient.role != models.UserRole.MANAGER:
            raise forbidden_error("Parents can only message kindergarten managers")
        if not recipient.kindergarten_id:
            raise forbidden_error("Recipient must belong to a kindergarten")
        if not parent_has_active_enrollment(db, current_user.id, recipient.kindergarten_id):
            raise forbidden_error("You can only message managers of kindergartens where your children are enrolled")
        return
    raise forbidden_error("You do not have permission to send messages")


def resolve_recipients(db: Session, audience: AudienceDefinition, sender: models.User) -> Set[int]:
    """
    Resolve recipient user IDs based on audience definition.
    Enforces permissions and returns deduplicated set of user IDs.
    """
    # Enforce permissions based on sender role
    _validate_audience_permissions(db, audience, sender)

    # Start with base query for active users
    query = db.query(models.User.id).filter(models.User.status == models.UserStatus.ACTIVE)

    scope_value = audience.scope.value if hasattr(audience.scope, "value") else str(audience.scope)

    # Apply role filters
    if audience.include_roles:
        include_role_enums = [models.UserRole(role) for role in audience.include_roles]
        query = query.filter(models.User.role.in_(include_role_enums))
    elif audience.exclude_roles:
        exclude_role_enums = [models.UserRole(role) for role in audience.exclude_roles]
        query = query.filter(models.User.role.not_in_(exclude_role_enums))

    # Apply scope restrictions
    if sender.role == models.UserRole.MANAGER:
        # Managers can only target their own kindergarten (parents via enrollments)
        manager_kindergarten_id = sender.kindergarten_id
        if manager_kindergarten_id:
            parent_enrollment_subquery = (
                db.query(models.ParentProfile.user_id)
                .join(
                    models.Child,
                    models.Child.parent_id == models.ParentProfile.id
                )
                .join(
                    models.EnrollmentApplication,
                    models.EnrollmentApplication.child_id == models.Child.id
                )
                .filter(
                    models.EnrollmentApplication.kindergarten_id == manager_kindergarten_id,
                    models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
                )
                .distinct()
                .subquery()
            )
            query = query.filter(or_(
                and_(
                    models.User.role == models.UserRole.PARENT,
                    models.User.id.in_(parent_enrollment_subquery)
                ),
                and_(
                    models.User.role != models.UserRole.PARENT,
                    models.User.kindergarten_id == manager_kindergarten_id
                )
            ))
        else:
            query = query.filter(models.User.kindergarten_id == sender.kindergarten_id)
    elif sender.role == models.UserRole.SUPERVISOR:
        # Supervisors can only target their own kindergarten
        query = query.filter(models.User.kindergarten_id == sender.kindergarten_id)

    # Apply audience scope filters
    if scope_value == "GOVERNORATE" and audience.governorate_id:
        # Filter by specific governorate
        query = query.join(models.Kindergarten, models.User.kindergarten_id == models.Kindergarten.id)
        query = query.filter(models.Kindergarten.governorate == audience.governorate_id)
    elif scope_value == "KINDERGARTEN" and audience.kindergarten_ids:
        # Filter by specific kindergartens
        query = query.filter(models.User.kindergarten_id.in_(audience.kindergarten_ids))
    elif scope_value == "CLASS":
        # For class scope, we need to filter users who have children in specific classes
        # This is complex and would require joining through parent profiles and enrollments
        # For now, we'll skip this and rely on custom filters
        pass

    # Apply custom filters
    for filter_clause in audience.filters:
        query = _apply_filter_clause(query, filter_clause, sender)

    # Get base recipient IDs
    recipient_ids = set(row[0] for row in query.all())

    # Add explicitly included users
    if audience.include_user_ids:
        recipient_ids.update(audience.include_user_ids)

    # Remove excluded users
    if audience.exclude_user_ids:
        recipient_ids -= set(audience.exclude_user_ids)

    # Remove sender from recipients
    recipient_ids.discard(sender.id)

    # Apply safety cap
    if len(recipient_ids) > settings.MAX_MESSAGE_RECIPIENTS:
        raise validation_error(f"Too many recipients ({len(recipient_ids)}). Maximum allowed: {settings.MAX_MESSAGE_RECIPIENTS}")

    return recipient_ids


def _validate_audience_permissions(db: Session, audience: AudienceDefinition, sender: models.User) -> None:
    """Validate that sender has permission to use this audience definition"""
    scope_value = audience.scope.value if hasattr(audience.scope, "value") else str(audience.scope)
    if sender.role == models.UserRole.ADMIN:
        # Admins can use any audience
        return

    if sender.role == models.UserRole.MANAGER:
        # Managers can only target their own kindergarten
        if scope_value not in [AudienceScope.GLOBAL.value, AudienceScope.KINDERGARTEN.value]:
            raise forbidden_error("Managers can only send messages within their kindergarten")
        if audience.kindergarten_ids:
            if not sender.kindergarten_id:
                raise validation_error("Manager must be assigned to a kindergarten", fields={"kindergarten_id": "required"})
            invalid_ids = [kg_id for kg_id in audience.kindergarten_ids if kg_id != sender.kindergarten_id]
            if invalid_ids:
                raise forbidden_error("Managers can only send messages within their kindergarten")
        # Additional validation will be done in resolve_recipients
        return

    if sender.role in [models.UserRole.SUPERVISOR, models.UserRole.PARENT]:
        # These roles can only send direct messages, not audience messages
        raise forbidden_error("You can only send direct messages")

    raise forbidden_error("Invalid sender role for audience messaging")


def _apply_filter_clause(query, filter_clause: FilterClause, sender: models.User):
    """Apply a single filter clause to the query"""
    field = filter_clause.field
    op = filter_clause.op
    value = filter_clause.value

    # Handle different field types
    if field.startswith("user."):
        return _apply_user_filter(query, field[5:], op, value)
    elif field.startswith("kindergarten."):
        return _apply_kindergarten_filter(query, field[13:], op, value)
    elif field.startswith("enrollment."):
        return _apply_enrollment_filter(query, field[11:], op, value)
    else:
        raise validation_error(f"Unsupported filter field: {field}")


def _apply_user_filter(query, field: str, op: FilterOperator, value):
    """Apply filter on user table"""
    if field == "role":
        if op == FilterOperator.EQ:
            query = query.filter(models.User.role == models.UserRole(value))
        elif op == FilterOperator.IN:
            roles = [models.UserRole(r) for r in value]
            query = query.filter(models.User.role.in_(roles))
        elif op == FilterOperator.NEQ:
            query = query.filter(models.User.role != models.UserRole(value))
        elif op == FilterOperator.NOT_IN:
            roles = [models.UserRole(r) for r in value]
            query = query.filter(models.User.role.not_in_(roles))
    elif field == "is_active":
        if op == FilterOperator.IS_TRUE:
            query = query.filter(models.User.status == models.UserStatus.ACTIVE)
        elif op == FilterOperator.IS_FALSE:
            query = query.filter(models.User.status != models.UserStatus.ACTIVE)
    # Add more user field filters as needed

    return query


def _apply_kindergarten_filter(query, field: str, op: FilterOperator, value):
    """Apply filter on kindergarten table (requires join)"""
    # Join with kindergarten if not already joined
    query = query.outerjoin(models.Kindergarten, models.User.kindergarten_id == models.Kindergarten.id)

    if field == "governorate":
        if op == FilterOperator.EQ:
            normalized_gov = validators.validate_jordan_governorate(value)
            query = query.filter(models.Kindergarten.governorate == normalized_gov)
        elif op == FilterOperator.IN:
            normalized_govs = [validators.validate_jordan_governorate(g) for g in value]
            query = query.filter(models.Kindergarten.governorate.in_(normalized_govs))
    elif field == "id":
        if op == FilterOperator.EQ:
            query = query.filter(models.Kindergarten.id == value)
        elif op == FilterOperator.IN:
            query = query.filter(models.Kindergarten.id.in_(value))

    return query


def _apply_enrollment_filter(query, field: str, op: FilterOperator, value):
    """Apply filter on enrollment table (requires join)"""
    # This is complex - for now, we'll handle basic enrollment status
    if field == "status":
        # For enrollment status, we need to join through parent profiles and enrollments
        # This is a simplified implementation
        if op == FilterOperator.EQ:
            status_enum = models.EnrollmentStatus(value)
            query = query.join(
                models.ParentProfile,
                models.ParentProfile.user_id == models.User.id
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.ParentProfile.id
            ).filter(models.EnrollmentApplication.status == status_enum)

    return query


def get_audience_options(db: Session, current_user: models.User) -> dict:
    """
    Get available options for building audience filters based on user permissions.
    Returns roles, governorates, kindergartens, and classes that the user can target.
    """
    options = {
        "roles": [],
        "governorates": [],
        "kindergartens": [],
        "classes": []
    }

    # Role options - all users can see available roles
    role_options = [
        {"value": "ADMIN", "label": "Admins"},
        {"value": "MANAGER", "label": "Managers"},
        {"value": "SUPERVISOR", "label": "Teachers"},
        {"value": "PARENT", "label": "Parents"}
    ]
    options["roles"] = role_options

    # Governorate options - get unique governorates from kindergartens
    governorates_query = db.query(models.Kindergarten.governorate).distinct()
    if current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        # Non-admins can only see their own governorate
        governorates_query = governorates_query.filter(models.Kindergarten.id == current_user.kindergarten_id)

    governorates = [row[0] for row in governorates_query.all() if row[0]]
    options["governorates"] = sorted(list(set(governorates)))

    # Kindergarten options
    kindergartens_query = db.query(
        models.Kindergarten.id,
        models.Kindergarten.name_ar,
        models.Kindergarten.governorate
    ).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)

    if current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        # Non-admins can only see their own kindergarten
        kindergartens_query = kindergartens_query.filter(models.Kindergarten.id == current_user.kindergarten_id)

    kindergartens = [
        {"id": row[0], "name": row[1], "governorate": row[2]}
        for row in kindergartens_query.all()
    ]
    options["kindergartens"] = kindergartens

    # Class options
    classes_query = db.query(
        models.Class.id,
        models.Class.name_ar,
        models.Class.kindergarten_id,
        models.Kindergarten.name_ar.label("kindergarten_name")
    ).join(
        models.Kindergarten,
        models.Class.kindergarten_id == models.Kindergarten.id
    ).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)

    if current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        # Non-admins can only see classes in their own kindergarten
        classes_query = classes_query.filter(models.Class.kindergarten_id == current_user.kindergarten_id)

    classes = [
        {
            "id": row[0],
            "name": row[1],
            "kindergarten_id": row[2],
            "kindergarten_name": row[3]
        }
        for row in classes_query.all()
    ]
    options["classes"] = classes

    return options
