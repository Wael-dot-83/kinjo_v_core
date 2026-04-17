"""Add import tracking tables and class/profile hardening.

Revision ID: f66e02e0bc57
Revises: f38c5803c8e5
Create Date: 2026-02-11 06:52:19.709337
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f66e02e0bc57"
down_revision: Union[str, None] = "f38c5803c8e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name))


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(c.get("name") == constraint_name for c in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    if not _table_exists("import_logs"):
        op.create_table(
            "import_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("stored_file_path", sa.String(length=500), nullable=True),
            sa.Column("total_rows", sa.Integer(), nullable=False),
            sa.Column("imported_count", sa.Integer(), nullable=False),
            sa.Column("updated_count", sa.Integer(), nullable=False),
            sa.Column("skipped_count", sa.Integer(), nullable=False),
            sa.Column("errors_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    op.create_index("ix_import_logs_id", "import_logs", ["id"], unique=False, if_not_exists=True)

    if not _table_exists("imported_kindergartens"):
        op.create_table(
            "imported_kindergartens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name_ar", sa.String(length=255), nullable=False),
            sa.Column("name_en", sa.String(length=255), nullable=True),
            sa.Column("governorate", sa.String(length=100), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("area", sa.String(length=100), nullable=True),
            sa.Column("detailed_address", sa.Text(), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name_ar", "city", "phone", name="uq_imported_kindergartens_name_city_phone"),
        )
    op.create_index("idx_imported_kindergartens_city", "imported_kindergartens", ["city"], unique=False, if_not_exists=True)
    op.create_index(
        "idx_imported_kindergartens_governorate",
        "imported_kindergartens",
        ["governorate"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index("ix_imported_kindergartens_id", "imported_kindergartens", ["id"], unique=False, if_not_exists=True)

    # Legacy cleanup: curriculum_outcomes is removed from the active model set.
    if _index_exists("curriculum_outcomes", "ix_curriculum_outcomes_id"):
        op.drop_index("ix_curriculum_outcomes_id", table_name="curriculum_outcomes")
    if _table_exists("curriculum_outcomes"):
        op.drop_table("curriculum_outcomes")

    if _table_exists("children") and not _unique_exists("children", "uq_children_parent_name_dob"):
        with op.batch_alter_table("children") as batch_op:
            batch_op.create_unique_constraint(
                "uq_children_parent_name_dob",
                ["parent_id", "first_name", "last_name", "date_of_birth"],
            )

    if _table_exists("classes"):
        with op.batch_alter_table("classes") as batch_op:
            if not _column_exists("classes", "class_code"):
                batch_op.add_column(sa.Column("class_code", sa.String(length=32), nullable=True))
            if not _column_exists("classes", "age_group"):
                batch_op.add_column(
                    sa.Column(
                        "age_group",
                        sa.Enum("AGE_0_1", "AGE_1_2", "AGE_2_4", name="age_group_enum"),
                        nullable=True,
                    )
                )
            if not _column_exists("classes", "enrolled_children_count"):
                batch_op.add_column(
                    sa.Column("enrolled_children_count", sa.Integer(), nullable=False, server_default="0")
                )
            batch_op.alter_column("kindergarten_id", existing_type=sa.INTEGER(), nullable=False)
            if not _unique_exists("classes", "uq_classes_class_code"):
                batch_op.create_unique_constraint("uq_classes_class_code", ["class_code"])

    if _table_exists("kindergartens") and not _unique_exists("kindergartens", "uq_kindergartens_license_number"):
        with op.batch_alter_table("kindergartens") as batch_op:
            batch_op.create_unique_constraint("uq_kindergartens_license_number", ["license_number"])

    if _table_exists("supervisor_assignments") and not _column_exists("supervisor_assignments", "full_time_dedication"):
        with op.batch_alter_table("supervisor_assignments") as batch_op:
            batch_op.add_column(sa.Column("full_time_dedication", sa.Boolean(), nullable=False, server_default=sa.true()))

    if _table_exists("survey_responses") and not _unique_exists("survey_responses", "uq_survey_responses_survey_parent"):
        with op.batch_alter_table("survey_responses") as batch_op:
            batch_op.create_unique_constraint(
                "uq_survey_responses_survey_parent",
                ["survey_id", "parent_id"],
            )


def downgrade() -> None:
    if _table_exists("survey_responses") and _unique_exists("survey_responses", "uq_survey_responses_survey_parent"):
        with op.batch_alter_table("survey_responses") as batch_op:
            batch_op.drop_constraint("uq_survey_responses_survey_parent", type_="unique")

    if _table_exists("supervisor_assignments") and _column_exists("supervisor_assignments", "full_time_dedication"):
        with op.batch_alter_table("supervisor_assignments") as batch_op:
            batch_op.drop_column("full_time_dedication")

    if _table_exists("kindergartens") and _unique_exists("kindergartens", "uq_kindergartens_license_number"):
        with op.batch_alter_table("kindergartens") as batch_op:
            batch_op.drop_constraint("uq_kindergartens_license_number", type_="unique")

    if _table_exists("classes"):
        with op.batch_alter_table("classes") as batch_op:
            if _unique_exists("classes", "uq_classes_class_code"):
                batch_op.drop_constraint("uq_classes_class_code", type_="unique")
            if _column_exists("classes", "enrolled_children_count"):
                batch_op.drop_column("enrolled_children_count")
            if _column_exists("classes", "age_group"):
                batch_op.drop_column("age_group")
            if _column_exists("classes", "class_code"):
                batch_op.drop_column("class_code")
            batch_op.alter_column("kindergarten_id", existing_type=sa.INTEGER(), nullable=True)

    if _table_exists("children") and _unique_exists("children", "uq_children_parent_name_dob"):
        with op.batch_alter_table("children") as batch_op:
            batch_op.drop_constraint("uq_children_parent_name_dob", type_="unique")

    if not _table_exists("curriculum_outcomes"):
        op.create_table(
            "curriculum_outcomes",
            sa.Column("id", sa.INTEGER(), nullable=False),
            sa.Column("domain", sa.VARCHAR(length=16), nullable=False),
            sa.Column("age_band_min_months", sa.INTEGER(), nullable=False),
            sa.Column("age_band_max_months", sa.INTEGER(), nullable=False),
            sa.Column("indicator_code", sa.VARCHAR(length=50), nullable=False),
            sa.Column("description", sa.TEXT(), nullable=False),
            sa.Column("created_at", sa.DATETIME(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("indicator_code"),
        )
    op.create_index("ix_curriculum_outcomes_id", "curriculum_outcomes", ["id"], unique=False, if_not_exists=True)

    op.drop_index("ix_imported_kindergartens_id", table_name="imported_kindergartens", if_exists=True)
    op.drop_index("idx_imported_kindergartens_governorate", table_name="imported_kindergartens", if_exists=True)
    op.drop_index("idx_imported_kindergartens_city", table_name="imported_kindergartens", if_exists=True)
    if _table_exists("imported_kindergartens"):
        op.drop_table("imported_kindergartens")

    op.drop_index("ix_import_logs_id", table_name="import_logs", if_exists=True)
    if _table_exists("import_logs"):
        op.drop_table("import_logs")

