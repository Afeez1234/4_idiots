"""timetable: class kind (L/T/P) and draft vs published slots

Revision ID: e3b8d4f6a702
Revises: c7d5e9a1f204
Create Date: 2026-10-13

Timetables are now imported from Student Affairs PDF sheets. Imported slots
land as drafts (is_published = false), invisible to students and lecturers
until an admin publishes them. Every existing slot is published, so nothing
anyone sees today changes.

kind records Lecture / Tutorial / Practical, printed on the sheets as
"ACC204(L)", "ACC204(T)", "ACC206(P)". NULL for slots added by hand.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3b8d4f6a702'
down_revision = 'c7d5e9a1f204'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('timetable', sa.Column('kind', sa.String(1), nullable=True))
    # server_default true: every existing row becomes "published", which is
    # what they effectively were -- students already see them.
    op.add_column('timetable', sa.Column('is_published', sa.Boolean(), nullable=False,
                                         server_default=sa.true()))


def downgrade():
    op.drop_column('timetable', 'is_published')
    op.drop_column('timetable', 'kind')
