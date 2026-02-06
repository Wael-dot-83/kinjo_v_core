"""
Compare models.py table/column definitions against actual SQLite database schema.
Reports any columns defined in the model but missing from the database.
"""
import sqlite3
import sys

DB_PATH = r"E:\KInjov2\data\kinjo.db"

# All tables and their expected columns extracted from models.py
MODEL_TABLES = {
    "kindergartens": [
        "id", "name_ar", "name_en", "governorate", "city", "area",
        "address_line", "contact_phone", "contact_email", "status",
        "operating_hours_start", "operating_hours_end", "license_number",
        "license_valid_until", "created_at", "updated_at"
    ],
    "users": [
        "id", "username", "email", "hashed_password", "role", "status",
        "kindergarten_id", "created_at", "updated_at"
    ],
    "password_reset_tokens": [
        "id", "user_id", "token", "expires_at", "used", "created_at"
    ],
    "parent_profiles": [
        "id", "user_id", "first_name", "second_name", "last_name",
        "first_name_en", "last_name_en", "phone_number", "gender",
        "nationality", "national_id", "passport_number",
        "home_governorate", "home_city", "home_area", "home_address_line",
        "work_address", "correspondence_preference",
        "profile_complete", "profile_completed_at",
        "created_at", "updated_at"
    ],
    "children": [
        "id", "parent_id", "first_name", "last_name", "gender",
        "date_of_birth", "father_name", "mother_first_name",
        "mother_second_name", "mother_last_name", "mother_nationality",
        "mother_national_id", "mother_passport_number", "media_consent",
        "correspondence_flag", "profile_complete", "profile_completed_at",
        "created_at", "updated_at"
    ],
    "classes": [
        "id", "kindergarten_id", "name_ar", "name_en", "capacity_total",
        "min_age_months", "max_age_months", "is_active", "created_at", "updated_at"
    ],
    "supervisor_assignments": [
        "id", "class_id", "supervisor_id", "is_primary", "start_date",
        "end_date", "created_at", "updated_at"
    ],
    "kindergarten_services": [
        "id", "kindergarten_id", "service_name", "description",
        "enabled_flag", "created_at", "updated_at"
    ],
    "operating_calendar": [
        "id", "kindergarten_id", "date", "is_open", "reason", "created_at"
    ],
    "enrollment_applications": [
        "id", "child_id", "kindergarten_id", "class_id", "status",
        "status_reason", "source", "submitted_at", "decision_by",
        "decision_at", "enrollment_start_date", "enrollment_end_date",
        "class_assignment_date", "created_at", "updated_at"
    ],
    "waitlist_entries": [
        "id", "enrollment_id", "status", "priority_score",
        "offer_sent_at", "offer_expiry_at", "created_at", "updated_at"
    ],
    "attendance_logs": [
        "id", "child_id", "date", "check_in_at", "check_out_at",
        "method", "dropped_by_name", "picked_by_name", "created_at"
    ],
    "daily_reports": [
        "id", "child_id", "date", "status", "submitted_by", "submitted_at",
        "approved_by", "approved_at", "arrival_time", "leave_time",
        "breakfast", "snack", "milk", "lunch", "nap_start", "nap_end",
        "nap_duration_minutes", "activities", "notes", "created_at", "updated_at"
    ],
    "incidents": [
        "id", "child_id", "kindergarten_id", "type", "severity_level",
        "description", "occurred_at", "notify_parent_at",
        "followup_required_flag", "followup_sla_deadline", "closed_at",
        "created_at", "updated_at"
    ],
    "observations": [
        "id", "child_id", "observed_by", "domain", "observation_text",
        "mastery_level", "observed_at", "created_at"
    ],
    "portfolios": [
        "id", "child_id", "title", "description", "status",
        "published_at", "parent_viewed_at", "created_at"
    ],
    "health_alerts": [
        "id", "child_id", "alert_type", "description", "severity",
        "created_at", "updated_at"
    ],
    "messages": [
        "id", "thread_type", "sender_id", "recipient_id", "thread_id",
        "reply_to_id", "kindergarten_id", "subject", "message_body",
        "allow_replies", "target_mode", "target_roles",
        "target_governorates", "target_kindergarten_ids", "target_search",
        "recipient_count", "translated_text", "created_at"
    ],
    "message_recipients": [
        "id", "message_id", "recipient_user_id", "delivered_at",
        "read_at", "status", "created_at"
    ],
    "message_user_states": [
        "id", "message_id", "user_id", "read_at", "archived_at",
        "deleted_at", "created_at"
    ],
    "message_attachments": [
        "id", "message_id", "uploaded_by_id", "file_name", "content_type",
        "file_size", "storage_provider", "storage_key", "url",
        "deleted_at", "created_at"
    ],
    "user_device_tokens": [
        "id", "user_id", "token", "platform", "device_name",
        "is_active", "last_used_at", "created_at"
    ],
    "notifications": [
        "id", "user_id", "message_id", "channel", "status", "payload",
        "error_message", "created_at", "sent_at"
    ],
    "events": [
        "id", "kindergarten_id", "title", "description", "type",
        "start_at", "end_at", "requires_consent_flag", "created_at"
    ],
    "surveys": [
        "id", "kindergarten_id", "title", "description",
        "nps_question_enabled", "start_date", "end_date", "created_at"
    ],
    "survey_responses": [
        "id", "survey_id", "parent_id", "nps_score", "feedback_text", "created_at"
    ],
    "audit_logs": [
        "id", "user_id", "action", "entity_type", "entity_id",
        "details", "ip_address", "sensitivity_level", "created_at"
    ],
    "staff_presence_logs": [
        "id", "staff_id", "kindergarten_id", "date", "start_at",
        "end_at", "created_at"
    ],
    "ratio_compliance": [
        "id", "kindergarten_id", "date", "operating_minutes",
        "compliant_minutes", "staff_count_avg", "child_count_avg", "created_at"
    ],
    "kpi_snapshots": [
        "id", "kindergarten_id", "kpi_name", "kpi_value",
        "period_start", "period_end", "is_locked", "created_at"
    ],
    "governance_scores": [
        "id", "kindergarten_id", "period_start", "period_end",
        "governance_quality_index", "child_experience_index",
        "final_governance_score", "band", "created_at"
    ],
    "safeguarding_cases": [
        "id", "child_id", "kindergarten_id", "case_description",
        "opened_at", "escalated_at", "closed_at",
        "sla_escalation_deadline", "sla_closure_deadline",
        "created_at", "updated_at"
    ],
    "tasks": [
        "id", "kindergarten_id", "title", "description", "status",
        "priority", "assigned_to", "created_by", "due_date",
        "completed_at", "created_at", "updated_at"
    ],
    "training_modules": [
        "id", "name", "description", "is_mandatory", "created_at", "updated_at"
    ],
    "staff_training_completion": [
        "id", "user_id", "training_module_id", "kindergarten_id",
        "completion_date", "status", "created_at", "updated_at"
    ],
    "kpi_targets": [
        "id", "kpi_name", "target_value", "effective_date",
        "kindergarten_id", "created_at", "updated_at"
    ],
    "advanced_analytics_cache": [
        "id", "dimension_type", "dimension_id", "period_type",
        "period_start", "period_end",
        "attendance_rate", "chronic_absence_rate", "incident_rate_per_100",
        "serious_incident_rate", "ratio_compliance_rate", "report_completion_rate",
        "parent_satisfaction_nps", "child_development_index",
        "staff_turnover_rate", "regulatory_compliance_score",
        "attendance_trend_slope", "risk_score", "improvement_velocity",
        "attendance_incident_correlation", "staffing_quality_correlation",
        "health_alerts_count", "created_at", "updated_at"
    ],
    "analytics_dimension_cache": [
        "id", "dimension_type", "dimension_id", "period_type", "period_date",
        "total_capacity", "total_enrolled", "enrollment_rate", "pending_applications",
        "expected_attendance", "actual_attendance", "attendance_rate", "chronic_absence_count",
        "expected_reports", "submitted_reports", "report_completion_rate",
        "total_incidents", "high_severity_incidents", "incident_rate_per_100",
        "total_staff", "ratio_compliant_minutes", "ratio_total_minutes", "ratio_compliance_rate",
        "surveys_sent", "survey_responses", "survey_response_rate", "nps_score",
        "governance_quality_index", "child_experience_index", "final_governance_score",
        "created_at", "updated_at"
    ],
    "export_jobs": [
        "id", "user_id", "export_format", "report_type", "filters",
        "status", "file_path", "file_size", "error_message",
        "started_at", "completed_at", "created_at"
    ],
}


