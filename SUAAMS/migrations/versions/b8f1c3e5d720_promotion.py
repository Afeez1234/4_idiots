"""departments: programme length; promotion_runs

Revision ID: b8f1c3e5d720
Revises: a6d2f8c4e317
Create Date: 2026-10-14

Students' levels never changed after enrolment. Promotion (promotion.py)
moves every active student up one level once per academic year. It needs
each department's programme length (4 or 5 years) to know who is in their
final year, and records each run so a year can't be promoted twice and a
run can be undone.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT


# revision identifiers, used by Alembic.
revision = 'b8f1c3e5d720'
down_revision = 'a6d2f8c4e317'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('departments', sa.Column('programme_years', sa.Integer(), nullable=True))
    op.create_table(
        'promotion_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('academic_year', sa.String(20), nullable=False, unique=True),
        sa.Column('promoted', sa.Integer(), nullable=False),
        # MEDIUMTEXT on MySQL: TEXT's 64 KB is about 10,000 students' ids.
        sa.Column('moves', sa.Text().with_variant(MEDIUMTEXT, 'mysql'), nullable=False),
        sa.Column('run_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('promotion_runs')
    op.drop_column('departments', 'programme_years')
