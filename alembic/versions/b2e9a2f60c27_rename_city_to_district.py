"""rename_city_to_district

Revision ID: b2e9a2f60c27
Revises: p2_fk_cascade_001
Create Date: 2026-06-29 08:48:08.572361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e9a2f60c27'
down_revision: Union[str, None] = 'p2_fk_cascade_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS governorates (id INTEGER PRIMARY KEY)")
    with op.batch_alter_table('kindergartens') as batch_op:
        batch_op.alter_column('city', new_column_name='district')
    
    with op.batch_alter_table('imported_kindergartens') as batch_op:
        batch_op.alter_column('city', new_column_name='district')

    with op.batch_alter_table('parent_profiles') as batch_op:
        batch_op.alter_column('home_city', new_column_name='home_district')

    op.execute('DROP TABLE IF EXISTS administrative_divisions')
    op.create_table('administrative_divisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('governorate', sa.String(length=100), nullable=False),
        sa.Column('district', sa.String(length=100), nullable=False),
        sa.Column('area', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('governorate', 'district', 'area', name='uq_admin_div_gov_dist_area')
    )
    op.create_index(op.f('ix_administrative_divisions_area'), 'administrative_divisions', ['area'], unique=False)
    op.create_index(op.f('ix_administrative_divisions_district'), 'administrative_divisions', ['district'], unique=False)
    op.create_index(op.f('ix_administrative_divisions_governorate'), 'administrative_divisions', ['governorate'], unique=False)
    op.create_index(op.f('ix_administrative_divisions_id'), 'administrative_divisions', ['id'], unique=False)



def downgrade() -> None:
    op.drop_index(op.f('ix_administrative_divisions_id'), table_name='administrative_divisions')
    op.drop_index(op.f('ix_administrative_divisions_governorate'), table_name='administrative_divisions')
    op.drop_index(op.f('ix_administrative_divisions_district'), table_name='administrative_divisions')
    op.drop_index(op.f('ix_administrative_divisions_area'), table_name='administrative_divisions')
    op.drop_table('administrative_divisions')

    with op.batch_alter_table('parent_profiles') as batch_op:
        batch_op.alter_column('home_district', new_column_name='home_city')

    with op.batch_alter_table('imported_kindergartens') as batch_op:
        batch_op.alter_column('district', new_column_name='city')

    with op.batch_alter_table('kindergartens') as batch_op:
        batch_op.alter_column('district', new_column_name='city')

