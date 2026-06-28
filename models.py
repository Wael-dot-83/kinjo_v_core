"""
SQLAlchemy ORM Models for KInJo Kindergarten Management Platform
"""
import enum
import uuid
from enum import Enum as PyEnum
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Float, Date, DateTime,
    ForeignKey, Enum, CheckConstraint, UniqueConstraint, Index, JSON,
    ForeignKeyConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, validates
from sqlalchemy.sql import func
from database import Base

# =============================================================================
# Analytics & Reporting Enums (must be defined before models that use them)
# =============================================================================

class AnalyticsDimensionType(str, PyEnum):
    """Dimension types for analytics aggregation"""
    NETWORK = "NETWORK"
    GOVERNORATE = "GOVERNORATE"
    KINDERGARTEN = "KINDERGARTEN"
    CLASS = "CLASS"
    CHILD = "CHILD"
    CITY = "CITY"
    AREA = "AREA"
    STAFF = "STAFF"
    PARENT = "PARENT"

class AnalyticsPeriodType(str, PyEnum):
    """Period types for analytics aggregation"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"

class ExportStatus(str, PyEnum):
    """Export job status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Enums
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    SUPERVISOR = "SUPERVISOR"
    PARENT = "PARENT"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class KindergartenStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class EnrollmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    WAITLISTED = "WAITLISTED"
    ACTIVE = "ACTIVE"


# Active enrollment statuses for cross-kindergarten exclusivity.
# DRAFT is intentionally excluded.
ACTIVE_ENROLLMENT_STATUSES = {
    EnrollmentStatus.SUBMITTED,
    EnrollmentStatus.PENDING_REVIEW,
    EnrollmentStatus.ACCEPTED,
    EnrollmentStatus.ACTIVE,
}


def is_active_enrollment_status(status_value) -> bool:
    """Return True when the status should be treated as active."""
    if status_value is None:
        return False
    if isinstance(status_value, EnrollmentStatus):
        return status_value in ACTIVE_ENROLLMENT_STATUSES
    try:
        return EnrollmentStatus(status_value) in ACTIVE_ENROLLMENT_STATUSES
    except (ValueError, TypeError, AttributeError):
        return False


class WaitlistStatus(str, enum.Enum):
    WAITLISTED = "WAITLISTED"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class AttendanceMethod(str, enum.Enum):
    PIN = "PIN"
    QR = "QR"
    KIOSK = "KIOSK"
    MANUAL = "MANUAL"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"  # Future
    EXCUSED = "EXCUSED"  # Future


class DailyReportStatus(str, enum.Enum):
    DRAFT = "DRAFT"                           # Created/edited by supervisor, not yet submitted
    SUBMITTED = "SUBMITTED"                   # Submitted to manager, awaiting review
    APPROVED = "APPROVED"                     # Manager approved (internal state)
    SENT_TO_PARENT = "SENT_TO_PARENT"         # Final report sent to parent
    REJECTED = "REJECTED"                     # Manager rejected, returned to supervisor
    RETURNED = "RETURNED"                     # Alias for backward compatibility


class DailyChecklistStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    NOT_REQUIRED = "NOT_REQUIRED"


class IncidentType(str, enum.Enum):
    INJURY = "INJURY"
    BEHAVIOR = "BEHAVIOR"
    BEHAVIORAL = "BEHAVIORAL"
    ILLNESS = "ILLNESS"
    ACCIDENT = "ACCIDENT"
    HEALTH = "HEALTH"
    OTHER = "OTHER"


class SeverityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReportType(str, enum.Enum):
    INCIDENT_SUMMARY = "INCIDENT_SUMMARY"
    ATTENDANCE_SUMMARY = "ATTENDANCE_SUMMARY"
    COMPLIANCE_REPORT = "COMPLIANCE_REPORT"


class ReportScopeType(str, enum.Enum):
    KINDERGARTEN = "KINDERGARTEN"
    GOVERNORATE = "GOVERNORATE"
    ALL = "ALL"


class AlertStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertOperator(str, enum.Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"


class ActionPlanStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class LearningDomain(str, enum.Enum):
    SOCIAL_EMOTIONAL = "SOCIAL_EMOTIONAL"
    PHYSICAL = "PHYSICAL"
    COGNITIVE = "COGNITIVE"
    LANGUAGE = "LANGUAGE"


class MasteryLevel(str, enum.Enum):
    ON_TRACK = "ON_TRACK"
    NEEDS_SUPPORT = "NEEDS_SUPPORT"
    EXCEEDS = "EXCEEDS"


class PortfolioStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class MessageThreadType(str, enum.Enum):
    DIRECT = "DIRECT"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    CLASS = "CLASS"
    BROADCAST = "BROADCAST"


class MessageQueueStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    IN_APP = "IN_APP"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class DevicePlatform(str, enum.Enum):
    IOS = "IOS"
    ANDROID = "ANDROID"
    WEB = "WEB"


class EventType(str, enum.Enum):
    TRIP = "TRIP"
    MEETING = "MEETING"
    HOLIDAY = "HOLIDAY"
    CELEBRATION = "CELEBRATION"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


# Models
class Kindergarten(Base):
    __tablename__ = "kindergartens"

    id = Column(Integer, primary_key=True, index=True)
    name_ar = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=True)
    governorate = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    area = Column(String(100), nullable=False)
    address_line = Column(Text, nullable=False)
    contact_phone = Column(String(20), nullable=False)
    contact_email = Column(String(255), nullable=True)  # Made optional
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(Enum(KindergartenStatus), nullable=False, default=KindergartenStatus.DRAFT)
    operating_hours_start = Column(String(5), nullable=True)
    operating_hours_end = Column(String(5), nullable=True)
    license_number = Column(String(100), nullable=True)
    license_valid_until = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("license_number", name="uq_kindergartens_license_number"),
        Index("idx_kindergartens_governorate", "governorate"),
        Index("idx_kindergartens_governorate_city", "governorate", "city"),
        Index("idx_kindergartens_status", "status"),
        Index("idx_kindergartens_latitude", "latitude"),
        Index("idx_kindergartens_longitude", "longitude"),
    )

    # Relationships
    users = relationship("User", back_populates="kindergarten")
    classes = relationship("Class", back_populates="kindergarten", overlaps="classes")
    services = relationship("KindergartenService", back_populates="kindergarten")
    calendar = relationship("OperatingCalendar", back_populates="kindergarten")
    enrollments = relationship("EnrollmentApplication", back_populates="kindergarten")
    incidents = relationship("Incident", back_populates="kindergarten")
    events = relationship("Event", back_populates="kindergarten")
    messages = relationship("Message", back_populates="kindergarten")
    surveys = relationship("Survey", back_populates="kindergarten")
    supervisor_profiles = relationship("SupervisorProfile", back_populates="kindergarten")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Opaque, globally-unique public identifier — for any future public-facing
    # URL/API surface that should not expose the sequential internal id
    # (GWS S.5.10-026). Internal numeric id is still the FK/PK everywhere else.
    public_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    # Profile fields (manager/supervisor)
    full_name = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    nationality = Column(String(100), nullable=True)
    national_id = Column(String(50), nullable=True)
    passport_number = Column(String(50), nullable=True)
    # IAM hardening columns
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False, server_default="0")
    mfa_secret = Column(String(255), nullable=True)
    totp_secret = Column(String(255), nullable=True)
    mfa_enrolled_at = Column(DateTime(timezone=True), nullable=True)
    mfa_last_verified_at = Column(DateTime(timezone=True), nullable=True)
    notification_preferences = Column(JSON, nullable=True)
    preferred_language = Column(String(10), nullable=False, default="ar", server_default="ar")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="users")
    parent_profile = relationship("ParentProfile", foreign_keys="[ParentProfile.user_id]", back_populates="user", uselist=False)
    supervisor_assignments = relationship("SupervisorAssignment", foreign_keys="[SupervisorAssignment.supervisor_id]", back_populates="supervisor")
    supervisor_profile = relationship("SupervisorProfile", back_populates="user", uselist=False)
    daily_reports_submitted = relationship("DailyReport", foreign_keys="DailyReport.submitted_by", back_populates="submitter")
    daily_reports_approved = relationship("DailyReport", foreign_keys="DailyReport.approved_by", back_populates="approver")
    observations = relationship("Observation", back_populates="observer")
    messages_sent = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    messages_received = relationship("Message", foreign_keys="Message.recipient_id", back_populates="recipient")
    message_states = relationship("MessageUserState", back_populates="user")
    dashboard_preferences = relationship("UserDashboardPreference", back_populates="user", uselist=False)
    filter_preferences = relationship("UserFilterPreference", back_populates="user", uselist=False)

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(role != 'MANAGER') OR (kindergarten_id IS NOT NULL)",
            name="manager_must_have_kindergarten"
        ),
        Index("ix_users_role", "role"),
        Index("ix_users_status", "status"),
        Index("ix_users_kindergarten_id", "kindergarten_id"),
        Index("ix_users_role_status", "role", "status"),
    )


