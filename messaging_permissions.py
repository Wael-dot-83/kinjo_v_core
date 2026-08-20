from typing import Any, List, Optional, Tuple, Set, Union
import enum
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, text

import models
from dependencies import has_role
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


# Use the canonical definition from models.py for consistency
from models import ACTIVE_ENROLLMENT_STATUSES


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
        from services.jordan_locations import governorate_query_aliases
        kg_rows = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate.in_(governorate_query_aliases(governorate_name) or [governorate_name]),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
        scope_ids = [row[0] for row in kg_rows]
        if not scope_ids:
            raise validation_error(
                "لا توجد حضانات نشطة في هذه المحافظة.",
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
        from services.jordan_locations import governorate_query_aliases
        kg_rows = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate.in_(governorate_query_aliases(governorate_trimmed) or [governorate_trimmed]),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()
        scope_ids = [row[0] for row in kg_rows]
        if not scope_ids:
            raise validation_error(
                "لا توجد حضانات نشطة في هذه المحافظة.",
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

        parent_user_ids = [u.id for u in users if u.role == models.UserRole.PARENT]

        # Batch-prefetch parent enrollment sets to avoid N+1 per parent user
        manager_enrolled_parents: set = set()
        if parent_user_ids and current_user.role == models.UserRole.MANAGER:
            manager_enrolled_parents = set(
                row[0] for row in db.query(models.ParentProfile.user_id)
                .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
                .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
                .filter(
                    models.ParentProfile.user_id.in_(parent_user_ids),
                    models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                    models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
                )
                .distinct().all()
            )

        scope_enrolled_parents: set = set()
        if parent_user_ids and kindergarten_ids:
            scope_enrolled_parents = set(
                row[0] for row in db.query(models.ParentProfile.user_id)
                .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
                .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
                .filter(
                    models.ParentProfile.user_id.in_(parent_user_ids),
                    models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids),
                    models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
                )
                .distinct().all()
            )

        for user in users:
            if user.status != models.UserStatus.ACTIVE:
                raise validation_error("Recipient is not active", fields={"recipient_id": "inactive"})
            if current_user.role == models.UserRole.MANAGER:
                if user.role == models.UserRole.SUPERVISOR:
                    if user.kindergarten_id != current_user.kindergarten_id:
                        raise forbidden_error("Managers can only message supervisors in their kindergarten")
                elif user.role == models.UserRole.PARENT:
                    if user.id not in manager_enrolled_parents:
                        raise forbidden_error("Managers can only message parents with active enrollment")
                else:
                    raise forbidden_error("Managers can only message supervisors and parents")
            if kindergarten_ids:
                if user.role == models.UserRole.PARENT:
                    if user.id not in scope_enrolled_parents:
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
        if not has_role(recipient, models.UserRole.MANAGER) or recipient.kindergarten_id != current_user.kindergarten_id:
            raise forbidden_error("Supervisors can only message their kindergarten manager")
        return
    if current_user.role == models.UserRole.PARENT:
        if not has_role(recipient, models.UserRole.MANAGER):
            raise forbidden_error("Parents can only message kindergarten managers")
        if not recipient.kindergarten_id:
            raise forbidden_error("Recipient must belong to a kindergarten")
        if not parent_has_active_enrollment(db, current_user.id, recipient.kindergarten_id):
            raise forbidden_error("You can only message managers of kindergartens where your children are enrolled")
        return
    raise forbidden_error("You do not have permission to send messages")


def _resolve_governorate_filter_values(audience: "AudienceDefinition") -> List[str]:
    """Extract governorate filter values from audience definition (supports both
    legacy governorate_id field and new filters-based approach).

    Each requested governorate is validated and then expanded to every accepted
    stored form (stable key, canonical name, and legacy aliases) so scoping matches
    kindergarten rows regardless of which form the governorate is persisted under —
    e.g. the capital targeted as "العاصمة"/"عمان"/"amman" all match the same rows.
    """
    from services.jordan_locations import governorate_query_aliases

    governorates: List[str] = []

    def _add(raw_value: str, field: str) -> None:
        try:
            canonical = validators.validate_jordan_governorate(str(raw_value))
        except validators.ValidationError:
            raise validation_error("المحافظة غير صالحة", fields={field: "invalid"})
        governorates.extend(governorate_query_aliases(canonical) or [canonical])

    # Legacy field (single governorate string)
    if audience.governorate_id:
        raw = str(audience.governorate_id).strip()
        if raw:
            _add(raw, "governorate_id")

    # Check filters for governorate.EQ / governorate.IN
    for fc in audience.filters or []:
        if fc.field == "kindergarten.governorate":
            op_val = fc.op.value if hasattr(fc.op, "value") else str(fc.op)
            if op_val == "EQ" and fc.value:
                _add(fc.value, "governorate")
            elif op_val == "IN" and isinstance(fc.value, list):
                for v in fc.value:
                    _add(v, "governorate")
    return list(dict.fromkeys(governorates))


def _build_parent_subquery_for_scope(
    db: Session,
    kindergarten_ids: Optional[List[int]] = None,
    governorates: Optional[List[str]] = None,
) -> Any:
    """Build a subquery returning parent user_ids who have active enrollments
    in the given kindergartens or governorates.  Parents relate to kindergartens
    through Child → EnrollmentApplication, NOT through User.kindergarten_id."""
    sq = (
        db.query(models.ParentProfile.user_id)
        .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
        .join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        )
        .filter(models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES))
    )
    if kindergarten_ids:
        sq = sq.filter(models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids))
    if governorates:
        sq = sq.join(
            models.Kindergarten,
            models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id,
        ).filter(models.Kindergarten.governorate.in_(governorates))
    return sq.distinct().scalar_subquery()


