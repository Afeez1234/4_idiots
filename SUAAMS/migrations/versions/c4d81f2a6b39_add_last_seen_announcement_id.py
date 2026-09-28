"""add last_seen_announcement_id to students

Revision ID: c4d81f2a6b39
Revises: 5c63620a0ca4
Create Date: 2026-09-28

Read watermark backing the student announcements badge. An announcement is
unread for a student while its id is greater than this value.

Nullable with no server default on purpose: NULL means "has never opened
the list", so every existing student sees their full history as unread on
first open rather than silently starting at a badge of zero.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d81f2a6b39'
down_revision = '5c63620a0ca4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'students',
        sa.Column('last_seen_announcement_id', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('students', 'last_seen_announcement_id')
