"""Schema consistency patch for classes/supervisor/waitlist drift.

Revision ID: 20260224_schema_consistency_patch
Revises: 20260219_reconcile_classes_columns
Create Date: 2026-02-24 23:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260224_schema_consistency_patch"
down_revision: Union[str, None] = "20260219_reconcile_classes_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AGE_GROUP_VALUES = ("AGE_0_1", "AGE_1_2", "AGE_2_4")
AGE_GROUP_ENUM_NAME = "age_group_enum"


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _unique_exists(table_name: str, unique_name: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    for uq in inspector.get_unique_constraints(table_name):
        if uq.get("name") == unique_name:
            return True
    for idx in inspector.get_indexes(table_name):
        if idx.get("name") == unique_name and idx.get("unique"):
            return True
    return False


def _age_group_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        enum_type = sa.Enum(*AGE_GROUP_VALUES, name=AGE_GROUP_ENUM_NAME)
        enum_type.create(bind, checkfirst=True)
        return sa.Enum(*AGE_GROUP_VALUES, name=AGE_GROUP_ENUM_NAME, create_type=False)
    return sa.String(length=7)


def upgrade() -> None:
    # Cleanup from failed/partial SQLite batch table recreation.
    if _table_exists("_alembic_tmp_classes"):
        op.drop_table("_alembic_tmp_classes")

    if _table_exists("classes"):
        if not _column_exists("classes", "class_code"):
            op.add_column("classes", sa.Column("class_code", sa.String(length=32), nullable=True))

        if not _column_exists("classes", "age_group"):
            op.add_column("classes", sa.Column("age_group", _age_group_type(), nullable=True))

        if not _column_exists("classes", "enrolled_children_count"):
            op.add_column(
                "classes",
                sa.Column(
                    "enrolled_children_count",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )

        op.execute(sa.text("UPDATE classes SET class_code = 'CLS-' || id WHERE class_code IS NULL OR class_code = ''"))
        op.execute(sa.text("UPDATE classes SET age_group = 'AGE_2_4' WHERE age_group IS NULL OR age_group = ''"))
        op.execute(sa.text("UPDATE classes SET enrolled_children_count = 0 WHERE enrolled_children_count IS NULL"))

        with op.batch_alter_table("classes", schema=None) as batch_op:
            batch_op.alter_column("class_code", existing_type=sa.String(length=32), nullable=False)
            batch_op.alter_column("age_group", existing_type=_age_group_type(), nullable=False)
            batch_op.alter_column(
                "enrolled_children_count",
                existing_type=sa.Integer(),
                nullable=False,
                server_default=None,
            )

        if not _unique_exists("classes", "uq_classes_class_code"):
            with op.batch_alter_table("classes", schema=None) as batch_op:
                batch_op.create_unique_constraint("uq_classes_class_code", ["class_code"])

    if _table_exists("supervisor_assignments") and not _column_exists(
        "supervisor_assignments", "full_time_dedication"
    ):
        with op.batch_alter_table("supervisor_assignments", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "full_time_dedication",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )
        with op.batch_alter_table("supervisor_assignments", schema=None) as batch_op:
            batch_op.alter_column("full_time_dedication", server_default=None)

    if _table_exists("waitlist_entries") and _index_exists("waitlist_entries", "idx_waitlist_status_priority"):
        op.drop_index("idx_waitlist_status_priority", table_name="waitlist_entries")


def downgrade() -> None:
    # No-op by design: prior revisions own the original schema shape.
    pass