class UserDashboardPreference(Base):
    """User dashboard widget preferences"""
    __tablename__ = "user_dashboard_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    widget_config = Column(JSON, nullable=True)  # JSON array of widget configurations
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="dashboard_preferences")

    __table_args__ = (
        Index("idx_user_dashboard_preferences_user_id", "user_id"),
    )


class UserFilterPreference(Base):
    """User filter preferences for dashboard"""
    __tablename__ = "user_filter_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    filter_config = Column(JSON, nullable=True)  # JSON object of filter configurations
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="filter_preferences")

    __table_args__ = (
        Index("idx_user_filter_preferences_user_id", "user_id"),
    )


class SupervisorProfile(Base):
    __tablename__ = "supervisor_profiles"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="supervisor_profile")
    kindergarten = relationship("Kindergarten", back_populates="supervisor_profiles")
    classes = relationship("Class", back_populates="supervisor", overlaps="classes,kindergarten")

    __table_args__ = (
        UniqueConstraint("user_id", "kindergarten_id", name="uq_supervisor_profiles_user_kindergarten"),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_password_reset_tokens_used", "used"),
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )

    # Relationships
    user = relationship("User", backref="password_reset_tokens")


class ParentProfile(Base):
    __tablename__ = "parent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    second_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=False)
    first_name_en = Column(String(100), nullable=True)
    last_name_en = Column(String(100), nullable=True)
    phone_number = Column(String(20), nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    nationality = Column(String(100), nullable=False)
    national_id = Column(String(50), nullable=True)
    passport_number = Column(String(50), nullable=True)
    home_governorate = Column(String(100), nullable=False)
    home_city = Column(String(100), nullable=False)
    home_area = Column(String(100), nullable=False)
    home_address_line = Column(Text, nullable=False)
    work_address = Column(Text, nullable=True)
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    emergency_contact_relationship = Column(String(100), nullable=True)  # e.g. uncle, grandmother
    relationship_to_child = Column(String(100), nullable=True)  # father, mother, guardian
    parent_type = Column(String(20), nullable=True)  # FATHER, MOTHER, OTHER — structured enum for UI
    correspondence_preference = Column(Boolean, nullable=False, default=True)
    notification_language = Column(String(10), nullable=False, server_default="ar", default="ar")
    profile_complete = Column(Boolean, nullable=False, default=False)
    profile_completed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("uq_parent_profiles_national_id", "national_id", unique=True),
        Index("ix_parent_profiles_phone_number", "phone_number"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="parent_profile")
    children = relationship("Child", back_populates="parent")


class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, index=True)
    # Opaque, globally-unique public identifier — see User.public_id docstring.
    public_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    parent_id = Column(Integer, ForeignKey("parent_profiles.id"), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    father_name = Column(String(255), nullable=False)
    mother_first_name = Column(String(100), nullable=False)
    mother_second_name = Column(String(100), nullable=True)
    mother_last_name = Column(String(100), nullable=False)
    mother_nationality = Column(String(100), nullable=False)
    mother_national_id = Column(String(50), nullable=True)
    mother_passport_number = Column(String(50), nullable=True)
    media_consent = Column(Boolean, nullable=False, default=False)
    correspondence_flag = Column(Boolean, nullable=False, default=False)  # Explicit opt-in required
    profile_complete = Column(Boolean, nullable=False, default=False)
    profile_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("date_of_birth <= CURRENT_DATE", name="ck_children_dob_not_future"),
        UniqueConstraint("parent_id", "first_name", "last_name", "date_of_birth", name="uq_children_parent_name_dob"),
        Index("idx_child_dob", "date_of_birth"),
        Index("idx_child_parent_id", "parent_id"),
    )

    # Additional child fields
    second_name = Column(String(100), nullable=True)  # Must match parent's
    nationality = Column(String(100), nullable=True)
    national_id = Column(String(50), nullable=True)  # Conditional: if Jordanian
    passport_number = Column(String(50), nullable=True)  # Conditional: non-Jordanian
    photo_url = Column(String(500), nullable=True)  # Uploaded photo path
    photo_metadata = Column(JSON, nullable=True)  # {filename, content_type, size, uploaded_at}
    health_notes = Column(Text, nullable=True)  # Allergies, medications, conditions
    educational_notes = Column(Text, nullable=True)  # Learning notes / special needs
    has_special_needs = Column(Boolean, nullable=False, server_default="false", default=False)
    has_medical_condition = Column(Boolean, nullable=False, server_default="false", default=False)
    medical_notes = Column(Text, nullable=True)
    allergy_notes = Column(Text, nullable=True)
    special_needs_notes = Column(Text, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    blood_type = Column(String(5), nullable=True)
    vaccination_up_to_date = Column(Boolean, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Corresponding guardian (secondary contact who may pick up / be contacted for the child)
    corresponding_type = Column(String(20), nullable=True)  # PENDING_MANAGER, GUARDIAN
    corresponding_phone = Column(String(20), nullable=True)
    corresponding_pending_reason = Column(String(255), nullable=True)

    # Relationships
    parent = relationship("ParentProfile", back_populates="children")
    enrollments = relationship("EnrollmentApplication", back_populates="child")
    attendance_logs = relationship("AttendanceLog", back_populates="child")
    daily_reports = relationship("DailyReport", back_populates="child")
    incidents = relationship("Incident", back_populates="child")
    observations = relationship("Observation", back_populates="child")
    portfolios = relationship("Portfolio", back_populates="child")
    health_alerts = relationship("HealthAlert", back_populates="child")
    documents = relationship("ChildDocument", back_populates="child", cascade="all, delete-orphan")


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    name_ar = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=True)
    class_code = Column(String(32), nullable=False, unique=True)  # Human-friendly unique code
    age_group = Column(Enum('AGE_0_1', 'AGE_1_2', 'AGE_2_4', name='age_group_enum'), nullable=False)
    enrolled_children_count = Column(Integer, nullable=False, default=0)
    capacity_total = Column(Integer, nullable=False)
    min_age_months = Column(Integer, nullable=False)
    max_age_months = Column(Integer, nullable=False)
    supervisor_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("supervisor_id", name="uq_classes_supervisor"),
        ForeignKeyConstraint(
            ["supervisor_id", "kindergarten_id"],
            ["supervisor_profiles.user_id", "supervisor_profiles.kindergarten_id"],
            name="fk_classes_supervisor_profile"
        ),
        Index("idx_classes_kindergarten_id", "kindergarten_id"),
        Index("idx_classes_is_active", "is_active"),
    )

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="classes", overlaps="classes")
    supervisor_assignments = relationship("SupervisorAssignment", back_populates="class_")
    enrollments = relationship("EnrollmentApplication", back_populates="class_")
    supervisor = relationship("SupervisorProfile", back_populates="classes", overlaps="classes,kindergarten")


