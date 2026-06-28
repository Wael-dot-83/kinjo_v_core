"""add_new_kpi_governance_models

Revision ID: c17d2043714e
Revises: kpi_p0_idx_001
Create Date: 2026-06-24 20:53:16.202399

Adds new models for KPI governance enhancement:
- financial_records
- development_assessments
- individualized_learning_plans
- accessibility_audits
- communication_events
- portal_logins

Restored from compiled bytecode (.pyc) — source file was removed when the
governance expansion was isolated to a separate branch (stash@{0}).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c17d2043714e"
down_revision = "kpi_p0_idx_001"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def upgrade() -> None:
    if _dialect_name() == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_generic()


def _upgrade_sqlite() -> None:
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}

    if "financial_records" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE financial_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kindergarten_id INTEGER NOT NULL,
                record_type VARCHAR(20) NOT NULL,
                amount FLOAT NOT NULL,
                currency VARCHAR(3) NOT NULL DEFAULT 'JOD',
                description TEXT,
                recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                period_start DATE,
                period_end DATE,
                created_by INTEGER,
                deleted_at DATETIME,
                deleted_by INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id),
                FOREIGN KEY(created_by) REFERENCES users(id),
                FOREIGN KEY(deleted_by) REFERENCES users(id)
            )
        """))
        conn.execute(sa.text("CREATE INDEX ix_financial_records_kg_type ON financial_records(kindergarten_id, record_type)"))
        conn.execute(sa.text("CREATE INDEX ix_financial_records_recorded_at ON financial_records(recorded_at)"))

    if "development_assessments" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE development_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_id INTEGER NOT NULL,
                kindergarten_id INTEGER NOT NULL,
                domain VARCHAR(20) NOT NULL,
                milestone_code VARCHAR(50) NOT NULL,
                milestone_description TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'NOT_STARTED',
                assessed_at DATE NOT NULL,
                assessed_by INTEGER,
                notes TEXT,
                updated_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(child_id) REFERENCES children(id),
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id),
                FOREIGN KEY(assessed_by) REFERENCES users(id)
            )
        """))
        conn.execute(sa.text("CREATE UNIQUE INDEX uq_dev_assessment_child_milestone_date ON development_assessments(child_id, milestone_code, assessed_at)"))
        conn.execute(sa.text("CREATE INDEX ix_dev_assessments_child ON development_assessments(child_id)"))
        conn.execute(sa.text("CREATE INDEX ix_dev_assessments_kg ON development_assessments(kindergarten_id)"))
        conn.execute(sa.text("CREATE INDEX ix_dev_assessments_domain ON development_assessments(domain)"))

    if "individualized_learning_plans" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE individualized_learning_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_id INTEGER NOT NULL,
                kindergarten_id INTEGER NOT NULL,
                plan_document TEXT,
                goals JSON,
                start_date DATE NOT NULL,
                end_date DATE,
                status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
                created_by INTEGER,
                reviewed_by INTEGER,
                reviewed_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY(child_id) REFERENCES children(id),
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id),
                FOREIGN KEY(created_by) REFERENCES users(id),
                FOREIGN KEY(reviewed_by) REFERENCES users(id)
            )
        """))
        conn.execute(sa.text("CREATE INDEX ix_ilp_child ON individualized_learning_plans(child_id)"))
        conn.execute(sa.text("CREATE INDEX ix_ilp_kg ON individualized_learning_plans(kindergarten_id)"))
        conn.execute(sa.text("CREATE INDEX ix_ilp_status ON individualized_learning_plans(status)"))

    if "accessibility_audits" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE accessibility_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kindergarten_id INTEGER NOT NULL,
                criteria_code VARCHAR(50) NOT NULL,
                criteria_description TEXT,
                is_compliant BOOLEAN NOT NULL DEFAULT 0,
                evidence_notes TEXT,
                audited_at DATE NOT NULL,
                audited_by INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id),
                FOREIGN KEY(audited_by) REFERENCES users(id)
            )
        """))
        conn.execute(sa.text("CREATE UNIQUE INDEX uq_access_audit_kg_criteria_date ON accessibility_audits(kindergarten_id, criteria_code, audited_at)"))
        conn.execute(sa.text("CREATE INDEX ix_access_audits_kg ON accessibility_audits(kindergarten_id)"))
        conn.execute(sa.text("CREATE INDEX ix_access_audits_criteria ON accessibility_audits(criteria_code)"))

    if "communication_events" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE communication_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kindergarten_id INTEGER NOT NULL,
                message_id INTEGER,
                parent_user_id INTEGER,
                staff_user_id INTEGER,
                direction VARCHAR(20) NOT NULL,
                sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                responded_at DATETIME,
                response_language VARCHAR(10),
                parent_preferred_language VARCHAR(10),
                is_translated BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id),
                FOREIGN KEY(message_id) REFERENCES messages(id),
                FOREIGN KEY(parent_user_id) REFERENCES users(id),
                FOREIGN KEY(staff_user_id) REFERENCES users(id)
            )
        """))
        conn.execute(sa.text("CREATE INDEX ix_comm_events_kg ON communication_events(kindergarten_id)"))
        conn.execute(sa.text("CREATE INDEX ix_comm_events_parent ON communication_events(parent_user_id)"))
        conn.execute(sa.text("CREATE INDEX ix_comm_events_staff ON communication_events(staff_user_id)"))
        conn.execute(sa.text("CREATE INDEX ix_comm_events_sent_at ON communication_events(sent_at)"))

    if "portal_logins" not in existing:
        conn.execute(sa.text("""
            CREATE TABLE portal_logins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kindergarten_id INTEGER,
                logged_in_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ip_address VARCHAR(50),
                user_agent VARCHAR(255),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(kindergarten_id) REFERENCES kindergartens(id)
            )
        """))
        conn.execute(sa.text("CREATE INDEX ix_portal_logins_user ON portal_logins(user_id)"))
        conn.execute(sa.text("CREATE INDEX ix_portal_logins_kg ON portal_logins(kindergarten_id)"))
        conn.execute(sa.text("CREATE INDEX ix_portal_logins_logged_in_at ON portal_logins(logged_in_at)"))