def resolve_recipients(db: Session, audience: AudienceDefinition, sender: models.User) -> Set[int]:
    """
    Resolve recipient user IDs based on audience definition.
    Enforces permissions and returns deduplicated set of user IDs.

    Handles parents correctly: parents relate to kindergartens through
    enrollment_applications (not User.kindergarten_id which is always NULL
    for parents).  Staff (MANAGER/SUPERVISOR) relate via User.kindergarten_id.
    """
    import logging as _log
    logger = _log.getLogger(__name__)

    # Reject unknown/ill-shaped advanced filters before any recipient query.
    # A filter that is accepted by the API must never be silently ignored.
    _validate_audience_filters(audience.filters or [])

    # Enforce permissions based on sender role
    _validate_audience_permissions(db, audience, sender)

    scope_value = audience.scope.value if hasattr(audience.scope, "value") else str(audience.scope)

    # Determine requested roles
    include_role_enums: Optional[List[models.UserRole]] = None
    exclude_role_enums: Optional[List[models.UserRole]] = None
    if audience.include_roles:
        include_role_enums = [models.UserRole(role) for role in audience.include_roles]
    elif audience.exclude_roles:
        exclude_role_enums = [models.UserRole(role) for role in audience.exclude_roles]

    # Determine scoping kindergarten_ids and governorates
    scope_kg_ids: Optional[List[int]] = None
    scope_governorates: Optional[List[str]] = None

    if sender.role == models.UserRole.MANAGER:
        # Managers always scoped to their own kindergarten
        scope_kg_ids = [sender.kindergarten_id] if sender.kindergarten_id else None
    elif sender.role == models.UserRole.SUPERVISOR:
        scope_kg_ids = [sender.kindergarten_id] if sender.kindergarten_id else None
    elif sender.role == models.UserRole.ADMIN:
        if scope_value == "KINDERGARTEN" and audience.kindergarten_ids:
            scope_kg_ids = list(audience.kindergarten_ids)
        elif scope_value == "GOVERNORATE":
            scope_governorates = _resolve_governorate_filter_values(audience)
            if not scope_governorates:
                raise validation_error("المحافظة مطلوبة للنطاق الجغرافي", fields={"governorate": "required"})
        # GLOBAL scope => no extra filtering

    # --- Resolve staff (MANAGER / SUPERVISOR) ---
    wants_parent = True
    wants_staff = True
    if include_role_enums is not None:
        wants_parent = models.UserRole.PARENT in include_role_enums
        wants_staff = any(r in include_role_enums for r in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR])
    if exclude_role_enums is not None:
        if models.UserRole.PARENT in exclude_role_enums:
            wants_parent = False

    recipient_ids: Set[int] = set()

    if wants_staff:
        staff_query = db.query(models.User.id).filter(
            models.User.status == models.UserStatus.ACTIVE,
        )
        # Apply role filter for staff
        staff_roles_wanted = [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]
        if include_role_enums is not None:
            staff_roles_wanted = [r for r in include_role_enums if r in {models.UserRole.MANAGER, models.UserRole.SUPERVISOR}]
        if exclude_role_enums is not None:
            staff_roles_wanted = [r for r in staff_roles_wanted if r not in exclude_role_enums]
        if staff_roles_wanted:
            staff_query = staff_query.filter(models.User.role.in_(staff_roles_wanted))
            # Apply kindergarten/governorate scope for staff
            if scope_kg_ids:
                staff_query = staff_query.filter(models.User.kindergarten_id.in_(scope_kg_ids))
            elif scope_governorates:
                staff_query = staff_query.join(
                    models.Kindergarten,
                    models.User.kindergarten_id == models.Kindergarten.id,
                ).filter(models.Kindergarten.governorate.in_(scope_governorates))
            recipient_ids.update(row[0] for row in staff_query.distinct().all())

    if wants_parent:
        parent_query = db.query(models.User.id).filter(
            models.User.status == models.UserStatus.ACTIVE,
            models.User.role == models.UserRole.PARENT,
        )
        # Parents are scoped via enrollments, not User.kindergarten_id
        if scope_kg_ids or scope_governorates:
            parent_subquery = _build_parent_subquery_for_scope(
                db,
                kindergarten_ids=scope_kg_ids,
                governorates=scope_governorates,
            )
            parent_query = parent_query.filter(models.User.id.in_(parent_subquery))
        recipient_ids.update(row[0] for row in parent_query.distinct().all())

    # Add explicitly included users
    if audience.include_user_ids:
        if sender.role == models.UserRole.MANAGER:
            invalid_ids = set(audience.include_user_ids) - recipient_ids
            if invalid_ids:
                raise forbidden_error(
                    "Managers can explicitly include only supervisors and parents in their own kindergarten"
                )
        else:
            recipient_ids.update(audience.include_user_ids)

    # Every accepted custom filter is restrictive, including for explicitly
    # included users. Intersecting per-clause result sets gives deterministic
    # AND semantics shared by preview and send (both call this resolver).
    for filter_clause in audience.filters or []:
        recipient_ids &= _recipient_ids_matching_filter(db, filter_clause)

    # Remove excluded users
    if audience.exclude_user_ids:
        recipient_ids -= set(audience.exclude_user_ids)

    # Remove sender from recipients
    recipient_ids.discard(sender.id)

    # Apply safety cap
    if len(recipient_ids) > settings.MAX_MESSAGE_RECIPIENTS:
        raise validation_error(
            f"عدد المستلمين كبير جداً ({len(recipient_ids)}). الحد الأقصى: {settings.MAX_MESSAGE_RECIPIENTS}",
        )

    logger.info(
        "resolve_recipients: sender=%s role=%s scope=%s resolved=%d recipients",
        sender.id, sender.role.value, scope_value, len(recipient_ids),
    )

    return recipient_ids


