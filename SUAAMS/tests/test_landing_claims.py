"""The landing page's numbers match the code that enforces them (2026-10-23).

landing/index.html and privacy.html state the check-in code's lifetime, the
Bluetooth code's rotation, the late cut-off and the attendance colour
thresholds. Each one is read here from the constant that owns it and every
mention on the pages is compared, so changing a constant without the page
fails this test instead of leaving a public page that's wrong.

Constants are read from source with ast, not imported, so this needs no
database, secrets or Flask app.

Run with:  python tests/test_landing_claims.py
(also collected by pytest if it is installed)
"""

import ast
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SERVER = REPO / 'SUAAMS'
LANDING = REPO / 'landing'
COURSES_VIEW = (REPO / 'SUAAMS_Mobile' / 'suaams' / 'lib' / 'features'
                / 'student' / 'presentation' / 'views' / 'courses_view.dart')


def python_constant(filename, name):
    tree = ast.parse((SERVER / filename).read_text(encoding='utf-8'))
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)):
            return ast.literal_eval(node.value)
    raise AssertionError(f'{name} not found in {filename}')


def app_thresholds():
    """The Records screen's colour cut-offs, highest first (green, amber)."""
    source = COURSES_VIEW.read_text(encoding='utf-8')
    return [int(n) for n in re.findall(r'course\.pct >= (\d+)', source)]


def page_text(name):
    return (LANDING / name).read_text(encoding='utf-8')


# (what the page says, value in code, pattern capturing the page's number,
#  pages that must mention it)
CLAIMS = [
    ('check-in code lifetime',
     python_constant('beacon.py', 'BEACON_TOKEN_TTL_SECONDS'),
     r'expires? after (\d+) seconds',
     ['index.html', 'privacy.html']),
    ('check-in code lifetime, stat band',
     python_constant('beacon.py', 'BEACON_TOKEN_TTL_SECONDS'),
     r'<b>(\d+)<small>s</small></b><span>before a check-in code expires',
     ['index.html']),
    ('Bluetooth code rotation',
     python_constant('ble_beacon.py', 'SLOT_SECONDS'),
     r'changes every (\d+) seconds',
     ['index.html']),
    ('late cut-off',
     python_constant('utils.py', 'LATE_GRACE_MINUTES'),
     r'started more than (\d+) minutes ago',
     ['index.html']),
    ('green threshold',
     app_thresholds()[0],
     r'<strong>Green</strong> at (\d+)% or more',
     ['index.html']),
    ('amber upper bound',
     app_thresholds()[0],
     r'<strong>Amber</strong> from \d+% up to (\d+)%',
     ['index.html']),
    ('amber lower bound',
     app_thresholds()[1],
     r'<strong>Amber</strong> from (\d+)% up to',
     ['index.html']),
    ('red threshold',
     app_thresholds()[1],
     r'<strong>Red</strong> under (\d+)%',
     ['index.html']),
]


class LandingClaimsTest(unittest.TestCase):

    def test_app_has_two_thresholds(self):
        self.assertEqual(len(app_thresholds()), 2,
                         'courses_view.dart colour rule changed shape')

    def test_every_claim_matches_code(self):
        for label, expected, pattern, pages in CLAIMS:
            for page in pages:
                with self.subTest(claim=label, page=page):
                    found = [int(n) for n in re.findall(pattern, page_text(page))]
                    self.assertTrue(found, f'{page} no longer states the {label}')
                    self.assertEqual(set(found), {expected},
                                     f'{page} says {found}, code says {expected}')


if __name__ == '__main__':
    unittest.main()