class SupervisorAssignment(Base):
    __tablename__ = "supervisor_assignments"

    id = Column(Integer, primary_key=True, index=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    full_time_dedication = Column(Boolean, nullable=False, default=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    class_ = relationship("Class", back_populates="supervisor_assignments")
    supervisor = relationship("User", foreign_keys=[supervisor_id], back_populates="supervisor_assignments")


class KindergartenService(Base):
    __tablename__ = "kindergarten_services"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    service_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    enabled_flag = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="services")


class OperatingCalendar(Base):
    __tablename__ = "operating_calendar"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    date = Column(Date, nullable=False)
    is_open = Column(Boolean, nullable=False, default=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="calendar")


class EnrollmentApplication(Base):
    __tablename__ = "enrollment_applications"

    id = Column(Integer, primary_key=True, index=True)
    # Opaque, globally-unique public identifier — see User.public_id docstring.
    public_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    status = Column(Enum(EnrollmentStatus), nullable=False, default=EnrollmentStatus.DRAFT)
    # True only for active-like statuses; None for inactive (allows multiple inactive rows per child).
    is_active = Column(Boolean, nullable=True)
    status_reason = Column(String(255), nullable=True)
    source = Column(String(50), nullable=False, default="WEB")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    decision_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
    enrollment_start_date = Column(Date, nullable=True)
    enrollment_end_date = Column(Date, nullable=True)
    class_assignment_date = Column(Date, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        # Prevent duplicate enrollments for same child + kindergarten.
        UniqueConstraint("child_id", "kindergarten_id", name="uq_enrollment_child_kindergarten"),
        # Enforce a single active enrollment per child (NULLs allowed for inactive).
        Index("uq_enrollment_child_active", "child_id", "is_active", unique=True),
        Index("ix_enrollment_child_id", "child_id"),
        Index("ix_enrollment_child_status", "child_id", "status"),
        Index("ix_enrollment_kg_status", "kindergarten_id", "status"),
        Index("ix_enrollment_status", "status"),
        Index("ix_enrollment_source", "source"),
        Index("ix_enrollment_decision_by", "decision_by"),
        Index("ix_enrollment_submitted_at", "submitted_at"),
        Index("ix_enrollment_decision_at", "decision_at"),
    )

    # Relationships
    child = relationship("Child", back_populates="enrollments")
    kindergarten = relationship("Kindergarten", back_populates="enrollments")
    class_ = relationship("Class", back_populates="enrollments")
    waitlist_entry = relationship("WaitlistEntry", back_populates="enrollment", uselist=False)

    @validates("status")
    def _sync_is_active(self, key, value):
        self.is_active = True if is_active_enrollment_status(value) else None
        return value


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("enrollment_applications.id"), unique=True, nullable=False)
    status = Column(Enum(WaitlistStatus), nullable=False, default=WaitlistStatus.WAITLISTED)
    priority_score = Column(Float, nullable=False, default=0.0)
    offer_sent_at = Column(DateTime(timezone=True), nullable=True)
    offer_expiry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    enrollment = relationship("EnrollmentApplication", back_populates="waitlist_entry")


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Enum(AttendanceStatus), nullable=False)
    check_in_at = Column(DateTime(timezone=True), nullable=True)
    check_out_at = Column(DateTime(timezone=True), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    picked_by_name = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("child_id", "date", name="uq_attendance_child_date"),
        CheckConstraint(
            "(check_out_at IS NULL) OR (check_in_at IS NULL) OR (check_out_at >= check_in_at)",
            name="ck_attendance_checkout_after_checkin"
        ),
        Index("ix_attendance_date", "date"),
        Index("ix_attendance_class_id", "class_id"),
        Index("ix_attendance_class_date", "class_id", "date"),
        Index("ix_attendance_recorded_by", "recorded_by"),
        Index("ix_attendance_child_date_status", "child_id", "date", "status"),
    )

    # Relationships
    child = relationship("Child", back_populates="attendance_logs")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Enum(DailyReportStatus), nullable=False, default=DailyReportStatus.DRAFT)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    sent_to_parent_at = Column(DateTime(timezone=True), nullable=True)
    rejected_reason = Column(Text, nullable=True)
    arrival_time = Column(String(5), nullable=False)
    leave_time = Column(String(5), nullable=True)
    # Mood and health
    mood = Column(String(20), nullable=True)  # happy, normal, sad, tired, sick
    health_notes = Column(Text, nullable=True)
    # Meals
    breakfast = Column(Boolean, nullable=True)
    snack = Column(Boolean, nullable=True)
    milk = Column(Boolean, nullable=True)
    lunch = Column(Boolean, nullable=True)
    # Sleep
    nap_start = Column(String(5), nullable=True)
    nap_end = Column(String(5), nullable=True)
    nap_duration_minutes = Column(Integer, nullable=True)
    # Bathroom/Diaper
    bathroom_count = Column(Integer, nullable=True, default=0)
    diaper_wet = Column(Boolean, nullable=True, default=False)
    diaper_soiled = Column(Boolean, nullable=True, default=False)
    # Activities and notes
    activities = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("kindergarten_id", "child_id", "date", name="uq_daily_report_kindergarten_child_date"),
        Index("ix_daily_reports_child_date", "child_id", "date"),
        Index("ix_daily_reports_kg_date_status", "kindergarten_id", "date", "status"),
    )

    # Relationships
    child = relationship("Child", back_populates="daily_reports")
    submitter = relationship("User", foreign_keys=[submitted_by], back_populates="daily_reports_submitted")
    approver = relationship("User", foreign_keys=[approved_by], back_populates="daily_reports_approved")

    # Helper methods for workflow
    def is_editable_by_supervisor(self) -> bool:
        """Supervisor can edit when DRAFT or REJECTED"""
        return self.status in [DailyReportStatus.DRAFT, DailyReportStatus.REJECTED, DailyReportStatus.RETURNED]

    def is_editable_by_manager(self) -> bool:
        """Manager can edit when SUBMITTED"""
        return self.status == DailyReportStatus.SUBMITTED

    def can_submit_to_manager(self) -> bool:
        """Supervisor can submit when DRAFT or REJECTED"""
        return self.status in [DailyReportStatus.DRAFT, DailyReportStatus.REJECTED, DailyReportStatus.RETURNED]

    def can_approve(self) -> bool:
        """Manager can approve when SUBMITTED"""
        return self.status == DailyReportStatus.SUBMITTED

    def can_reject(self) -> bool:
        """Manager can reject when SUBMITTED"""
        return self.status == DailyReportStatus.SUBMITTED

    def get_status_badge(self) -> dict:
        """Return status badge info for UI"""
        status_map = {
            DailyReportStatus.DRAFT: {"text": "Draft", "color": "secondary", "icon": "bi-pencil"},
            DailyReportStatus.SUBMITTED: {"text": "Awaiting approval", "color": "warning", "icon": "bi-hourglass-split"},
            DailyReportStatus.APPROVED: {"text": "Approved", "color": "success", "icon": "bi-check-circle"},
            DailyReportStatus.SENT_TO_PARENT: {"text": "Sent to parent", "color": "primary", "icon": "bi-send-check"},
            DailyReportStatus.REJECTED: {"text": "Rejected", "color": "danger", "icon": "bi-x-circle"},
            DailyReportStatus.RETURNED: {"text": "Returned", "color": "danger", "icon": "bi-x-circle"},
        }
        return status_map.get(self.status, {"text": str(self.status.value), "color": "secondary", "icon": "bi-question-circle"})


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    type = Column(Enum(IncidentType), nullable=False)
    severity_level = Column(Enum(SeverityLevel), nullable=False)
    description = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    notify_parent_at = Column(DateTime(timezone=True), nullable=True)
    followup_required_flag = Column(Boolean, nullable=False, default=False)
    followup_sla_deadline = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    classification = Column(String(100), nullable=True)
    parent_informed = Column(Boolean, nullable=False, default=False)
    parent_response = Column(Text, nullable=True)
    parent_not_informed_reason = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    attachment_url = Column(String(500), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_incidents_kg_occurred_at", "kindergarten_id", "occurred_at"),
        Index("ix_incidents_kg_severity", "kindergarten_id", "severity_level"),
    )

    # Relationships
    child = relationship("Child", back_populates="incidents")
    kindergarten = relationship("Kindergarten", back_populates="incidents")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(Enum(ReportType), nullable=False)
    scope_type = Column(Enum(ReportScopeType), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    governorate = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    file_path = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_reports_scope_type", "scope_type"),
        Index("idx_reports_created_by", "created_by"),
        Index("idx_reports_created_at", "created_at"),
    )

    # Relationships
    kindergarten = relationship("Kindergarten")
    creator = relationship("User")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    observed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    domain = Column(Enum(LearningDomain), nullable=False)
    observation_text = Column(Text, nullable=False)
    mastery_level = Column(Enum(MasteryLevel), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    child = relationship("Child", back_populates="observations")
    observer = relationship("User", back_populates="observations")


class CurriculumOutcome(Base):
    __tablename__ = "curriculum_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(Enum(LearningDomain), nullable=False)
    age_band_min_months = Column(Integer, nullable=False)
    age_band_max_months = Column(Integer, nullable=False)
    indicator_code = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_curriculum_outcomes_domain_age", "domain", "age_band_min_months"),
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(PortfolioStatus), nullable=False, default=PortfolioStatus.DRAFT)
    published_at = Column(DateTime(timezone=True), nullable=True)
    parent_viewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    child = relationship("Child", back_populates="portfolios")


