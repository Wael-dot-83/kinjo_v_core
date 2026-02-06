"""
SQLAlchemy ORM Models for KInJo Kindergarten Management Platform
"""
import enum
from enum import Enum as PyEnum
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, Date, DateTime,
    ForeignKey, Enum, CheckConstraint, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
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


class DailyReportStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"


class IncidentType(str, enum.Enum):
    INJURY = "INJURY"
    BEHAVIOR = "BEHAVIOR"
    ILLNESS = "ILLNESS"
    OTHER = "OTHER"


class SeverityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


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
    status = Column(Enum(KindergartenStatus), nullable=False, default=KindergartenStatus.DRAFT)
    operating_hours_start = Column(String(5), nullable=True)
    operating_hours_end = Column(String(5), nullable=True)
    license_number = Column(String(100), nullable=True)
    license_valid_until = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    users = relationship("User", back_populates="kindergarten")
    classes = relationship("Class", back_populates="kindergarten")
    services = relationship("KindergartenService", back_populates="kindergarten")
    calendar = relationship("OperatingCalendar", back_populates="kindergarten")
    enrollments = relationship("EnrollmentApplication", back_populates="kindergarten")
    incidents = relationship("Incident", back_populates="kindergarten")
    events = relationship("Event", back_populates="kindergarten")
    messages = relationship("Message", back_populates="kindergarten")
    surveys = relationship("Survey", back_populates="kindergarten")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="users")
    parent_profile = relationship("ParentProfile", back_populates="user", uselist=False)
    supervisor_assignments = relationship("SupervisorAssignment", back_populates="supervisor")
    daily_reports_submitted = relationship("DailyReport", foreign_keys="DailyReport.submitted_by", back_populates="submitter")
    daily_reports_approved = relationship("DailyReport", foreign_keys="DailyReport.approved_by", back_populates="approver")
    observations = relationship("Observation", back_populates="observer")
    messages_sent = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    messages_received = relationship("Message", foreign_keys="Message.recipient_id", back_populates="recipient")
    message_states = relationship("MessageUserState", back_populates="user")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="password_reset_tokens")


class ParentProfile(Base):
    __tablename__ = "parent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
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
    correspondence_preference = Column(Boolean, nullable=False, default=True)
    profile_complete = Column(Boolean, nullable=False, default=False)
    profile_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="parent_profile")
    children = relationship("Child", back_populates="parent")


class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, index=True)
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
    correspondence_flag = Column(Boolean, nullable=False, default=True)
    profile_complete = Column(Boolean, nullable=False, default=False)
    profile_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent = relationship("ParentProfile", back_populates="children")
    enrollments = relationship("EnrollmentApplication", back_populates="child")
    attendance_logs = relationship("AttendanceLog", back_populates="child")
    daily_reports = relationship("DailyReport", back_populates="child")
    incidents = relationship("Incident", back_populates="child")
    observations = relationship("Observation", back_populates="child")
    portfolios = relationship("Portfolio", back_populates="child")
    health_alerts = relationship("HealthAlert", back_populates="child")


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    name_ar = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=True)
    capacity_total = Column(Integer, nullable=False)
    min_age_months = Column(Integer, nullable=False)
    max_age_months = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    kindergarten = relationship("Kindergarten", back_populates="classes")
    supervisor_assignments = relationship("SupervisorAssignment", back_populates="class_")
    enrollments = relationship("EnrollmentApplication", back_populates="class_")


class SupervisorAssignment(Base):
    __tablename__ = "supervisor_assignments"

    id = Column(Integer, primary_key=True, index=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    class_ = relationship("Class", back_populates="supervisor_assignments")
    supervisor = relationship("User", back_populates="supervisor_assignments")


class KindergartenService(Base):
    __tablename__ = "kindergarten_services"

    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=True)
    service_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    enabled_flag = Column(Boolean, nullable=False, default=True)
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
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    status = Column(Enum(EnrollmentStatus), nullable=False, default=EnrollmentStatus.DRAFT)
    status_reason = Column(String(255), nullable=True)
    source = Column(String(50), nullable=False, default="WEB")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    decision_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
    enrollment_start_date = Column(Date, nullable=True)
    enrollment_end_date = Column(Date, nullable=True)
    class_assignment_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    child = relationship("Child", back_populates="enrollments")
    kindergarten = relationship("Kindergarten", back_populates="enrollments")
    class_ = relationship("Class", back_populates="enrollments")
    waitlist_entry = relationship("WaitlistEntry", back_populates="enrollment", uselist=False)


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
    date = Column(Date, nullable=False)
    check_in_at = Column(DateTime(timezone=True), nullable=False)
    check_out_at = Column(DateTime(timezone=True), nullable=True)
    method = Column(Enum(AttendanceMethod), nullable=False)
    dropped_by_name = Column(String(255), nullable=True)
    picked_by_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    child = relationship("Child", back_populates="attendance_logs")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Enum(DailyReportStatus), nullable=False, default=DailyReportStatus.DRAFT)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    arrival_time = Column(String(5), nullable=False)
    leave_time = Column(String(5), nullable=False)
    breakfast = Column(Boolean, nullable=True)
    snack = Column(Boolean, nullable=True)
    milk = Column(Boolean, nullable=True)
    lunch = Column(Boolean, nullable=True)
    nap_start = Column(String(5), nullable=True)
    nap_end = Column(String(5), nullable=True)
    nap_duration_minutes = Column(Integer, nullable=True)
    activities = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("child_id", "date", name="uq_daily_report_child_date"),
        Index("ix_daily_reports_child_date", "child_id", "date")
    )

    # Relationships
    child = relationship("Child", back_populates="daily_reports")
    submitter = relationship("User", foreign_keys=[submitted_by], back_populates="daily_reports_submitted")
    approver = relationship("User", foreign_keys=[approved_by], back_populates="daily_reports_approved")


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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    child = relationship("Child", back_populates="incidents")
    kindergarten = relationship("Kindergarten", back_populates="incidents")


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


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    channel = Column(Enum(NotificationChannel), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING)
    payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    message = relationship("Message")

    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_message", "message_id"),
        Index("ix_notifications_channel", "channel"),
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

    # Relationships
    survey = relationship("Survey", back_populates="responses")
    parent = relationship("User") # No back_populate needed on User for now strictly


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    sensitivity_level = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())




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
    opened_at = Column(DateTime(timezone=True), nullable=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    sla_escalation_deadline = Column(DateTime(timezone=True), nullable=True)
    sla_closure_deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


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


class ExportFormat(str, PyEnum):
    """Export file formats"""
    CSV = "CSV"
    PDF = "PDF"
    EXCEL = "EXCEL"


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
