"""Align audit_logs.details with the model: jsonb -> TEXT.

models.AuditLog declares ``details = Column(Text)`` and every caller passes a
human-readable sentence ("Created kindergarten ..."). PostgreSQL, however, had
the column as jsonb, so any audit-logged write raised

    psycopg2.errors.InvalidTextRepresentation:
    invalid input syntax for type json ... Token "Created" is invalid

That made POST /api/admin/kindergartens return 500 in production: an admin could
not create a kindergarten at all. SQLite stores the column as text and accepts
anything, so the test suite never saw it.

old_data and new_data are genuinely JSON in the model and are left as jsonb.

Conversion is safe: details is NULL on all but one row, and that row holds a
JSON object which becomes its serialized text form. Nothing is discarded.

Revision ID: audit_details_text_01
Revises: enum_drift_repair_01
"""
from alembic import op
import sqlalchemy as sa

revision = "audit_details_text_01"
down_revision = "enum_drift_repair_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite already stores this column as text.
        return

    current = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'audit_logs' AND column_name = 'details'"
        )
    ).scalar()
    if current is None or current.lower() == "text":
        return

    # A jsonb string would render as "\"x\"" through a plain cast, so unwrap
    # scalar strings and serialize anything structured.
    op.execute(
        sa.text(
            "ALTER TABLE audit_logs "
            "ALTER COLUMN details TYPE TEXT "
            "USING CASE WHEN details IS NULL THEN NULL "
            "WHEN jsonb_typeof(details) = 'string' THEN details #>> '{}' "
            "ELSE details::text END"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Only rows holding valid JSON can go back; wrap everything else as a JSON
    # string so the conversion cannot fail.
    op.execute(
        sa.text(
            "ALTER TABLE audit_logs "
            "ALTER COLUMN details TYPE JSONB "
            "USING CASE WHEN details IS NULL THEN NULL "
            "ELSE to_jsonb(details) END"
        )
    )
