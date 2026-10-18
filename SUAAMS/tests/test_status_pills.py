"""One colour and one label per attendance status, everywhere (2026-10-18).

The web map lives in _macros.html attendance_status_pill and matches the
Flutter app's attendance_status.dart: present green, late amber, absent
red, excused grey. The four hand-written copies it replaced disagreed --
the student pages showed Late green and Excused red, the same as Absent.

Pins the map, and that no template writes its own again.

Run with:  python tests/test_status_pills.py
(also collected by pytest if it is installed)
"""

import os
import pathlib
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

EXPECTED = {           # status: (data-tone, label)
    'present': ('success', 'Present'),
    'late': ('warning', 'Late'),
    'absent': ('error', 'Absent'),
    'excused': ('neutral', 'Excused'),
}


class StatusPillTestCase(unittest.TestCase):

    def setUp(self):
        app = Flask(__name__, template_folder=str(TEMPLATES))
        self.macro = app.jinja_env.from_string(
            "{% from '_macros.html' import attendance_status_pill %}{{ attendance_status_pill(s) }}")

    def pill(self, status):
        html = self.macro.render(s=status)
        tone = re.search(r'data-tone="([a-z]+)"', html).group(1)
        label = re.sub(r'<[^>]+>|check|schedule|close', '', html).strip()
        return tone, label

    def test_each_status_has_its_one_colour_and_label(self):
        for status, expected in EXPECTED.items():
            self.assertEqual(self.pill(status), expected, status)
            self.assertEqual(self.pill(status.upper()), expected, status)   # case-insensitive

    def test_excused_is_not_shown_like_absent(self):
        self.assertNotEqual(self.pill('excused')[0], self.pill('absent')[0])

    def test_no_template_hand_writes_status_colours(self):
        # The patterns the old copies used. Any of them back means a page
        # has its own map again.
        patterns = [r"status == 'late'", r"status in \('present', 'late'\)", r"is_present = record\.status"]
        offenders = [str(p.relative_to(TEMPLATES)) for p in sorted(TEMPLATES.rglob('*.html'))
                     if any(re.search(pat, p.read_text(encoding='utf-8')) for pat in patterns)]
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
