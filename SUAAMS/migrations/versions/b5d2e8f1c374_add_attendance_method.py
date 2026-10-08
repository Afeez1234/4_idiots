"""add attendance.method (nfc / ble / rfid)

Revision ID: b5d2e8f1c374
Revises: a41c7e9d2b63
Create Date: 2026-10-08

Records how each check-in happened, now that BLE exists alongside NFC as a
weaker fallback channel (see ble_beacon.py). Nullable with no default:
rows recorded before this column existed stay NULL ("unknown") rather than
being guessed at -- the RFID card path also wrote attendance, so a blanket
'nfc' backfill would mislabel some of them.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5d2e8f1c374'
down_revision = 'a41c7e9d2b63'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attendance', sa.Column('method', sa.String(length=8), nullable=True))


def downgrade():
    op.drop_column('attendance', 'method')
