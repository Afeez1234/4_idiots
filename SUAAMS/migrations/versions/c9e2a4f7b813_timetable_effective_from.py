"""timetable: effective_from

Revision ID: c9e2a4f7b813
Revises: b8f1c3e5d720
Create Date: 2026-10-15

Analytics counts each timetable slot as due once a week. With no record of
when a slot started, a class added or moved mid-semester was counted as
missed back to the first week of teaching. effective_from records the date
the slot started running. Existing rows stay NULL, which Analytics reads as
"from the first day of teaching" -- what it did before.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e2a4f7b813'
down_revision = 'b8f1c3e5d720'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('timetable', sa.Column('effective_from', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('timetable', 'effective_from')
