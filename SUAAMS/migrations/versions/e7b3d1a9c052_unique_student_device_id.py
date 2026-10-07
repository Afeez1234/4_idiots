"""make students.device_id unique (one account per phone)

Revision ID: e7b3d1a9c052
Revises: c4d81f2a6b39
Create Date: 2026-10-07

Login previously only enforced one phone per account, so a single phone
could be bound to several students and its owner could check them all in.
mobile_login now refuses to bind a phone that another student holds; this
constraint backs that check so two simultaneous first-logins can't both
win the race.

NULL (unbound) is allowed any number of times by MySQL's unique index.

The upgrade refuses to run while duplicate bindings exist rather than
deciding on its own which student keeps the phone. Unbind the extra
accounts from the Admin dashboard first; the error lists the device_ids.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7b3d1a9c052'
down_revision = 'c4d81f2a6b39'
branch_labels = None
depends_on = None


def upgrade():
    students = sa.table('students', sa.column('device_id', sa.String))
    duplicates = op.get_bind().execute(
        sa.select(students.c.device_id, sa.func.count().label('n'))
        .where(students.c.device_id.isnot(None))
        .group_by(students.c.device_id)
        .having(sa.func.count() > 1)
    ).all()
    if duplicates:
        listed = ', '.join(f'{row.device_id!r} ({row.n} students)' for row in duplicates)
        raise RuntimeError(
            'Cannot make students.device_id unique: these phones are bound '
            f'to more than one student: {listed}. Unbind the extra accounts '
            'from the Admin dashboard, then rerun the migration.'
        )

    op.create_unique_constraint('uq_students_device_id', 'students', ['device_id'])


def downgrade():
    op.drop_constraint('uq_students_device_id', 'students', type_='unique')
