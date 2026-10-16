"""terminals; which reader took each check-in, and whether it was the right room

Revision ID: d4a7c2e9f150
Revises: c9e2a4f7b813
Create Date: 2026-10-16

The server knew one reader identity, shared by every reader, so it could
not tell readers apart and any reader accepted any class's check-in. Each
reader now has its own row (code, secret hash, room, Bluetooth number), and
attendance records which reader took it and whether that reader was in the
class's room. See models.Terminal and terminal_rooms.py.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a7c2e9f150'
down_revision = 'c9e2a4f7b813'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'terminals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(32), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('room', sa.String(50), nullable=True),
        sa.Column('ble_number', sa.Integer(), nullable=True, unique=True),
        sa.Column('secret_hash', sa.String(64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    # Batch mode: plain ALTERs on MySQL (production), and it also lets the
    # migration be run both ways on SQLite, which can't ALTER constraints.
    with op.batch_alter_table('attendance') as batch:
        batch.add_column(sa.Column('terminal_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('wrong_room', sa.Boolean(), nullable=True))
        batch.create_foreign_key('fk_attendance_terminal', 'terminals',
                                 ['terminal_id'], ['id'], ondelete='SET NULL')
    op.add_column('offline_checkin_logs', sa.Column('wrong_room', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('offline_checkin_logs', 'wrong_room')
    with op.batch_alter_table('attendance') as batch:
        batch.drop_constraint('fk_attendance_terminal', type_='foreignkey')
        batch.drop_column('wrong_room')
        batch.drop_column('terminal_id')
    op.drop_table('terminals')