class HealthAlert(Base):
    __tablename__ = "health_alerts"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    alert_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    child = relationship("Child", back_populates="health_alerts")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_type = Column(Enum(MessageThreadType), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Add recipient_id for direct messages
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    thread_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    subject = Column(String(255), nullable=True)
    message_body = Column(Text, nullable=False)
    allow_replies = Column(Boolean, nullable=False, default=True)
    target_mode = Column(String(50), nullable=True)
    target_roles = Column(JSON, nullable=True)
    target_governorates = Column(JSON, nullable=True)
    target_kindergarten_ids = Column(JSON, nullable=True)
    target_search = Column(String(255), nullable=True)
    recipient_count = Column(Integer, nullable=True)
    translated_text = Column(Text, nullable=True)
    queue_status = Column(Enum(MessageQueueStatus), nullable=True, default=MessageQueueStatus.SENT)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id], back_populates="messages_sent")
    # Add relationship for recipient if needed, or just use foreign key
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="messages_received")
    thread_root = relationship("Message", remote_side=[id], foreign_keys=[thread_id], backref="thread_messages")
    reply_to = relationship("Message", remote_side=[id], foreign_keys=[reply_to_id], backref="replies")
    kindergarten = relationship("Kindergarten", back_populates="messages")
    user_states = relationship("MessageUserState", back_populates="message", cascade="all, delete-orphan")
    attachments = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan")
    recipients = relationship("MessageRecipient", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_messages_kindergarten_created_at", "kindergarten_id", "created_at"),
        Index("ix_messages_sender_id", "sender_id"),
        Index("ix_messages_recipient_id", "recipient_id"),
        Index("ix_messages_thread_id", "thread_id"),
        Index("ix_messages_thread_type", "thread_type"),
    )


class MessageRecipient(Base):
    """Recipients for announcement messages (many-to-many relationship)"""
    __tablename__ = "message_recipients"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="queued")  # queued, sent, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="recipients")
    recipient = relationship("User")

    __table_args__ = (
        UniqueConstraint("message_id", "recipient_user_id", name="uq_message_recipient"),
        Index("ix_message_recipients_message_id", "message_id"),
        Index("ix_message_recipients_recipient_user_id", "recipient_user_id"),
        Index("ix_message_recipients_status", "status"),
    )


class MessageUserState(Base):
    __tablename__ = "message_user_states"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="user_states")
    user = relationship("User", back_populates="message_states")

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_user_state"),
        Index("ix_message_user_state_user_read", "user_id", "read_at"),
        Index("ix_message_user_state_user_archived", "user_id", "archived_at"),
        Index("ix_message_user_state_user_deleted", "user_id", "deleted_at"),
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_provider = Column(String(50), nullable=False)
    storage_key = Column(String(500), nullable=False)
    url = Column(String(500), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="attachments")
    uploaded_by = relationship("User")

    __table_args__ = (
        Index("ix_message_attachments_message_id", "message_id"),
        Index("ix_message_attachments_uploaded_by", "uploaded_by_id"),
    )


class UserDeviceToken(Base):
    __tablename__ = "user_device_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), nullable=False, unique=True)
    platform = Column(Enum(DevicePlatform), nullable=False)
    device_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")

    __table_args__ = (
        Index("ix_user_device_tokens_user_id", "user_id"),
        Index("ix_user_device_tokens_platform", "platform"),
    )


class AbsenceRequestStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class NotificationType(str, enum.Enum):
    MESSAGE = "MESSAGE"
    DAILY_REPORT_SENT = "DAILY_REPORT_SENT"  # Report sent to parent
    DAILY_REPORT_SUBMITTED = "DAILY_REPORT_SUBMITTED"  # Supervisor submitted to manager
    DAILY_REPORT_REJECTED = "DAILY_REPORT_REJECTED"  # Manager rejected report
    DAILY_REPORT_MISSING = "DAILY_REPORT_MISSING"  # Alert for missing reports
    ABSENCE_REQUEST_SUBMITTED = "ABSENCE_REQUEST_SUBMITTED"  # Parent submitted absence request
    ABSENCE_REQUEST_APPROVED = "ABSENCE_REQUEST_APPROVED"  # Manager approved absence request
    ABSENCE_REQUEST_REJECTED = "ABSENCE_REQUEST_REJECTED"  # Manager rejected absence request
    ATTENDANCE_CORRECTED = "ATTENDANCE_CORRECTED"  # Attendance status changed
    SYSTEM = "SYSTEM"
    GOVERNANCE_REMINDER = "GOVERNANCE_REMINDER"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    daily_report_id = Column(Integer, ForeignKey("daily_reports.id"), nullable=True)
    absence_request_id = Column(Integer, ForeignKey("absence_requests.id"), nullable=True)
    notification_type = Column(Enum(NotificationType), nullable=True, default=NotificationType.MESSAGE)
    channel = Column(Enum(NotificationChannel), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING)
    payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    message = relationship("Message")
    daily_report = relationship("DailyReport")

    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_message", "message_id"),
        Index("ix_notifications_channel", "channel"),
        Index("ix_notifications_daily_report", "daily_report_id"),
    )


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(EventType), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    requires_consent_flag = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="events")


class Survey(Base):
    __tablename__ = "surveys"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    nps_question_enabled = Column(Boolean, nullable=False, default=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="surveys")
    responses = relationship("SurveyResponse", back_populates="survey")


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nps_score = Column(Integer, nullable=True) # 0-10
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("survey_id", "parent_id", name="uq_survey_responses_survey_parent"),
    )

    # Relationships
    survey = relationship("Survey", back_populates="responses")
    parent = relationship("User") # No back_populate needed on User for now strictly


class AbsenceRequest(Base):
    """Parent absence request for a child over a date range."""
    __tablename__ = "absence_requests"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("parent_profiles.id"), nullable=False)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(Enum(AbsenceRequestStatus), nullable=False, default=AbsenceRequestStatus.SUBMITTED)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_note = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent = relationship("ParentProfile")
    child = relationship("Child")
    kindergarten = relationship("Kindergarten")
    class_ = relationship("Class")
    manager = relationship("User")

    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_absence_start_lte_end"),
        Index("ix_absence_child_dates", "child_id", "start_date", "end_date"),
        Index("ix_absence_kg_status", "kindergarten_id", "status", "created_at"),
        Index("ix_absence_parent", "parent_id", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    actor_role = Column(String(50), nullable=True)
    request_id = Column(String(36), nullable=True)
    ip_address = Column(String(50), nullable=True)
    sensitivity_level = Column(Integer, nullable=True)
    impersonated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    impersonation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_entity_type", "entity_type"),
        Index("idx_audit_logs_created_at", "created_at"),
        Index("idx_audit_logs_user_id", "user_id"),
    )


class StaffPresenceLog(Base):
    __tablename__ = "staff_presence_logs"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RatioCompliance(Base):
    __tablename__ = "ratio_compliance"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    date = Column(Date, nullable=False)
    operating_minutes = Column(Integer, nullable=False)
    compliant_minutes = Column(Integer, nullable=False)
    staff_count_avg = Column(Float, nullable=False)
    child_count_avg = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_ratio_compliance_kg_date", "kindergarten_id", "date"),
    )


class KPISnapshot(Base):
    __tablename__ = "kpi_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    kpi_name = Column(String(100), nullable=False)
    kpi_value = Column(Float, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    is_locked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GovernanceScore(Base):
    __tablename__ = "governance_scores"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    governance_quality_index = Column(Float, nullable=False)
    child_experience_index = Column(Float, nullable=False)
    final_governance_score = Column(Float, nullable=False)
    band = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SafeguardingCase(Base):
    __tablename__ = "safeguarding_cases"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    case_description = Column(Text, nullable=False)
    status = Column(String(50), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    sla_escalation_deadline = Column(DateTime(timezone=True), nullable=True)
    sla_closure_deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ContactMessage(Base):
    """
    Public contact-form submission.  Anyone can submit; only admins can view
    and resolve.  Added as part of P1-D audit remediation.
    """
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    subject = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_contact_messages_is_resolved", "is_resolved"),
        Index("ix_contact_messages_submitted_at_desc", submitted_at.desc()),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    priority = Column(Enum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TrainingStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"

class TrainingModule(Base):
    __tablename__ = "training_modules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class StaffTrainingCompletion(Base):
    __tablename__ = "staff_training_completion"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    training_module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True) # Optional, for network-level trainings
    completion_date = Column(Date, nullable=True)
    status = Column(Enum(TrainingStatus), nullable=False, default=TrainingStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="training_completions")
    training_module = relationship("TrainingModule")
    kindergarten = relationship("Kindergarten") # Optional relationship

    __table_args__ = (
        UniqueConstraint("user_id", "training_module_id", name="uq_staff_training"),
        Index("ix_staff_training_kindergarten", "kindergarten_id"),
    )

class KPITarget(Base):
    __tablename__ = "kpi_targets"

    id = Column(Integer, primary_key=True, index=True)
    kpi_name = Column(String(100), nullable=False)
    target_value = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True) # NULL for network-wide target
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    kindergarten = relationship("Kindergarten")

    __table_args__ = (
        UniqueConstraint("kpi_name", "effective_date", "kindergarten_id", name="uq_kpi_target"),
        Index("ix_kpi_target_name_date", "kpi_name", "effective_date"),
    )


# =============================================================================
# Analytics & Reporting Models
# =============================================================================

# (AnalyticsDimensionType enum defined at top of file)

# Advanced Analytics Cache for multi-dimensional, advanced, and predictive metrics
class AdvancedAnalyticsCache(Base):
    """
    Multi-dimensional analytics cache with advanced, predictive, and correlation metrics.
    """
    __tablename__ = "advanced_analytics_cache"

    id = Column(Integer, primary_key=True, index=True)
    dimension_type = Column(Enum(AnalyticsDimensionType), nullable=False)
    dimension_id = Column(String(100), nullable=False)
    period_type = Column(Enum(AnalyticsPeriodType), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Core KPIs
    attendance_rate = Column(Float)
    chronic_absence_rate = Column(Float)
    incident_rate_per_100 = Column(Float)
    serious_incident_rate = Column(Float)
    ratio_compliance_rate = Column(Float)
    report_completion_rate = Column(Float)

    # Advanced Metrics
    parent_satisfaction_nps = Column(Float)
    child_development_index = Column(Float)
    staff_turnover_rate = Column(Float)
    regulatory_compliance_score = Column(Float)

    # Predictive Indicators
    attendance_trend_slope = Column(Float)
    risk_score = Column(Float)
    improvement_velocity = Column(Float)

    # Correlations
    attendance_incident_correlation = Column(Float)
    staffing_quality_correlation = Column(Float)

    # Health/Alerts
    health_alerts_count = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_adv_analytics_cache_dim', 'dimension_type', 'dimension_id'),
        Index('ix_adv_analytics_cache_period', 'period_type', 'period_start', 'period_end'),
        Index('ix_adv_analytics_cache_lookup', 'dimension_type', 'dimension_id', 'period_type', 'period_start', 'period_end', unique=True),
    )


# (AnalyticsPeriodType and ExportStatus enums defined at top of file)


class ExportFormat(str, PyEnum):
    """Export file formats"""
    CSV = "CSV"
    JSON = "JSON"
    EXCEL = "EXCEL"
    PDF = "PDF"


class AnalyticsDimensionCache(Base):
    """
    Pre-aggregated metrics cache for fast dashboard loading.
    Stores computed KPIs at various dimension levels (network, governorate, KG, class).
    """
    __tablename__ = "analytics_dimension_cache"

    id = Column(Integer, primary_key=True, index=True)
    dimension_type = Column(Enum(AnalyticsDimensionType), nullable=False)
    dimension_id = Column(String(100), nullable=False)  # governorate name, KG id, class id, or "NETWORK"
    period_type = Column(Enum(AnalyticsPeriodType), nullable=False)
    period_date = Column(Date, nullable=False)  # Start date of the period

    # Enrollment metrics
    total_capacity = Column(Integer, nullable=True)
    total_enrolled = Column(Integer, nullable=True)
    enrollment_rate = Column(Float, nullable=True)
    pending_applications = Column(Integer, nullable=True)

    # Attendance metrics
    expected_attendance = Column(Integer, nullable=True)
    actual_attendance = Column(Integer, nullable=True)
    attendance_rate = Column(Float, nullable=True)
    chronic_absence_count = Column(Integer, nullable=True)

    # Daily reports metrics
    expected_reports = Column(Integer, nullable=True)
    submitted_reports = Column(Integer, nullable=True)
    report_completion_rate = Column(Float, nullable=True)

    # Safety metrics
    total_incidents = Column(Integer, nullable=True)
    high_severity_incidents = Column(Integer, nullable=True)
    incident_rate_per_100 = Column(Float, nullable=True)

    # Staffing metrics
    total_staff = Column(Integer, nullable=True)
    ratio_compliant_minutes = Column(Integer, nullable=True)
    ratio_total_minutes = Column(Integer, nullable=True)
    ratio_compliance_rate = Column(Float, nullable=True)

    # Engagement metrics
    surveys_sent = Column(Integer, nullable=True)
    survey_responses = Column(Integer, nullable=True)
    survey_response_rate = Column(Float, nullable=True)
    nps_score = Column(Float, nullable=True)

    # Governance scores
    governance_quality_index = Column(Float, nullable=True)
    child_experience_index = Column(Float, nullable=True)
    final_governance_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_analytics_cache_dimension', 'dimension_type', 'dimension_id'),
        Index('ix_analytics_cache_period', 'period_type', 'period_date'),
        Index('ix_analytics_cache_lookup', 'dimension_type', 'dimension_id', 'period_type', 'period_date'),
    )


