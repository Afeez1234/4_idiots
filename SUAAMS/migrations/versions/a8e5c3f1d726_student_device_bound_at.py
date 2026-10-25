"""students.device_bound_at: when the current phone was bound

Revision ID: a8e5c3f1d726
Revises: d4a7c2e9f150
Create Date: 2026-10-25

The admin's record drawer says when a student's phone was bound, so a
desk can tell "bound this morning" from "bound since the start of term".
Nullable, with no backfill: phones bound before this migration have no
recorded date and the drawer says so rather than inventing one.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e5c3f1d726'
down_revision = 'd4a7c2e9f150'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('students', sa.Column('device_bound_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('students', 'device_bound_at')
