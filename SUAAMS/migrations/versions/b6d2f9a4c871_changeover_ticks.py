"""changeover_ticks: the changeover checklist's manual ticks

Revision ID: b6d2f9a4c871
Revises: a8e5c3f1d726
Create Date: 2026-10-26

The admin's semester changeover checklist (changeover.py) reads every step
from data it already has, except two the data can't confirm: graduating the
final years and uploading the new intake. An admin marks those done; this
table remembers who and when, one row per semester and step.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6d2f9a4c871'
down_revision = 'a8e5c3f1d726'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'changeover_ticks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('step', sa.String(length=20), nullable=False),
        sa.Column('done_by', sa.Integer(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['semester_id'], ['semesters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['done_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('semester_id', 'step', name='uq_changeover_tick'),
    )


def downgrade():
    op.drop_table('changeover_ticks')