class ExportJob(Base):
    """
    Track asynchronous export requests for CSV/PDF/Excel reports.
    """
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    export_format = Column(Enum(ExportFormat), nullable=False)
    report_type = Column(String(100), nullable=False)  # e.g., "attendance_summary", "incident_report"
    filters = Column(JSON, nullable=True)  # Store filter parameters as JSON
    status = Column(Enum(ExportStatus), nullable=False, default=ExportStatus.PENDING)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", backref="export_jobs")

    __table_args__ = (
        Index('ix_export_jobs_user_status', 'user_id', 'status'),
    )


class ReportTemplate(Base):
    """Saved report configurations for quick reuse."""
    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    report_type = Column(String(100), nullable=False)
    filters = Column(JSON, nullable=True)
    export_format = Column(String(20), nullable=False, default="CSV")
    include_charts = Column(Boolean, nullable=False, default=True)
    include_summary = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User")

    __table_args__ = (
        Index("ix_report_templates_created_by", "created_by"),
    )


class ScheduledReport(Base):
    """Scheduled report generation and delivery."""
    __tablename__ = "scheduled_reports"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    report_type = Column(String(100), nullable=False)
    filters = Column(JSON, nullable=True)
    export_format = Column(String(20), nullable=False, default="CSV")
    frequency = Column(String(50), nullable=False)  # daily, weekly, monthly, quarterly, once
    recipients = Column(JSON, nullable=True)  # list of user_ids or emails
    next_run = Column(DateTime(timezone=True), nullable=True)
    last_run = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User")

    __table_args__ = (
        Index("ix_scheduled_reports_created_by", "created_by"),
        Index("ix_scheduled_reports_next_run", "next_run"),
    )


class PredictiveModel(Base):
    __tablename__ = "predictive_models"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=False)
    trained_at = Column(DateTime(timezone=True), nullable=False)
    training_start = Column(Date, nullable=True)
    training_end = Column(Date, nullable=True)
    parameters = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_predictive_models_metric_scope", "metric_type", "scope_type", "scope_id"),
        Index("ix_predictive_models_trained_at", "trained_at"),
    )


class PredictionCache(Base):
    __tablename__ = "prediction_cache"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False)
    params_hash = Column(String(128), nullable=False)
    points = Column(JSON, nullable=False)
    forecast_points = Column(JSON, nullable=False)
    confidence = Column(JSON, nullable=False)
    model_meta = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_prediction_cache_lookup", "metric_type", "scope_type", "scope_id", "params_hash", unique=True),
        Index("ix_prediction_cache_created_at", "created_at"),
    )


class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    detected_at = Column(Date, nullable=False)
    score = Column(Float, nullable=False)
    severity = Column(Enum(SeverityLevel), nullable=False)
    message = Column(String(255), nullable=False)
    is_acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_anomaly_alerts_metric_scope", "metric_type", "scope_type", "scope_id"),
        Index("ix_anomaly_alerts_detected_at", "detected_at"),
        Index("ix_anomaly_alerts_ack", "is_acknowledged"),
    )


class DrilldownPath(Base):
    __tablename__ = "drilldown_paths"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    visited_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_drilldown_paths_user_ts", "user_id", "visited_at"),
    )


class AlertThreshold(Base):
    __tablename__ = "alert_thresholds"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    operator = Column(Enum(AlertOperator), nullable=False)
    threshold_value = Column(Float, nullable=False)
    window_days = Column(Integer, nullable=False, default=30)
    severity = Column(Enum(SeverityLevel), nullable=False, default=SeverityLevel.MEDIUM)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_alert_thresholds_scope", "metric_type", "scope_type", "scope_id"),
        Index("ix_alert_thresholds_active", "is_active"),
    )


class ActiveAlert(Base):
    __tablename__ = "active_alerts"

    id = Column(Integer, primary_key=True, index=True)
    threshold_id = Column(Integer, ForeignKey("alert_thresholds.id"), nullable=False)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    current_value = Column(Float, nullable=False)
    message = Column(String(255), nullable=False)
    severity = Column(Enum(SeverityLevel), nullable=False, default=SeverityLevel.MEDIUM)
    status = Column(Enum(AlertStatus), nullable=False, default=AlertStatus.ACTIVE)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_active_alerts_status", "status"),
        Index("ix_active_alerts_scope", "metric_type", "scope_type", "scope_id"),
    )


class PerformanceTarget(Base):
    __tablename__ = "performance_targets"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    target_value = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_performance_targets_lookup", "metric_type", "scope_type", "scope_id", "effective_date"),
    )


