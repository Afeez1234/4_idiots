"""offline tap review: 'accepted' status + reviewed_by / reviewed_at

Revision ID: f2c9a7e4b158
Revises: d3f6a2c8e915
Create Date: 2026-10-12

Lecturers can now accept or reject taps a terminal read while it was
offline (utils.review_offline_tap). An accepted tap becomes attendance with
method='offline'; the log row records which lecturer decided and when.

offline_checkin_logs was first created by add_offline_checkin_log.py, not
by a migration, so Alembic has never known about it. A database where that
script was never run has no table at all. This upgrade handles both: it
creates the table in its current shape if it's missing, and alters it in
place if it exists. attendance.method needs no change -- it is a
VARCHAR(8) and 'offline' is 7 characters.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c9a7e4b158'
down_revision = 'd3f6a2c8e915'
branch_labels = None
depends_on = None

OLD_STATUS = sa.Enum('pending_verification', 'superseded', 'rejected')
NEW_STATUS = sa.Enum('pending_verification', 'superseded', 'accepted', 'rejected')


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('offline_checkin_logs'):
        # Same shape as OfflineCheckinLog in models.py, review columns included.
        op.create_table(
            'offline_checkin_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('sessions.id'), nullable=False),
            sa.Column('terminal_id', sa.String(64), nullable=False),
            sa.Column('captured_at', sa.DateTime(), nullable=False),
            sa.Column('synced_at', sa.DateTime(), nullable=False),
            sa.Column('status', NEW_STATUS, nullable=False, server_default='pending_verification'),
            sa.Column('reason', sa.String(120), nullable=True),
            sa.Column('reviewed_by', sa.Integer(),
                      sa.ForeignKey('users.id', name='fk_offline_checkin_reviewed_by',
                                    ondelete='SET NULL'),
                      nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('student_id', 'session_id', name='uq_offline_checkin_student_session'),
        )
        op.create_index('ix_offline_checkin_session_status', 'offline_checkin_logs',
                        ['session_id', 'status'])
        return

    op.alter_column('offline_checkin_logs', 'status',
                    existing_type=OLD_STATUS, type_=NEW_STATUS,
                    existing_nullable=False, server_default='pending_verification')
    op.add_column('offline_checkin_logs', sa.Column('reviewed_by', sa.Integer(), nullable=True))
    op.add_column('offline_checkin_logs', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_offline_checkin_reviewed_by', 'offline_checkin_logs', 'users',
        ['reviewed_by'], ['id'], ondelete='SET NULL',
    )


def downgrade():
    # Leaves the table in place (it predates Alembic) and only removes what
    # this revision added. Accepted rows have to become something the old
    # enum allows first; 'superseded' is the honest fit, since attendance
    # for that student now exists.
    op.execute("UPDATE offline_checkin_logs SET status = 'superseded' WHERE status = 'accepted'")
    op.drop_constraint('fk_offline_checkin_reviewed_by', 'offline_checkin_logs', type_='foreignkey')
    op.drop_column('offline_checkin_logs', 'reviewed_at')
    op.drop_column('offline_checkin_logs', 'reviewed_by')
    op.alter_column('offline_checkin_logs', 'status',
                    existing_type=NEW_STATUS, type_=OLD_STATUS,
                    existing_nullable=False, server_default='pending_verification')
