"""Production hardening: soft delete, audit JSONB, medical fields, missing columns,
capacity trigger, audit triggers, date checks, composite indexes, safeguarding status,
survey unique constraint, health severity check.

Revision ID: c1a2b3d4e5f6
Revises: f4b7a9c2d613
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "f4b7a9c2d613"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that need soft-delete columns
SOFT_DELETE_TABLES = [
    "users",
    "parent_profiles",
    "children",
    "classes",
    "enrollment_applications",
    "kindergarten_services",
    "supervisor_assignments",
    "surveys",
    "events",
    "tasks",
    "attendance_logs",
]

# Sensitive tables that need audit triggers
AUDIT_TRIGGER_TABLES = [
    "children",
    "parent_profiles",
    "enrollment_applications",
    "incidents",
    "safeguarding_cases",
    "health_alerts",
    "attendance_logs",
    "daily_reports",
    "users",
]


def _add_fk_column(
    table_name: str,
    column_name: str,
    target: str,
    *,
    nullable: bool = True,
) -> None:
    ref_table, ref_column = target.split(".", 1)
    add_fk_column_sqlite_safe(
        table_name,
        column_name,
        ref_table,
        ref_column,
        sa.Integer(),
        nullable=nullable,
    )


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if not _column_exists(table_name, column_name):
        return
    if _dialect_name() == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_column(column_name)
    else:
        op.drop_column(table_name, column_name)


def _unique_or_index_exists(table_name: str, name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    unique_constraints = inspector.get_unique_constraints(table_name)
    indexes = inspector.get_indexes(table_name)
    return any(item["name"] == name for item in unique_constraints + indexes)


def _foreign_key_exists(
    table_name: str,
    column_name: str,
    ref_table: str,
    ref_column: str,
    constraint_name: str,
) -> bool:
    if not _table_exists(table_name):
        return False
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name):
        if fk.get("name") == constraint_name:
            return True
        if (
            fk.get("constrained_columns") == [column_name]
            and fk.get("referred_table") == ref_table
            and fk.get("referred_columns") == [ref_column]
        ):
            return True
    return False


def _fk_name(table_name: str, column_name: str, ref_table: str) -> str:
    return f"fk_{table_name}_{column_name}_{ref_table}"


def _added_fk_specs() -> list[tuple[str, str, str, str, str]]:
    specs = [
        (
            table,
            "deleted_by",
            "users",
            "id",
            _fk_name(table, "deleted_by", "users"),
        )
        for table in SOFT_DELETE_TABLES
    ]
    specs.extend([
        ("attendance_logs", "class_id", "classes", "id", "fk_attendance_class"),
        ("incidents", "reported_by", "users", "id", _fk_name("incidents", "reported_by", "users")),
        ("incidents", "class_id", "classes", "id", _fk_name("incidents", "class_id", "classes")),
        ("incidents", "closed_by", "users", "id", _fk_name("incidents", "closed_by", "users")),
        ("incidents", "deleted_by", "users", "id", _fk_name("incidents", "deleted_by", "users")),
        ("messages", "recipient_id", "users", "id", _fk_name("messages", "recipient_id", "users")),
        (
            "safeguarding_cases",
            "assigned_to",
            "users",
            "id",
            _fk_name("safeguarding_cases", "assigned_to", "users"),
        ),
    ])
    return specs


def _create_foreign_key_sqlite_safe(
    table_name: str,
    column_name: str,
    ref_table: str,
    ref_column: str,
    *,
    constraint_name: str | None = None,
    ondelete: str | None = None,
) -> None:
    """Create an FK, using Alembic batch mode for SQLite table rebuilds."""
    constraint_name = constraint_name or _fk_name(table_name, column_name, ref_table)
    if _foreign_key_exists(table_name, column_name, ref_table, ref_column, constraint_name):
        return

    if _dialect_name() == "sqlite":
        # SQLite cannot ALTER TABLE ADD CONSTRAINT. Alembic batch mode creates a
        # replacement table with the FK, copies data, and swaps it into place.
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                ref_table,
                [column_name],
                [ref_column],
                ondelete=ondelete,
            )
    else:
        op.create_foreign_key(
            constraint_name,
            table_name,
            ref_table,
            [column_name],
            [ref_column],
            ondelete=ondelete,
        )


def _drop_foreign_key_sqlite_safe(
    table_name: str,
    column_name: str,
    ref_table: str,
    ref_column: str,
    *,
    constraint_name: str | None = None,
) -> None:
    constraint_name = constraint_name or _fk_name(table_name, column_name, ref_table)
    if not _foreign_key_exists(table_name, column_name, ref_table, ref_column, constraint_name):
        return

    if _dialect_name() == "sqlite":
        # All SQLite FKs added by this migration are on columns removed below;
        # dropping the column through batch mode removes the FK in the same
        # rebuild and avoids name-reflection differences across SQLite builds.
        return
    else:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def add_fk_column_sqlite_safe(
    table_name: str,
    column_name: str,
    ref_table: str,
    ref_column: str,
    type_: sa.types.TypeEngine,
    nullable: bool = True,
    *,
    constraint_name: str | None = None,
    create_constraint: bool = True,
    ondelete: str | None = None,
    **kwargs,
) -> None:
    """Add an FK column portably across PostgreSQL and SQLite.

    PostgreSQL supports adding constraints directly. SQLite does not support
    ALTER TABLE ADD CONSTRAINT, so the column is added first and the FK is added
    through batch mode, which rebuilds the table internally. Callers can set
    create_constraint=False when they need to backfill before adding the FK.
    """
    _add_column_if_missing(
        table_name,
        sa.Column(column_name, type_, nullable=nullable, **kwargs),
    )
    if create_constraint:
        _create_foreign_key_sqlite_safe(
            table_name,
            column_name,
            ref_table,
            ref_column,
            constraint_name=constraint_name,
            ondelete=ondelete,
        )


def _ensure_survey_responses_table() -> None:
    if _table_exists("survey_responses"):
        return

    op.create_table(
        "survey_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("nps_score", sa.Integer(), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["survey_id"], ["surveys.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    if not _unique_or_index_exists("survey_responses", op.f("ix_survey_responses_id")):
        op.create_index(op.f("ix_survey_responses_id"), "survey_responses", ["id"])


def _deduplicate_survey_responses() -> None:
    """Keep the oldest response per (survey_id, parent_id) before uniqueness."""
    if not _table_exists("survey_responses"):
        return

    survey_responses = sa.table(
        "survey_responses",
        sa.column("id", sa.Integer()),
        sa.column("survey_id", sa.Integer()),
        sa.column("parent_id", sa.Integer()),
    )
    rows = op.get_bind().execute(
        sa.select(
            survey_responses.c.id,
            survey_responses.c.survey_id,
            survey_responses.c.parent_id,
        ).order_by(
            survey_responses.c.survey_id,
            survey_responses.c.parent_id,
            survey_responses.c.id,
        )
    ).mappings()

    seen: set[tuple[int, int]] = set()
    duplicate_ids: list[int] = []
    for row in rows:
        key = (row["survey_id"], row["parent_id"])
        if key in seen:
            duplicate_ids.append(row["id"])
        else:
            seen.add(key)

    if duplicate_ids:
        op.get_bind().execute(
            survey_responses.delete().where(survey_responses.c.id.in_(duplicate_ids))
        )


def _backfill_attendance_class_id() -> None:
    attendance_logs = sa.table(
        "attendance_logs",
        sa.column("child_id", sa.Integer()),
        sa.column("class_id", sa.Integer()),
    )
    enrollments = sa.table(
        "enrollment_applications",
        sa.column("child_id", sa.Integer()),
        sa.column("class_id", sa.Integer()),
        sa.column("status", sa.String()),
    )
    active_class = (
        sa.select(enrollments.c.class_id)
        .where(
            enrollments.c.child_id == attendance_logs.c.child_id,
            enrollments.c.status == "ACTIVE",
            enrollments.c.class_id.is_not(None),
        )
        .limit(1)
        .scalar_subquery()
    )

    op.get_bind().execute(
        attendance_logs.update()
        .where(attendance_logs.c.class_id.is_(None))
        .values(class_id=active_class)
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # -------------------------------------------------------------------------
    # 1. Soft-delete columns on all core entities
    # -------------------------------------------------------------------------
    for table in SOFT_DELETE_TABLES:
        _add_column_if_missing(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        _add_fk_column(table, "deleted_by", "users.id")

    # -------------------------------------------------------------------------
    # 2. Audit log: add JSONB columns + convert details from TEXT to JSON
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS old_data JSONB")
        op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS new_data JSONB")
        op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_role VARCHAR(50)")
        op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id UUID")
        # Convert details column from TEXT to JSONB (cast existing text as JSON)
        op.execute("""
            ALTER TABLE audit_logs
                ALTER COLUMN details TYPE JSONB
                USING CASE
                    WHEN details IS NULL THEN NULL
                    WHEN details ~ '^\\s*[{\\[]' THEN details::JSONB
                    ELSE to_jsonb(details)
                END
        """)
    else:
        _add_column_if_missing("audit_logs", sa.Column("old_data", sa.JSON(), nullable=True))
        _add_column_if_missing("audit_logs", sa.Column("new_data", sa.JSON(), nullable=True))
        _add_column_if_missing("audit_logs", sa.Column("actor_role", sa.String(50), nullable=True))
        _add_column_if_missing("audit_logs", sa.Column("request_id", sa.String(36), nullable=True))

    # -------------------------------------------------------------------------
    # 3. Children: medical / allergy / emergency profile columns
    # -------------------------------------------------------------------------
    _add_column_if_missing("children", sa.Column("medical_notes", sa.Text(), nullable=True))
    _add_column_if_missing("children", sa.Column("allergy_notes", sa.Text(), nullable=True))
    _add_column_if_missing("children", sa.Column("special_needs_notes", sa.Text(), nullable=True))
    _add_column_if_missing("children", sa.Column("emergency_contact_name", sa.String(255), nullable=True))
    _add_column_if_missing("children", sa.Column("emergency_contact_phone", sa.String(20), nullable=True))
    _add_column_if_missing("children", sa.Column("blood_type", sa.String(5), nullable=True))
    _add_column_if_missing("children", sa.Column("vaccination_up_to_date", sa.Boolean(), nullable=True))

    # -------------------------------------------------------------------------
    # 4. Attendance logs: class_id FK
    # -------------------------------------------------------------------------
    add_fk_column_sqlite_safe(
        "attendance_logs",
        "class_id",
        "classes",
        "id",
        sa.Integer(),
        nullable=True,
        constraint_name="fk_attendance_class",
        create_constraint=False,
        ondelete="SET NULL",
    )
    # Backfill before adding the FK so SQLite batch-copy validation and
    # PostgreSQL constraint creation both see clean data.
    _backfill_attendance_class_id()
    _create_foreign_key_sqlite_safe(
        "attendance_logs",
        "class_id",
        "classes",
        "id",
        constraint_name="fk_attendance_class",
        ondelete="SET NULL",
    )

    # -------------------------------------------------------------------------
    # 5. Incidents: add reported_by, class_id, closed_by
    # -------------------------------------------------------------------------
    _add_fk_column("incidents", "reported_by", "users.id")
    _add_fk_column("incidents", "class_id", "classes.id")
    _add_fk_column("incidents", "closed_by", "users.id")
    _add_column_if_missing("incidents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    _add_fk_column("incidents", "deleted_by", "users.id")

    # -------------------------------------------------------------------------
    # 6. Messages: direct recipient + read tracking
    # -------------------------------------------------------------------------
    add_fk_column_sqlite_safe(
        "messages",
        "recipient_id",
        "users",
        "id",
        sa.Integer(),
        nullable=True,
    )
    _add_column_if_missing("messages", sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"))
    _add_column_if_missing("messages", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))

    # -------------------------------------------------------------------------
    # 7. HealthAlert: severity constrained to known values
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            ALTER TABLE health_alerts
                ADD CONSTRAINT ck_health_alert_severity
                CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL'))
        """)

    # -------------------------------------------------------------------------
    # 8. SurveyResponse: unique per parent per survey
    # -------------------------------------------------------------------------
    _ensure_survey_responses_table()
    _deduplicate_survey_responses()
    if not _unique_or_index_exists("survey_responses", "uq_survey_response_per_parent"):
        if dialect == "sqlite":
            op.create_index(
                "uq_survey_response_per_parent",
                "survey_responses",
                ["survey_id", "parent_id"],
                unique=True,
            )
        else:
            op.create_unique_constraint(
                "uq_survey_response_per_parent",
                "survey_responses",
                ["survey_id", "parent_id"]
            )

    # -------------------------------------------------------------------------
    # 9. SafeguardingCase: add status enum + assigned_to
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'safeguardingstatus') THEN
                    CREATE TYPE safeguardingstatus AS ENUM (
                        'OPEN',
                        'UNDER_INVESTIGATION',
                        'ESCALATED',
                        'PENDING_CLOSURE',
                        'CLOSED'
                    );
                END IF;
            END$$;
        """)
        op.execute("""
            ALTER TABLE safeguarding_cases
                ADD COLUMN IF NOT EXISTS status safeguardingstatus NOT NULL DEFAULT 'OPEN'
        """)
        add_fk_column_sqlite_safe(
            "safeguarding_cases",
            "assigned_to",
            "users",
            "id",
            sa.Integer(),
            nullable=True,
        )
        # Backfill: cases with closed_at get CLOSED, cases with escalated_at get ESCALATED
        op.execute("""
            UPDATE safeguarding_cases
            SET status = CASE
                WHEN closed_at IS NOT NULL THEN 'CLOSED'::safeguardingstatus
                WHEN escalated_at IS NOT NULL THEN 'ESCALATED'::safeguardingstatus
                ELSE 'OPEN'::safeguardingstatus
            END
        """)
    else:
        _add_column_if_missing("safeguarding_cases", sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"))
        _add_fk_column("safeguarding_cases", "assigned_to", "users.id")

    # -------------------------------------------------------------------------
    # 10. Enrollment applications: partial unique index (no duplicate ACTIVE enrolment)
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_enrollment_unique_active
                ON enrollment_applications(child_id, class_id)
                WHERE status = 'ACTIVE'
        """)

    # -------------------------------------------------------------------------
    # 11. Future-date CHECK constraints
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            ALTER TABLE attendance_logs
                ADD CONSTRAINT ck_attendance_not_future
                CHECK (date <= CURRENT_DATE)
        """)
        op.execute("""
            ALTER TABLE daily_reports
                ADD CONSTRAINT ck_report_not_future
                CHECK (date <= CURRENT_DATE)
        """)
        # Time-string format checks on daily_reports
        op.execute(r"""
            ALTER TABLE daily_reports
                ADD CONSTRAINT ck_arrival_time_format
                CHECK (arrival_time IS NULL OR arrival_time ~ '^([01]\d|2[0-3]):[0-5]\d$'),
                ADD CONSTRAINT ck_leave_time_format
                CHECK (leave_time IS NULL OR leave_time ~ '^([01]\d|2[0-3]):[0-5]\d$'),
                ADD CONSTRAINT ck_nap_start_format
                CHECK (nap_start IS NULL OR nap_start ~ '^([01]\d|2[0-3]):[0-5]\d$'),
                ADD CONSTRAINT ck_nap_end_format
                CHECK (nap_end IS NULL OR nap_end ~ '^([01]\d|2[0-3]):[0-5]\d$')
        """)

    # -------------------------------------------------------------------------
    # 12. Composite performance indexes
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        index_ddl = [
            "CREATE INDEX IF NOT EXISTS idx_attendance_child_date ON attendance_logs(child_id, date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_class_date ON attendance_logs(class_id, date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_incidents_kg_occurred ON incidents(kindergarten_id, occurred_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_incidents_child ON incidents(child_id, occurred_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, is_read, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_safeguarding_status ON safeguarding_cases(kindergarten_id, status, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_health_alerts_child ON health_alerts(child_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_waitlist_expiry ON waitlist_entries(offer_expiry_at) WHERE status = 'WAITLISTED'",
            "CREATE INDEX IF NOT EXISTS idx_enrollment_child_status ON enrollment_applications(child_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_ratio_compliance_kg_date ON ratio_compliance(kindergarten_id, date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id, created_at DESC)",
        ]
        for ddl in index_ddl:
            op.execute(ddl)

    # -------------------------------------------------------------------------
    # 13. Soft-delete partial indexes (exclude deleted rows from default lookups)
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        for table in SOFT_DELETE_TABLES + ["incidents"]:
            op.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_not_deleted "
                f"ON {table}(id) WHERE deleted_at IS NULL"
            )

    # -------------------------------------------------------------------------
    # 14. Class capacity enforcement trigger
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION enforce_class_capacity()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            DECLARE
                v_capacity  INTEGER;
                v_enrolled  INTEGER;
            BEGIN
                IF NEW.status = 'ACTIVE' THEN
                    SELECT capacity_total INTO v_capacity
                    FROM classes
                    WHERE id = NEW.class_id
                    FOR UPDATE;

                    SELECT COUNT(*) INTO v_enrolled
                    FROM enrollment_applications
                    WHERE class_id = NEW.class_id
                      AND status   = 'ACTIVE'
                      AND id       != NEW.id;

                    IF v_enrolled >= v_capacity THEN
                        RAISE EXCEPTION
                            'Class % has reached its capacity of % students',
                            NEW.class_id, v_capacity;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$;
        """)
        op.execute("""
            DROP TRIGGER IF EXISTS trg_enforce_class_capacity
                ON enrollment_applications;
            CREATE TRIGGER trg_enforce_class_capacity
                BEFORE INSERT OR UPDATE ON enrollment_applications
                FOR EACH ROW EXECUTE FUNCTION enforce_class_capacity();
        """)

    # -------------------------------------------------------------------------
    # 15. Audit trail triggers for sensitive tables
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION log_row_change()
            RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
            DECLARE
                v_user_id   INTEGER;
                v_actor_role TEXT;
                v_request_id UUID;
            BEGIN
                -- Retrieve session-level hints set by the application layer
                BEGIN
                    v_user_id    := current_setting('app.current_user_id', true)::INTEGER;
                EXCEPTION WHEN OTHERS THEN
                    v_user_id := NULL;
                END;
                BEGIN
                    v_actor_role := current_setting('app.current_user_role', true);
                EXCEPTION WHEN OTHERS THEN
                    v_actor_role := NULL;
                END;
                BEGIN
                    v_request_id := current_setting('app.request_id', true)::UUID;
                EXCEPTION WHEN OTHERS THEN
                    v_request_id := NULL;
                END;

                INSERT INTO audit_logs (
                    user_id, action, entity_type, entity_id,
                    old_data, new_data, actor_role, request_id,
                    ip_address, sensitivity_level, created_at
                ) VALUES (
                    v_user_id,
                    TG_OP,
                    TG_TABLE_NAME,
                    COALESCE(NEW.id, OLD.id),
                    CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
                    CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END,
                    v_actor_role,
                    v_request_id,
                    NULL,
                    3,
                    NOW()
                );
                RETURN COALESCE(NEW, OLD);
            END;
            $$;
        """)
        for tbl in AUDIT_TRIGGER_TABLES:
            op.execute(f"""
                DROP TRIGGER IF EXISTS trg_audit_{tbl} ON {tbl};
                CREATE TRIGGER trg_audit_{tbl}
                    AFTER INSERT OR UPDATE OR DELETE ON {tbl}
                    FOR EACH ROW EXECUTE FUNCTION log_row_change();
            """)

    # -------------------------------------------------------------------------
    # 16. Active-record views (soft-delete aware)
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            CREATE OR REPLACE VIEW active_children AS
                SELECT * FROM children WHERE deleted_at IS NULL;
            CREATE OR REPLACE VIEW active_classes AS
                SELECT * FROM classes WHERE deleted_at IS NULL;
            CREATE OR REPLACE VIEW active_enrollments AS
                SELECT * FROM enrollment_applications
                WHERE deleted_at IS NULL AND status = 'ACTIVE';
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Drop views
        op.execute("DROP VIEW IF EXISTS active_children")
        op.execute("DROP VIEW IF EXISTS active_classes")
        op.execute("DROP VIEW IF EXISTS active_enrollments")

        # Drop triggers and function
        for tbl in AUDIT_TRIGGER_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{tbl} ON {tbl}")
        op.execute("DROP FUNCTION IF EXISTS log_row_change()")
        op.execute("DROP TRIGGER IF EXISTS trg_enforce_class_capacity ON enrollment_applications")
        op.execute("DROP FUNCTION IF EXISTS enforce_class_capacity()")

        # Drop partial indexes
        for table in SOFT_DELETE_TABLES + ["incidents"]:
            op.execute(f"DROP INDEX IF EXISTS idx_{table}_not_deleted")
        op.execute("DROP INDEX IF EXISTS idx_enrollment_unique_active")

        # Drop composite indexes
        for idx in [
            "idx_attendance_child_date", "idx_attendance_class_date",
            "idx_incidents_kg_occurred", "idx_incidents_child",
            "idx_messages_sender", "idx_messages_recipient",
            "idx_safeguarding_status", "idx_health_alerts_child",
            "idx_waitlist_expiry", "idx_enrollment_child_status",
            "idx_ratio_compliance_kg_date", "idx_audit_logs_entity",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # Drop constraints
        op.execute("ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_not_future")
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_report_not_future")
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_arrival_time_format")
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_leave_time_format")
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_nap_start_format")
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_nap_end_format")
        op.execute("ALTER TABLE health_alerts DROP CONSTRAINT IF EXISTS ck_health_alert_severity")

    for table_name, column_name, ref_table, ref_column, constraint_name in _added_fk_specs():
        _drop_foreign_key_sqlite_safe(
            table_name,
            column_name,
            ref_table,
            ref_column,
            constraint_name=constraint_name,
        )

    # Drop added columns
    if _table_exists("survey_responses") and _unique_or_index_exists(
        "survey_responses",
        "uq_survey_response_per_parent",
    ):
        if dialect == "sqlite":
            op.drop_index("uq_survey_response_per_parent", table_name="survey_responses")
        else:
            op.drop_constraint("uq_survey_response_per_parent", "survey_responses", type_="unique")
    if _table_exists("survey_responses"):
        op.drop_table("survey_responses")

    _drop_column_if_exists("messages", "read_at")
    _drop_column_if_exists("messages", "is_read")
    _drop_column_if_exists("messages", "recipient_id")
    _drop_column_if_exists("incidents", "deleted_by")
    _drop_column_if_exists("incidents", "deleted_at")
    _drop_column_if_exists("incidents", "closed_by")
    _drop_column_if_exists("incidents", "class_id")
    _drop_column_if_exists("incidents", "reported_by")
    _drop_column_if_exists("attendance_logs", "class_id")
    _drop_column_if_exists("children", "vaccination_up_to_date")
    _drop_column_if_exists("children", "blood_type")
    _drop_column_if_exists("children", "emergency_contact_phone")
    _drop_column_if_exists("children", "emergency_contact_name")
    _drop_column_if_exists("children", "special_needs_notes")
    _drop_column_if_exists("children", "allergy_notes")
    _drop_column_if_exists("children", "medical_notes")
    _drop_column_if_exists("audit_logs", "request_id")
    _drop_column_if_exists("audit_logs", "actor_role")
    _drop_column_if_exists("audit_logs", "new_data")
    _drop_column_if_exists("audit_logs", "old_data")
    _drop_column_if_exists("safeguarding_cases", "assigned_to")
    _drop_column_if_exists("safeguarding_cases", "status")

    for table in SOFT_DELETE_TABLES:
        _drop_column_if_exists(table, "deleted_by")
        _drop_column_if_exists(table, "deleted_at")

    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS safeguardingstatus")
