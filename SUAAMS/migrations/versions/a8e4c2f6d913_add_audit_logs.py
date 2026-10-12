"""add audit_logs (who changed what on the admin dashboard)

Revision ID: a8e4c2f6d913
Revises: f2c9a7e4b158
Create Date: 2026-10-12

Several people now have personal admin logins (create_admin.py). Every
change made through the admin dashboard writes a row here naming who did it;
the admin Activity page reads them back. See audit.py and AuditLog in
models.py.

actor_id has no foreign key on purpose: an audit entry has to outlive the
account it describes.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e4c2f6d913'
down_revision = 'f2c9a7e4b158'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_label', sa.String(100), nullable=False),
        sa.Column('actor_role', sa.String(20), nullable=True),
        sa.Column('action', sa.String(60), nullable=False),
        sa.Column('entity_type', sa.String(40), nullable=True),
        sa.Column('entity_id', sa.String(64), nullable=True),
        sa.Column('summary', sa.String(255), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )
    # The Activity page lists newest first and filters by person and action.
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])


def downgrade():
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')
