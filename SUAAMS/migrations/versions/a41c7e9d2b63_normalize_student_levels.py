"""normalize students.level to bare numbers (100-500)

Revision ID: a41c7e9d2b63
Revises: e7b3d1a9c052
Create Date: 2026-10-07

Student.level was free text, so the same level was stored as "400", "400L"
and "400 l", splitting the admin roster's level filter and rendering as
"400LL" on the HOD pages (which append the "L" themselves). New writes are
now validated by utils.normalize_level; this rewrites the existing rows to
match.

The upgrade refuses to run while any value can't be mapped to 100-500
(e.g. a typo like "1000"), rather than guessing which level was meant.
Correct those students first; the error lists each bad value and how many
students hold it.

The normalising rule is copied here, not imported from utils, so this
migration keeps doing what it did today even if that function changes.
"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a41c7e9d2b63'
down_revision = 'e7b3d1a9c052'
branch_labels = None
depends_on = None

VALID_LEVELS = ('100', '200', '300', '400', '500')


def _normalize(raw):
    value = re.sub(r'\s+', '', raw or '').upper()
    if value.endswith('L'):
        value = value[:-1]
    return value if value in VALID_LEVELS else None


def upgrade():
    students = sa.table('students', sa.column('level', sa.String))
    bind = op.get_bind()

    stored = bind.execute(
        sa.select(students.c.level, sa.func.count().label('n'))
        .group_by(students.c.level)
    ).all()

    # Check everything before changing anything, so a bad value leaves the
    # table exactly as it was.
    invalid = [row for row in stored if _normalize(row.level) is None]
    if invalid:
        listed = ', '.join(f'{row.level!r} ({row.n} students)' for row in invalid)
        raise RuntimeError(
            'Cannot normalize students.level: these values are not a level '
            f'between 100 and 500: {listed}. Correct those students, then '
            'rerun the migration.'
        )

    for row in stored:
        canonical = _normalize(row.level)
        if canonical != row.level:
            bind.execute(
                students.update()
                .where(students.c.level == row.level)
                .values(level=canonical)
            )


def downgrade():
    # The original spellings ("400L" vs "400") aren't recorded anywhere, and
    # the bare number is valid under the old free-text rules anyway.
    pass
