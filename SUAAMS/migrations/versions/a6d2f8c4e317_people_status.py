"""students and lecturers: status (active, graduated, left, ...)

Revision ID: a6d2f8c4e317
Revises: e3b8d4f6a702
Create Date: 2026-10-13

Until now nobody could be switched off from the admin dashboard: a lecturer
who had left, or an expelled student, could still sign in. Each person now
has a status; anything but "active" switches their login off (see
people_status.py). Every existing row becomes "active", which is what they
all effectively were.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6d2f8c4e317'
down_revision = 'e3b8d4f6a702'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('students', sa.Column('status', sa.String(20), nullable=False, server_default='active'))
    op.add_column('lecturers', sa.Column('status', sa.String(20), nullable=False, server_default='active'))


def downgrade():
    op.drop_column('lecturers', 'status')
    op.drop_column('students', 'status')
