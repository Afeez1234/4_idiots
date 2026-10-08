"""Tests for campus time (campus_time.py) and late marking.

The bug these guard against: Render's clock is UTC, an hour behind Lagos,
and the code compared timetable times (campus time) with UTC "now" and
displayed stored UTC moments without converting. Late marking was an hour
too lenient and every check-in showed an hour early.

Run with:  python -m pytest tests/ -v
(the module also runs standalone via `python tests/test_campus_time.py`)
"""

import os
import sys
import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import campus_time  # noqa: E402
import utils  # noqa: E402


class LagosTestCase(unittest.TestCase):
    """Pins the timezone so the tests don't depend on the machine's env."""

    def setUp(self):
        self._prev = os.environ.get("INSTITUTION_TIMEZONE")
        os.environ["INSTITUTION_TIMEZONE"] = "Africa/Lagos"
        campus_time.campus_tz.cache_clear()

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("INSTITUTION_TIMEZONE", None)
        else:
            os.environ["INSTITUTION_TIMEZONE"] = self._prev
        campus_time.campus_tz.cache_clear()


class DisplayTests(LagosTestCase):
    def test_utc_moment_shows_in_lagos_time(self):
        # The reported case: checked in at 12:31 Lagos, shown as 11:31.
        self.assertEqual(campus_time.campus_fmt(datetime(2026, 10, 8, 11, 31)), "12:31")

    def test_aware_utc_datetime(self):
        moment = datetime(2026, 10, 8, 11, 31, tzinfo=timezone.utc)
        self.assertEqual(campus_time.campus_fmt(moment), "12:31")

    def test_bare_utc_time_like_session_start(self):
        self.assertEqual(campus_time.campus_fmt(time(11, 31), on_date=date(2026, 10, 8)), "12:31")

    def test_crosses_midnight_into_next_campus_day(self):
        moment = datetime(2026, 10, 8, 23, 30)  # 00:30 on the 9th in Lagos
        self.assertEqual(campus_time.campus_fmt(moment, "%d %H:%M"), "09 00:30")

    def test_none_stays_none(self):
        self.assertIsNone(campus_time.campus_fmt(None))

    def test_timezone_is_configurable(self):
        os.environ["INSTITUTION_TIMEZONE"] = "Africa/Nairobi"  # UTC+3
        campus_time.campus_tz.cache_clear()
        self.assertEqual(campus_time.campus_fmt(datetime(2026, 10, 8, 11, 31)), "14:31")


class CampusNowTests(LagosTestCase):
    def test_campus_now_is_naive_and_an_hour_ahead_of_utc(self):
        now = campus_time.campus_now()
        self.assertIsNone(now.tzinfo)
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertAlmostEqual((now - utc_now).total_seconds(), 3600, delta=5)


class LateMarkingTests(LagosTestCase):
    """compute_attendance_status against a 12:00 class on campus."""

    SESSION = SimpleNamespace(planned_start=time(12, 0), session_date=date(2026, 10, 8))

    def _status_at_campus(self, hh, mm):
        return utils.compute_attendance_status(
            self.SESSION, at=datetime(2026, 10, 8, hh, mm)
        )

    def test_on_time(self):
        self.assertEqual(self._status_at_campus(12, 0), "present")

    def test_inside_grace(self):
        self.assertEqual(self._status_at_campus(12, utils.LATE_GRACE_MINUTES), "present")

    def test_after_grace(self):
        self.assertEqual(self._status_at_campus(12, utils.LATE_GRACE_MINUTES + 1), "late")

    def test_default_now_is_campus_time_not_utc(self):
        # 12:40 in Lagos is 11:40 UTC. The old code compared the UTC value
        # against the 12:00 Lagos start and called this student present.
        campus_1240 = datetime(2026, 10, 8, 12, 40)
        with mock.patch.object(utils, "campus_now", return_value=campus_1240):
            self.assertEqual(utils.compute_attendance_status(self.SESSION), "late")

    def test_no_planned_start_is_always_present(self):
        adhoc = SimpleNamespace(planned_start=None, session_date=date(2026, 10, 8))
        self.assertEqual(utils.compute_attendance_status(adhoc), "present")


if __name__ == "__main__":
    unittest.main(verbosity=2)
