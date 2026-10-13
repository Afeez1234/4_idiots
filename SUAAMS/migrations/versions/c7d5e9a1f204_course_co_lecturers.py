"""course co-lecturers, and who started each session

Revision ID: c7d5e9a1f204
Revises: a8e4c2f6d913
Create Date: 2026-10-13

Courses often have several lecturers (a GST course can list six), but each
course had exactly one, and only that lecturer could start sessions, mark
students present or receive notifications. courses.lecturer_id stays as the
course COORDINATOR; course_lecturers holds everyone else who teaches it.
Every lecturer on a course has the same powers.

sessions.started_by records which user started each class, so with several
lecturers you can see who ran it. Existing sessions get NULL.

No data is copied: the coordinator is still on courses.lecturer_id, and the
new table starts empty.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d5e9a1f204'
down_revision = 'a8e4c2f6d913'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'course_lecturers',
        sa.Column('course_id', sa.Integer(),
                  sa.ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('lecturer_id', sa.Integer(),
                  sa.ForeignKey('lecturers.id', ondelete='CASCADE'), primary_key=True),
    )
    op.add_column('sessions', sa.Column('started_by', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_sessions_started_by_users', 'sessions', 'users',
        ['started_by'], ['id'], ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_sessions_started_by_users', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'started_by')
    op.drop_table('course_lecturers')
