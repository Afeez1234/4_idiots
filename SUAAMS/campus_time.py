"""Campus time: the one place the institution's timezone is defined.

Why this module exists
----------------------
The backend has two kinds of time, and it used to mix them up:

* Timetable times -- Timetable.start_time/end_time, Session.planned_start/
  planned_end. Clock times an admin typed in ("12:00"), meaning CAMPUS time.
* Moments -- Attendance.time_in, Session.start_time/stop_time, created_at
  columns. Stored in UTC, as CLAUDE.md requires.

Render's server clock is UTC, so `datetime.now()` and
`datetime.now(timezone.utc)` both read UTC there -- an hour behind Lagos.
Comparing that against a timetable time made late marking an hour too
lenient and matched the wrong "current class", and formatting a stored UTC
moment straight to HH:MM showed every check-in an hour early.

The rules, applied everywhere:

1. Anything compared WITH THE TIMETABLE uses campus_now() / campus_today().
2. Anything SHOWN to a person converts from UTC with campus_fmt() (Jinja:
   the `campus` filter).
3. Storage is unchanged: moments are still written in UTC.

Africa/Lagos has no daylight saving, but ZoneInfo is used rather than a
fixed +1 offset so another deployment can change INSTITUTION_TIMEZONE.
"""
# Annotations as strings: the repo doesn't pin Render's Python version.
from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

# A default is fine here, unlike the credentials: a wrong guess is visible
# on the first screen anyone looks at, and it isn't a secret.
_DEFAULT_TZ = "Africa/Lagos"


@lru_cache(maxsize=1)
def campus_tz() -> ZoneInfo:
    """The institution's timezone. Read on first use, not at import: app.py
    loads .env after the models (which import this) are already imported."""
    return ZoneInfo(os.environ.get("INSTITUTION_TIMEZONE", "").strip() or _DEFAULT_TZ)


def campus_now() -> datetime:
    """Current campus wall-clock time, NAIVE -- for comparing with timetable
    columns, which are naive campus times themselves."""
    return datetime.now(campus_tz()).replace(tzinfo=None)


def campus_today() -> date:
    """Today's date on campus. Differs from the UTC date between midnight
    and the UTC offset (00:00-01:00 in Lagos)."""
    return campus_now().date()


def to_campus(value: datetime | time | None, on_date: date | None = None) -> datetime | None:
    """A stored UTC moment as an aware campus datetime.

    Accepts a datetime (naive ones are taken as UTC, which is how MySQL
    hands back the UTC values we stored) or a bare time, such as
    Session.start_time, which is combined with `on_date` (the UTC date it
    belongs to; defaults to today) before converting.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        moment = datetime.combine(on_date or datetime.now(timezone.utc).date(),
                                  value, tzinfo=timezone.utc)
    return moment.astimezone(campus_tz())


def campus_fmt(value: datetime | time | None, fmt: str = "%H:%M",
               on_date: date | None = None) -> str | None:
    """Format a stored UTC moment in campus time. None stays None, so callers
    keep their existing `if value else '--'` fallbacks."""
    moment = to_campus(value, on_date)
    return moment.strftime(fmt) if moment else None
