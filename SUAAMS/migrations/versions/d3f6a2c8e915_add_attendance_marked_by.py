"""add attendance.marked_by (lecturer manual marking)

Revision ID: d3f6a2c8e915
Revises: b5d2e8f1c374
Create Date: 2026-10-09

Lecturers can now mark a student present by hand (method='manual') when the
student's phone can't check in. That is a person vouching for presence with
no device evidence behind it, so the row records which user did it.
Nullable: every existing row, and every self check-in, has no marker.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f6a2c8e915'
down_revision = 'b5d2e8f1c374'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attendance', sa.Column('marked_by', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_attendance_marked_by_users', 'attendance', 'users',
        ['marked_by'], ['id'], ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_attendance_marked_by_users', 'attendance', type_='foreignkey')
    op.drop_column('attendance', 'marked_by')