def _upgrade_generic() -> None:
    """PostgreSQL / generic SQLAlchemy upgrade."""
    dialect = _dialect_name()

    financial_record_type = postgresql.ENUM(
        "TUITION_PAYMENT", "OPERATING_EXPENSE", "REVENUE", "ADJUSTMENT",
        name="financialrecordtype", create_type=False,
    ) if dialect == "postgresql" else sa.String(20)
    if dialect == "postgresql":
        op.execute("CREATE TYPE IF NOT EXISTS financialrecordtype AS ENUM ('TUITION_PAYMENT','OPERATING_EXPENSE','REVENUE','ADJUSTMENT')")

    op.create_table(
        "financial_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("record_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="JOD"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_financial_records_kg_type", "financial_records", ["kindergarten_id", "record_type"])
    op.create_index("ix_financial_records_recorded_at", "financial_records", ["recorded_at"])

    learning_domain = sa.String(20)
    milestone_status = sa.String(20)

    op.create_table(
        "development_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("domain", learning_domain, nullable=False),
        sa.Column("milestone_code", sa.String(50), nullable=False),
        sa.Column("milestone_description", sa.Text(), nullable=True),
        sa.Column("status", milestone_status, nullable=False, server_default="NOT_STARTED"),
        sa.Column("assessed_at", sa.Date(), nullable=False),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("uq_dev_assessment_child_milestone_date", "development_assessments", ["child_id", "milestone_code", "assessed_at"], unique=True)
    op.create_index("ix_dev_assessments_child", "development_assessments", ["child_id"])
    op.create_index("ix_dev_assessments_kg", "development_assessments", ["kindergarten_id"])
    op.create_index("ix_dev_assessments_domain", "development_assessments", ["domain"])

    ilp_status = sa.String(20)

    op.create_table(
        "individualized_learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("plan_document", sa.Text(), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", ilp_status, nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ilp_child", "individualized_learning_plans", ["child_id"])
    op.create_index("ix_ilp_kg", "individualized_learning_plans", ["kindergarten_id"])
    op.create_index("ix_ilp_status", "individualized_learning_plans", ["status"])

    op.create_table(
        "accessibility_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("criteria_code", sa.String(50), nullable=False),
        sa.Column("criteria_description", sa.Text(), nullable=True),
        sa.Column("is_compliant", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("evidence_notes", sa.Text(), nullable=True),
        sa.Column("audited_at", sa.Date(), nullable=False),
        sa.Column("audited_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("uq_access_audit_kg_criteria_date", "accessibility_audits", ["kindergarten_id", "criteria_code", "audited_at"], unique=True)
    op.create_index("ix_access_audits_kg", "accessibility_audits", ["kindergarten_id"])
    op.create_index("ix_access_audits_criteria", "accessibility_audits", ["criteria_code"])

    comm_direction = sa.String(20)

    op.create_table(
        "communication_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("parent_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("direction", comm_direction, nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("response_language", sa.String(10), nullable=True),
        sa.Column("parent_preferred_language", sa.String(10), nullable=True),
        sa.Column("is_translated", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_comm_events_kg", "communication_events", ["kindergarten_id"])
    op.create_index("ix_comm_events_parent", "communication_events", ["parent_user_id"])
    op.create_index("ix_comm_events_staff", "communication_events", ["staff_user_id"])
    op.create_index("ix_comm_events_sent_at", "communication_events", ["sent_at"])

    op.create_table(
        "portal_logins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=True),
        sa.Column("logged_in_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_portal_logins_user", "portal_logins", ["user_id"])
    op.create_index("ix_portal_logins_kg", "portal_logins", ["kindergarten_id"])
    op.create_index("ix_portal_logins_logged_in_at", "portal_logins", ["logged_in_at"])


def downgrade() -> None:
    if _dialect_name() == "sqlite":
        conn = op.get_bind()
        existing = {r[0] for r in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}

    for idx, tbl in [
        ("ix_portal_logins_logged_in_at", "portal_logins"),
        ("ix_portal_logins_kg", "portal_logins"),
        ("ix_portal_logins_user", "portal_logins"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("portal_logins", if_exists=True)

    for idx, tbl in [
        ("ix_comm_events_staff", "communication_events"),
        ("ix_comm_events_sent_at", "communication_events"),
        ("ix_comm_events_parent", "communication_events"),
        ("ix_comm_events_kg", "communication_events"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("communication_events", if_exists=True)

    for idx, tbl in [
        ("uq_access_audit_kg_criteria_date", "accessibility_audits"),
        ("ix_access_audits_criteria", "accessibility_audits"),
        ("ix_access_audits_kg", "accessibility_audits"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("accessibility_audits", if_exists=True)

    for idx, tbl in [
        ("ix_ilp_status", "individualized_learning_plans"),
        ("ix_ilp_kg", "individualized_learning_plans"),
        ("ix_ilp_child", "individualized_learning_plans"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("individualized_learning_plans", if_exists=True)

    for idx, tbl in [
        ("uq_dev_assessment_child_milestone_date", "development_assessments"),
        ("ix_dev_assessments_domain", "development_assessments"),
        ("ix_dev_assessments_kg", "development_assessments"),
        ("ix_dev_assessments_child", "development_assessments"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("development_assessments", if_exists=True)

    for idx, tbl in [
        ("ix_financial_records_recorded_at", "financial_records"),
        ("ix_financial_records_kg_type", "financial_records"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    op.drop_table("financial_records", if_exists=True)