def _validate_audience_permissions(db: Session, audience: AudienceDefinition, sender: models.User) -> None:
    """Validate that sender has permission to use this audience definition.

    Rules:
    - Admin: any audience, any scope (GLOBAL / GOVERNORATE / KINDERGARTEN)
    - Manager: audience mode allowed, but ONLY targets SUPERVISOR and PARENT
      roles within their own kindergarten.  Scope must be GLOBAL or KINDERGARTEN
      matching their own KG.
    - Supervisor / Parent: cannot use audience mode (direct messages only).
    """
    scope_value = audience.scope.value if hasattr(audience.scope, "value") else str(audience.scope)

    if sender.role == models.UserRole.ADMIN:
        return  # Admins can use any audience

    if sender.role == models.UserRole.MANAGER:
        if not sender.kindergarten_id:
            raise validation_error(
                "يجب أن يكون المدير مرتبطاً بحضانة لإرسال الرسائل",
                fields={"kindergarten_id": "required"},
            )
        # Managers can only use GLOBAL (auto-scoped to their KG) or KINDERGARTEN
        if scope_value not in [AudienceScope.GLOBAL.value, AudienceScope.KINDERGARTEN.value]:
            raise forbidden_error("المدراء يمكنهم إرسال الرسائل داخل روضتهم فقط")
        # If explicit kindergarten_ids, they must match manager's own KG
        if audience.kindergarten_ids:
            invalid_ids = [kg_id for kg_id in audience.kindergarten_ids if kg_id != sender.kindergarten_id]
            if invalid_ids:
                raise forbidden_error("المدراء يمكنهم إرسال الرسائل داخل روضتهم فقط")
        # Managers can only target SUPERVISOR and PARENT roles
        allowed_manager_target_roles = {models.UserRole.SUPERVISOR, models.UserRole.PARENT}
        if audience.include_roles:
            for role_str in audience.include_roles:
                try:
                    role_enum = models.UserRole(role_str)
                except ValueError:
                    raise validation_error("دور غير صالح", fields={"roles": "invalid"})
                if role_enum not in allowed_manager_target_roles:
                    raise forbidden_error("المدراء يمكنهم مراسلة المشرفين وأولياء الأمور فقط")
        return

    if sender.role in [models.UserRole.SUPERVISOR, models.UserRole.PARENT]:
        raise forbidden_error("يمكنك إرسال رسائل مباشرة فقط")

    raise forbidden_error("ليس لديك صلاحية لإرسال رسائل جماعية")