class BenchmarkData(Base):
    __tablename__ = "benchmark_data"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(100), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    comparison_group = Column(String(50), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_benchmark_data_scope", "metric_type", "scope_type", "scope_id"),
        Index("ix_benchmark_data_period", "period_start", "period_end"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(String(100), nullable=True)
    metric_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(Enum(SeverityLevel), nullable=False, default=SeverityLevel.MEDIUM)
    recommended_actions = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    kindergarten = relationship("Kindergarten")

    __table_args__ = (
        Index("ix_recommendations_scope", "scope_type", "scope_id"),
        Index("ix_recommendations_kindergarten", "kindergarten_id"),
    )


class ActionPlan(Base):
    __tablename__ = "action_plans"

    id = Column(Integer, primary_key=True, index=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(Enum(ActionPlanStatus), nullable=False, default=ActionPlanStatus.OPEN)
    progress_percent = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    recommendation = relationship("Recommendation")
    kindergarten = relationship("Kindergarten")

    __table_args__ = (
        Index("ix_action_plans_status", "status"),
        Index("ix_action_plans_kindergarten", "kindergarten_id"),
    )


class ChildDocument(Base):
    """Upload & track enrollment documents, health certificates, permission forms."""
    __tablename__ = "child_documents"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    document_type = Column(String(50), nullable=False)  # birth_certificate, health_certificate, permission_form, id_copy, photo, other
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)  # bytes
    description = Column(String(500), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_child_documents_child_id", "child_id"),
        Index("idx_child_documents_type", "document_type"),
    )

    # Relationships
    child = relationship("Child", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    verifier = relationship("User", foreign_keys=[verified_by])


class DataQualityMetric(Base):
    __tablename__ = "data_quality_metrics"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=True)
    completeness_percent = Column(Float, nullable=False)
    accuracy_score = Column(Float, nullable=False)
    timeliness_score = Column(Float, nullable=False)
    consistency_score = Column(Float, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_data_quality_entity", "entity_type", "entity_id"),
        Index("ix_data_quality_evaluated_at", "evaluated_at"),
    )


class DailyReportView(Base):
    """Tracks when a parent views a sent daily report"""
    __tablename__ = "daily_report_views"

    id = Column(Integer, primary_key=True, index=True)
    daily_report_id = Column(Integer, ForeignKey("daily_reports.id"), nullable=False)
    parent_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now())

    daily_report = relationship("DailyReport")
    parent_user = relationship("User")

    __table_args__ = (
        UniqueConstraint("daily_report_id", "parent_user_id", name="uq_daily_report_view"),
        Index("ix_daily_report_views_report", "daily_report_id"),
    )


class DailyChecklist(Base):
    """Daily operational checklist completion records by kindergarten."""
    __tablename__ = "daily_checklists"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    checklist_date = Column(Date, nullable=False)
    checklist_type = Column(String(50), nullable=False)  # opening, safety, hygiene, closing
    status = Column(Enum(DailyChecklistStatus), nullable=False, default=DailyChecklistStatus.PENDING)
    notes = Column(Text, nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    kindergarten = relationship("Kindergarten")
    submitter = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "kindergarten_id",
            "checklist_date",
            "checklist_type",
            name="uq_daily_checklist_kindergarten_date_type",
        ),
        Index("ix_daily_checklists_kindergarten_date", "kindergarten_id", "checklist_date"),
        Index("ix_daily_checklists_status", "status"),
    )


class GovernanceReminder(Base):
    """Tracks governance reminders sent to KGs/supervisors with cooldown enforcement"""
    __tablename__ = "governance_reminders"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(20), nullable=False)  # "kindergarten" or "supervisor"
    target_id = Column(Integer, nullable=False)
    reminder_type = Column(String(50), nullable=False)  # e.g. "low_submission_rate"
    sent_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    cooldown_expires_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=True)

    sender = relationship("User")

    __table_args__ = (
        Index("ix_governance_reminders_target", "target_type", "target_id", "cooldown_expires_at"),
    )


# New models for Excel import feature
class ImportedKindergarten(Base):
    __tablename__ = "imported_kindergartens"

    id = Column(Integer, primary_key=True, index=True)
    name_ar = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=True)
    governorate = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    area = Column(String(100), nullable=True)
    detailed_address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("name_ar", "city", "phone", name="uq_imported_kindergartens_name_city_phone"),
        Index("idx_imported_kindergartens_governorate", "governorate"),
        Index("idx_imported_kindergartens_city", "city"),
    )


class ImportLog(Base):
    __tablename__ = "import_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    stored_file_path = Column(String(500), nullable=True)
    total_rows = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    errors_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# Jordan Heat Map — daily snapshot models
# Reference: docs/JORDAN_HEAT_MAP_TECHNICAL_SPECIFICATION.md §4
# These tables back the Admin Heat Map dashboard.  Snapshots are immutable
# once written; the pipeline is idempotent on (snapshot_date, dimension).
# =============================================================================


class MapIndicatorSnapshot(Base):
    """One row per (date, governorate, main_indicator). Upserted daily."""
    __tablename__ = "map_indicator_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    governorate_code = Column(String(8), nullable=False, index=True)
    main_indicator = Column(String(40), nullable=False)
    value = Column(Float, nullable=False)
    previous_value = Column(Float, nullable=True)
    trend_pct = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_date", "governorate_code", "main_indicator", name="uq_mis"),
        Index("idx_mis_latest", "snapshot_date", "governorate_code"),
        Index("idx_mis_history", "governorate_code", "main_indicator", "snapshot_date"),
        CheckConstraint("value BETWEEN 0 AND 100", name="ck_mis_value_range"),
    )


class MapSubIndicatorValue(Base):
    """One row per (date, governorate, sub_indicator)."""
    __tablename__ = "map_sub_indicator_value"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    governorate_code = Column(String(8), nullable=False, index=True)
    sub_indicator = Column(String(40), nullable=False)
    raw_value = Column(Float, nullable=False)
    threshold_high = Column(Float, nullable=True)
    threshold_low = Column(Float, nullable=True)
    above_threshold = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_date", "governorate_code", "sub_indicator", name="uq_ssiv"),
        Index("idx_ssiv_gov", "snapshot_date", "governorate_code"),
    )


class MapCorrelationSnapshot(Base):
    """One row per (date, main, sub, method) — Pearson / Spearman / Kendall τ-b."""
    __tablename__ = "map_correlation_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    main_indicator = Column(String(40), nullable=False)
    sub_indicator = Column(String(40), nullable=False)
    method = Column(String(10), nullable=False)
    coefficient = Column(Float, nullable=True)
    p_value = Column(Float, nullable=True)
    n_samples = Column(Integer, nullable=False, default=0)
    strength = Column(String(15), nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_date", "main_indicator", "sub_indicator", "method", name="uq_corr"),
        Index("idx_corr_latest", "snapshot_date"),
        Index("idx_corr_pair", "main_indicator", "sub_indicator", "snapshot_date"),
        CheckConstraint(
            "method IN ('pearson', 'spearman', 'kendall_tau')",
            name="ck_corr_method",
        ),
    )


class MapRegressionSnapshot(Base):
    """One row per (date, main, sub) — standardized OLS coefficient + VIF."""
    __tablename__ = "map_regression_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    main_indicator = Column(String(40), nullable=False)
    sub_indicator = Column(String(40), nullable=False)
    beta_std = Column(Float, nullable=False)
    std_error = Column(Float, nullable=True)
    t_stat = Column(Float, nullable=True)
    p_value = Column(Float, nullable=True)
    r_squared = Column(Float, nullable=True)
    adj_r_squared = Column(Float, nullable=True)
    high_impact = Column(Boolean, nullable=False, default=False)
    vif = Column(Float, nullable=True)
    vif_flag = Column(String(10), nullable=False, default="ok")
    n_samples = Column(Integer, nullable=False, default=0)
    ridge_used = Column(Boolean, nullable=False, default=False)
    fit_warning = Column(String(40), nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_date", "main_indicator", "sub_indicator", name="uq_reg"),
        Index("idx_reg_latest", "snapshot_date"),
        Index("idx_reg_main", "main_indicator", "snapshot_date"),
    )


