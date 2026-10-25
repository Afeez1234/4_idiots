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
    # The decoded demo code (Security, "What your phone actually sends").
    ('check-in code lifetime, decoded demo code',
     python_constant('beacon.py', 'BEACON_TOKEN_TTL_SECONDS'),
     r'expires (\d+) s after minting',
     ['index.html']),
    ('check-in code lifetime, security list',
     python_constant('beacon.py', 'BEACON_TOKEN_TTL_SECONDS'),
     r'dead in (\d+) s',
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


def manifest_text():
    return (REPO / 'SUAAMS_Mobile' / 'suaams' / 'android' / 'app' / 'src'
            / 'main' / 'AndroidManifest.xml').read_text(encoding='utf-8')


class LandingClaimsTest(unittest.TestCase):

    def test_demo_code_is_a_real_format_token(self):
        """The Security section shows a demo check-in code split into payload
        and signature. It must stay the real shape: 16 + 16 base64url
        characters (12-byte payload, 12-byte signature, beacon.py)."""
        html = page_text('index.html')
        payload = re.search(r'<span class="payload">([A-Za-z0-9_-]+)</span>', html)
        sig = re.search(r'<span class="sig">([A-Za-z0-9_-]+)</span>', html)
        self.assertTrue(payload and sig, 'demo code markup changed')
        self.assertEqual((len(payload.group(1)), len(sig.group(1))), (16, 16))

    def test_reader_photo_markup_matches_file(self):
        """The stage links img/reader-tap.webp only once the file exists.
        Linked before that, every visit makes a failed request and, without
        JavaScript, shows a broken-image icon; left commented out after the
        photo is added, the page keeps showing "Reader photo coming"."""
        html = page_text('index.html')
        # Strip HTML comments: the ready-to-use <img> waits inside one.
        live = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        linked = 'src="img/reader-tap.webp"' in live
        exists = (LANDING / 'img' / 'reader-tap.webp').exists()
        if exists:
            self.assertTrue(linked, 'img/reader-tap.webp exists: uncomment its <img> in index.html')
        else:
            self.assertFalse(linked, 'index.html links img/reader-tap.webp, which does not exist yet')

    def test_get_page_permissions_match_manifest(self):
        """/get lists what the app asks for. Location must be described as
        Android 11 and older only for as long as the manifest caps it there,
        and every listed permission must be one the manifest declares."""
        manifest = manifest_text()
        page = page_text('get/index.html')
        self.assertIn('ACCESS_FINE_LOCATION" android:maxSdkVersion="30"', manifest)
        self.assertIn('Android 11 and older only', page)
        for label, permission in [('NFC', 'android.permission.NFC'),
                                  ('Bluetooth', 'BLUETOOTH_SCAN'),
                                  ('Notifications', 'POST_NOTIFICATIONS'),
                                  ('Fingerprint or PIN', 'USE_BIOMETRIC')]:
            with self.subTest(permission=label):
                self.assertIn(f'<dt>{label}</dt>', page)
                self.assertIn(permission, manifest)

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
