"""reconcile missing classes columns for legacy sqlite databases

Revision ID: 20260219_reconcile_classes_columns
Revises: 20260219_add_supervisor_full_time_dedication
Create Date: 2026-02-19 02:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260219_reconcile_classes_columns"
down_revision: Union[str, None] = "20260219_add_supervisor_full_time_dedication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AGE_GROUP_ENUM = sa.Enum("AGE_0_1", "AGE_1_2", "AGE_2_4", name="age_group_enum")


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("classes"):
        return

    if not _column_exists("classes", "class_code"):
        with op.batch_alter_table("classes", schema=None) as batch_op:
            batch_op.add_column(sa.Column("class_code", sa.String(length=32), nullable=True))

    if not _column_exists("classes", "age_group"):
        with op.batch_alter_table("classes", schema=None) as batch_op:
            batch_op.add_column(sa.Column("age_group", AGE_GROUP_ENUM, nullable=True))

    if not _column_exists("classes", "enrolled_children_count"):
        with op.batch_alter_table("classes", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "enrolled_children_count",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )

    op.execute(sa.text("UPDATE classes SET class_code = 'CLS-' || id WHERE class_code IS NULL OR class_code = ''"))
    op.execute(sa.text("UPDATE classes SET age_group = 'AGE_2_4' WHERE age_group IS NULL OR age_group = ''"))
    op.execute(sa.text("UPDATE classes SET enrolled_children_count = 0 WHERE enrolled_children_count IS NULL"))

    with op.batch_alter_table("classes", schema=None) as batch_op:
        batch_op.alter_column("class_code", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("age_group", existing_type=AGE_GROUP_ENUM, nullable=False)
        batch_op.alter_column(
            "enrolled_children_count",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=None,
        )

    if not _index_exists("classes", "uq_classes_class_code"):
        with op.batch_alter_table("classes", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_classes_class_code", ["class_code"])


def downgrade() -> None:
    # No-op on downgrade: this revision reconciles divergent legacy schemas.
    # Destructive column drops here can break historical downgrade chains.
    pass