def get_db_columns(cursor, table_name):
    """Get actual column names from SQLite table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    rows = cursor.fetchall()
    return {row[1] for row in rows}  # row[1] is column name


def get_db_tables(cursor):
    """Get all table names from the database"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'")
    return {row[0] for row in cursor.fetchall()}


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    db_tables = get_db_tables(cursor)
    model_tables = set(MODEL_TABLES.keys())

    print("=" * 70)
    print("SCHEMA COMPARISON: models.py vs SQLite Database")
    print("=" * 70)

    # Tables in model but not in DB
    missing_tables = model_tables - db_tables
    if missing_tables:
        print(f"\n### TABLES IN MODEL BUT MISSING FROM DATABASE ({len(missing_tables)}):")
        for t in sorted(missing_tables):
            print(f"  - {t}")

    # Tables in DB but not in model
    extra_tables = db_tables - model_tables
    if extra_tables:
        print(f"\n### TABLES IN DATABASE BUT NOT IN MODEL ({len(extra_tables)}):")
        for t in sorted(extra_tables):
            print(f"  - {t}")

    # Column comparison for tables that exist in both
    common_tables = model_tables & db_tables
    tables_with_issues = 0
    total_missing_cols = 0
    total_extra_cols = 0

    print(f"\n### COLUMN COMPARISON ({len(common_tables)} tables in common):")
    print("-" * 70)

    for table_name in sorted(common_tables):
        model_cols = set(MODEL_TABLES[table_name])
        db_cols = get_db_columns(cursor, table_name)

        missing_from_db = model_cols - db_cols
        extra_in_db = db_cols - model_cols

        if missing_from_db or extra_in_db:
            tables_with_issues += 1
            print(f"\n  TABLE: {table_name}")
            if missing_from_db:
                total_missing_cols += len(missing_from_db)
                print(f"    MISSING from DB (in model but not in DB):")
                for col in sorted(missing_from_db):
                    print(f"      - {col}")
            if extra_in_db:
                total_extra_cols += len(extra_in_db)
                print(f"    EXTRA in DB (in DB but not in model):")
                for col in sorted(extra_in_db):
                    print(f"      + {col}")
        else:
            print(f"  TABLE: {table_name} -- OK (all {len(model_cols)} columns match)")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total model tables:       {len(model_tables)}")
    print(f"  Total DB tables:          {len(db_tables)}")
    print(f"  Tables missing from DB:   {len(missing_tables)}")
    print(f"  Extra tables in DB:       {len(extra_tables)}")
    print(f"  Tables with column diff:  {tables_with_issues}")
    print(f"  Total missing columns:    {total_missing_cols}")
    print(f"  Total extra DB columns:   {total_extra_cols}")

    conn.close()
    return 1 if missing_tables or total_missing_cols > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