class MapRiskSnapshot(Base):
    """One row per (date, governorate) — composite risk score + level + drivers."""
    __tablename__ = "map_risk_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    governorate_code = Column(String(8), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String(10), nullable=False)
    top_driver_sub = Column(String(40), nullable=True)
    top_driver_beta = Column(Float, nullable=True)
    trend_pct = Column(Float, nullable=True)
    contributing_subs = Column(JSON, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_date", "governorate_code", name="uq_risk"),
        Index("idx_risk_latest", "snapshot_date"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_range"),
        CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_risk_level",
        ),
    )


class MapAlertHistory(Base):
    """Append-only alert ledger.  One row per (date, gov, sub, rule)."""
    __tablename__ = "map_alert_history"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    governorate_code = Column(String(8), nullable=True, index=True)
    sub_indicator = Column(String(40), nullable=False, index=True)
    rule = Column(String(80), nullable=False)
    severity = Column(String(10), nullable=False)
    current_value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    message = Column(Text, nullable=False)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "governorate_code", "sub_indicator", "rule",
            name="uq_alert",
        ),
        CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_alert_severity",
        ),
    )


class MapDailyRunLog(Base):
    """Append-only audit log of the daily ETL pipeline runs."""
    __tablename__ = "map_daily_run_log"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(36), nullable=False, unique=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)
    rows_processed = Column(Integer, nullable=False, default=0)
    governorates = Column(Integer, nullable=False, default=0)
    errors = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','success','failed','partial')",
            name="ck_run_status",
        ),
    )


class Governorate(Base):
    """The 12 Jordan governorates, normalized seed data."""
    __tablename__ = "governorate"

    code = Column(String(8), primary_key=True)
    slug = Column(String(20), nullable=False, unique=True, index=True)
    name_en = Column(String(40), nullable=False)
    name_ar = Column(String(40), nullable=False)
    center_lon = Column(Float, nullable=False)
    center_lat = Column(Float, nullable=False)
    display_order = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)


# =============================================================================
# AI infrastructure (ai/ package: ml.py, llm.py, insights.py, embeddings.py)
# =============================================================================

class AIParentRecommendation(Base):
    __tablename__ = "ai_parent_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=True)
    report_date = Column(Date, nullable=False)
    source_report_id = Column(Integer, ForeignKey("daily_reports.id"), nullable=True)
    recommendation_type = Column(String(50), nullable=False)
    content_ar = Column(Text, nullable=True)
    content_en = Column(Text, nullable=True)
    model_version = Column(String(50), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    confidence = Column(Float, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    parent_feedback = Column(String(20), nullable=True)
    feedback_at = Column(DateTime(timezone=True), nullable=True)
    human_reviewed = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIManagerAlert(Base):
    __tablename__ = "ai_manager_alerts"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    alert_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)
    target_entity_type = Column(String(50), nullable=True)
    target_entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=False)
    rule_version = Column(String(20), nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    dismissed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIJobLog(Base):
    __tablename__ = "ai_job_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(100), nullable=False)
    job_type = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)
    records_in = Column(Integer, nullable=True)
    records_out = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    model_version = Column(String(50), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    job_metadata = Column(JSON, nullable=True)


class AIFeature(Base):
    __tablename__ = "ai_features"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    feature_name = Column(String(100), nullable=False)
    feature_value = Column(Float, nullable=True)
    feature_json = Column(JSON, nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)
    model_version = Column(String(50), nullable=True)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "feature_name", name="idx_ai_features_entity_feature"),
    )


class AIModelVersion(Base):
    __tablename__ = "ai_model_versions"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False)
    version = Column(String(20), nullable=False)
    model_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    parameters = Column(JSON, nullable=True)
    deployed_at = Column(DateTime(timezone=True), server_default=func.now())
    retired_at = Column(DateTime(timezone=True), nullable=True)
    deployed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_ai_model_version"),
    )


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, index=True)
    source_table = Column(String(100), nullable=False)
    source_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_role = Column(String(50), nullable=True)
    feedback_type = Column(String(50), nullable=False)
    feedback_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIEmbedding(Base):
    __tablename__ = "ai_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    source_table = Column(String(100), nullable=False)
    source_id = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    embedding = Column(Text, nullable=False)
    model_name = Column(String(100), nullable=False, default="nomic-embed-text")
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    content_hash = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("source_table", "source_id", "chunk_index", "model_name", name="uq_ai_embeddings_source"),
    )


class TelemetryEventType(str, PyEnum):
    PAGE_VIEW = "page_view"
    INTERACTION = "interaction"
    API_CALL = "api_call"
    ERROR = "error"


class WebVitalType(str, PyEnum):
    LCP = "lcp"
    FID = "fid"
    CLS = "cls"


class VitalRating(str, PyEnum):
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs-improvement"
    POOR = "poor"


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(36), nullable=False)
    session_id = Column(String(64), nullable=False)
    event_type = Column(Enum(TelemetryEventType), nullable=False)
    page = Column(String(255), nullable=False)
    role = Column(String(50), nullable=True)
    lang = Column(String(10), nullable=False, default="ar")
    direction = Column(String(10), nullable=False, default="rtl")
    timestamp_ms = Column(BigInteger, nullable=False)
    duration_ms = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_telemetry_event_id"),
        Index("ix_telemetry_events_session", "session_id"),
        Index("ix_telemetry_events_page", "page"),
        Index("ix_telemetry_events_role", "role"),
        Index("ix_telemetry_events_type", "event_type"),
        Index("ix_telemetry_events_timestamp", "timestamp_ms"),
    )


class WebVitalMetric(Base):
    __tablename__ = "web_vital_metrics"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False)
    page = Column(String(255), nullable=False)
    role = Column(String(50), nullable=True)
    lang = Column(String(10), nullable=False, default="ar")
    direction = Column(String(10), nullable=False, default="rtl")
    metric_name = Column(Enum(WebVitalType), nullable=False)
    value = Column(Float, nullable=False)
    rating = Column(Enum(VitalRating), nullable=False, default=VitalRating.GOOD)
    timestamp_ms = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_web_vitals_session", "session_id"),
        Index("ix_web_vitals_page", "page"),
        Index("ix_web_vitals_metric", "metric_name"),
        Index("ix_web_vitals_timestamp", "timestamp_ms"),
    )


class ClientErrorReport(Base):
    __tablename__ = "client_error_reports"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False)
    page = Column(String(255), nullable=False)
    role = Column(String(50), nullable=True)
    error_type = Column(String(50), nullable=False)
    message = Column(String(500), nullable=False)
    stack_hash = Column(String(16), nullable=True)
    timestamp_ms = Column(BigInteger, nullable=False)
    is_acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_client_errors_session", "session_id"),
        Index("ix_client_errors_page", "page"),
        Index("ix_client_errors_stack_hash", "stack_hash"),
        Index("ix_client_errors_timestamp", "timestamp_ms"),
    )