def _apply_filter_clause(query, filter_clause: FilterClause, sender: models.User):
    """Apply a single filter clause to the query"""
    _validate_filter_clause(filter_clause)
    field = filter_clause.field
    op = _as_filter_operator(filter_clause.op)
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
            query = query.filter(models.user_role_is_not(models.UserRole(value)))
        elif op == FilterOperator.NOT_IN:
            roles = [models.UserRole(r) for r in value]
            query = query.filter(models.User.role.not_in_(roles))
    elif field == "is_active":
        if op == FilterOperator.IS_TRUE:
            query = query.filter(models.User.status == models.UserStatus.ACTIVE)
        elif op == FilterOperator.IS_FALSE:
            query = query.filter(models.User.status != models.UserStatus.ACTIVE)
    else:
        raise validation_error(f"Unsupported filter field: user.{field}")

    return query


def _apply_kindergarten_filter(query, field: str, op: FilterOperator, value):
    """Apply filter on kindergarten table (requires join)"""
    # Join with kindergarten if not already joined
    query = query.outerjoin(models.Kindergarten, models.User.kindergarten_id == models.Kindergarten.id)

    if field == "governorate":
        from services.jordan_locations import governorate_query_aliases
        if op == FilterOperator.EQ:
            validators.validate_jordan_governorate(value)  # reject unknown governorates
            match_values = governorate_query_aliases(value) or [value]
            query = query.filter(models.Kindergarten.governorate.in_(match_values))
        elif op == FilterOperator.IN:
            match_values = []
            for g in value:
                validators.validate_jordan_governorate(g)  # reject unknown governorates
                match_values.extend(governorate_query_aliases(g) or [g])
            query = query.filter(models.Kindergarten.governorate.in_(sorted(set(match_values))))
    elif field == "id":
        if op == FilterOperator.EQ:
            query = query.filter(models.Kindergarten.id == value)
        elif op == FilterOperator.IN:
            query = query.filter(models.Kindergarten.id.in_(value))
    else:
        raise validation_error(f"Unsupported filter field: kindergarten.{field}")

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
                models.Child,
                models.Child.parent_id == models.ParentProfile.id,
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.status == status_enum)
        elif op == FilterOperator.IN:
            statuses = [models.EnrollmentStatus(item) for item in value]
            query = query.join(
                models.ParentProfile,
                models.ParentProfile.user_id == models.User.id,
            ).join(
                models.Child,
                models.Child.parent_id == models.ParentProfile.id,
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id,
            ).filter(models.EnrollmentApplication.status.in_(statuses))
    else:
        raise validation_error(f"Unsupported filter field: enrollment.{field}")

    return query


_SUPPORTED_FILTER_OPERATORS = {
    "user.role": {FilterOperator.EQ, FilterOperator.IN, FilterOperator.NEQ, FilterOperator.NOT_IN},
    "user.is_active": {FilterOperator.IS_TRUE, FilterOperator.IS_FALSE},
    "kindergarten.id": {FilterOperator.EQ, FilterOperator.IN},
    "kindergarten.governorate": {FilterOperator.EQ, FilterOperator.IN},
    "enrollment.status": {FilterOperator.EQ, FilterOperator.IN},
}


def _as_filter_operator(raw: Any) -> FilterOperator:
    try:
        if isinstance(raw, FilterOperator):
            return raw
        raw_value = raw.value if hasattr(raw, "value") else str(raw)
        return FilterOperator(raw_value)
    except ValueError:
        raise validation_error("Unsupported filter operator", fields={"filters": "operator"})


def _as_list(value: Any, *, field: str) -> List[Any]:
    if not isinstance(value, list) or not value:
        raise validation_error("Filter value must be a non-empty list", fields={field: "invalid"})
    return value


