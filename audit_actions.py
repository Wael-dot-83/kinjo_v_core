"""
Centralized audit action identifiers.

Use these constants instead of hard-coded strings to keep audit action
taxonomy consistent across endpoints and tests.
"""


class AuditAction:
    # User/Admin exports
    USER_EXPORT = "USER_EXPORT"
    AUDIT_LOG_EXPORT = "AUDIT_LOG_EXPORT"

    # Incident report exports
    INCIDENT_REPORT_EXPORT = "INCIDENT_REPORT_EXPORT"
    INCIDENT_REPORT_EXPORT_FAILED = "INCIDENT_REPORT_EXPORT_FAILED"

    # Analytics exports
    ANALYTICS_EXPORT_SYNC = "ANALYTICS_EXPORT_SYNC"
    ANALYTICS_EXPORT_SYNC_FAILED = "ANALYTICS_EXPORT_SYNC_FAILED"
    ANALYTICS_EXPORT_REQUESTED = "ANALYTICS_EXPORT_REQUESTED"
    ANALYTICS_EXPORT_REQUEST_FAILED = "ANALYTICS_EXPORT_REQUEST_FAILED"
    ANALYTICS_EXPORT_DOWNLOADED = "ANALYTICS_EXPORT_DOWNLOADED"
    ANALYTICS_EXPORT_JOB_COMPLETED = "ANALYTICS_EXPORT_JOB_COMPLETED"
    ANALYTICS_EXPORT_JOB_FAILED = "ANALYTICS_EXPORT_JOB_FAILED"

    # Admin dashboard
    ADMIN_DASHBOARD_VIEWED = "ADMIN_DASHBOARD_VIEWED"
    ADMIN_DASHBOARD_ERROR = "ADMIN_DASHBOARD_ERROR"
    CLASSIFICATION_CACHE_WARM = "CLASSIFICATION_CACHE_WARM"
    CLASSIFICATION_CACHE_INVALIDATE = "CLASSIFICATION_CACHE_INVALIDATE"

    # Kindergarten imports
    KINDERGARTEN_IMPORT = "KINDERGARTEN_IMPORT"


EXPORT_ACTIONS = {
    "user_export": AuditAction.USER_EXPORT,
    "audit_log_export": AuditAction.AUDIT_LOG_EXPORT,
    "incident_report_export": AuditAction.INCIDENT_REPORT_EXPORT,
    "incident_report_export_failed": AuditAction.INCIDENT_REPORT_EXPORT_FAILED,
    "analytics_export_sync": AuditAction.ANALYTICS_EXPORT_SYNC,
    "analytics_export_sync_failed": AuditAction.ANALYTICS_EXPORT_SYNC_FAILED,
    "analytics_export_requested": AuditAction.ANALYTICS_EXPORT_REQUESTED,
    "analytics_export_request_failed": AuditAction.ANALYTICS_EXPORT_REQUEST_FAILED,
    "analytics_export_downloaded": AuditAction.ANALYTICS_EXPORT_DOWNLOADED,
    "analytics_export_job_completed": AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED,
    "analytics_export_job_failed": AuditAction.ANALYTICS_EXPORT_JOB_FAILED,
}


EXPORT_ACTION_VALUES = frozenset(EXPORT_ACTIONS.values())