def _validate_filter_clause(filter_clause: FilterClause) -> None:
    field = str(filter_clause.field or "").strip()
    allowed = _SUPPORTED_FILTER_OPERATORS.get(field)
    if not allowed:
        raise validation_error(f"Unsupported filter field: {field}", fields={"filters": "field"})
    op = _as_filter_operator(filter_clause.op)
    if op not in allowed:
        raise validation_error(
            f"Unsupported operator {op.value} for {field}",
            fields={field: "operator"},
        )

    value = filter_clause.value
    if op in {FilterOperator.IN, FilterOperator.NOT_IN}:
        values = _as_list(value, field=field)
    elif op in {FilterOperator.IS_TRUE, FilterOperator.IS_FALSE}:
        if value not in (None, True, False):
            raise validation_error("Boolean filter does not accept a value", fields={field: "invalid"})
        values = []
    else:
        if isinstance(value, list) or value is None:
            raise validation_error("Filter value is required", fields={field: "invalid"})
        values = [value]

    try:
        if field == "user.role":
            for item in values:
                models.UserRole(str(item).strip().upper())
        elif field == "kindergarten.id":
            if any(isinstance(item, bool) or int(item) <= 0 for item in values):
                raise ValueError
        elif field == "kindergarten.governorate":
            for item in values:
                validators.validate_jordan_governorate(str(item))
        elif field == "enrollment.status":
            for item in values:
                models.EnrollmentStatus(str(item).strip().upper())
    except (TypeError, ValueError, validators.ValidationError):
        raise validation_error("Invalid filter value", fields={field: "invalid"})


def _validate_audience_filters(filters: List[FilterClause]) -> None:
    for filter_clause in filters:
        _validate_filter_clause(filter_clause)


def _recipient_ids_matching_filter(db: Session, filter_clause: FilterClause) -> Set[int]:
    """Resolve exactly the users matching one validated audience filter."""
    field = str(filter_clause.field).strip()
    op = _as_filter_operator(filter_clause.op)
    value = filter_clause.value

    if field == "user.role":
        scalar = models.UserRole(str(value).strip().upper()) if op in {FilterOperator.EQ, FilterOperator.NEQ} else None
        values = [models.UserRole(str(item).strip().upper()) for item in value] if isinstance(value, list) else []
        query = db.query(models.User.id)
        if op == FilterOperator.EQ:
            query = query.filter(models.User.role == scalar)
        elif op == FilterOperator.NEQ:
            query = query.filter(models.User.role != scalar)
        elif op == FilterOperator.IN:
            query = query.filter(models.User.role.in_(values))
        else:
            query = query.filter(models.User.role.not_in(values))
        return {row[0] for row in query.all()}

    if field == "user.is_active":
        expected = op == FilterOperator.IS_TRUE
        statuses = (
            [models.UserStatus.ACTIVE]
            if expected
            else [status for status in models.UserStatus if status != models.UserStatus.ACTIVE]
        )
        return {
            row[0]
            for row in db.query(models.User.id).filter(models.User.status.in_(statuses)).all()
        }

    if field == "enrollment.status":
        statuses = (
            [models.EnrollmentStatus(str(value).strip().upper())]
            if op == FilterOperator.EQ
            else [models.EnrollmentStatus(str(item).strip().upper()) for item in value]
        )
        query = (
            db.query(models.User.id)
            .join(models.ParentProfile, models.ParentProfile.user_id == models.User.id)
            .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
            .join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id,
            )
            .filter(models.EnrollmentApplication.status.in_(statuses))
        )
        return {row[0] for row in query.distinct().all()}

    if field == "kindergarten.id":
        kindergarten_ids = (
            [int(value)] if op == FilterOperator.EQ else [int(item) for item in value]
        )
        kindergarten_filter = models.Kindergarten.id.in_(kindergarten_ids)
    else:
        from services.jordan_locations import governorate_query_aliases

        raw_values = [value] if op == FilterOperator.EQ else value
        governorates: List[str] = []
        for raw_value in raw_values:
            canonical = validators.validate_jordan_governorate(str(raw_value))
            governorates.extend(governorate_query_aliases(canonical) or [canonical])
        kindergarten_filter = models.Kindergarten.governorate.in_(set(governorates))

    staff_ids = {
        row[0]
        for row in (
            db.query(models.User.id)
            .join(models.Kindergarten, models.User.kindergarten_id == models.Kindergarten.id)
            .filter(kindergarten_filter)
            .distinct()
            .all()
        )
    }
    parent_ids = {
        row[0]
        for row in (
            db.query(models.User.id)
            .join(models.ParentProfile, models.ParentProfile.user_id == models.User.id)
            .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
            .join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id,
            )
            .join(
                models.Kindergarten,
                models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id,
            )
            .filter(
                kindergarten_filter,
                models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
            )
            .distinct()
            .all()
        )
    }
    return staff_ids | parent_ids


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
