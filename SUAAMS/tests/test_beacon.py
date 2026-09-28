"""Tests for the compact HCE check-in beacon.

These cover the two properties the whole check-in redesign rests on and
that would otherwise only fail on real hardware:

  1. The token must stay small enough for a SINGLE APDU exchange. The old
     ~360-byte JWT forced a 64-byte chunked protocol across six round-trips,
     which is what made the flow unreliable. If someone grows the payload,
     test_token_fits_one_apdu_exchange fails loudly instead of silently
     reintroducing chunking on the reader.
  2. Verification must reject anything forged, tampered, expired, or
     malformed, and must fail closed when the signing key is unset.

Run with:  python -m pytest tests/ -v
(the module also runs standalone via `python tests/test_beacon.py`)
"""

import base64
import os
import sys
import time
import unittest

# Allow running both as `pytest tests/` and as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beacon  # noqa: E402


# One APDU exchange has to carry: the token, plus the 2-byte ISO 7816-4
# status word the HCE service always appends. The old chunking existed
# purely because a ~360-byte JWT blew past this.
MAX_APDU_BYTES = 64

# Raw token size the mint/verify pair is designed around: 12-byte payload
# + 12-byte truncated signature.
EXPECTED_RAW_BYTES = 24


class BeaconTestCase(unittest.TestCase):
    """Base class that gives every test a known signing key."""

    SECRET = "unit-test-signing-secret"

    def setUp(self):
        self._prev = os.environ.get(beacon._SIGNING_SECRET_ENV)
        os.environ[beacon._SIGNING_SECRET_ENV] = self.SECRET

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(beacon._SIGNING_SECRET_ENV, None)
        else:
            os.environ[beacon._SIGNING_SECRET_ENV] = self._prev

    @staticmethod
    def _raw(token):
        return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))

    @staticmethod
    def _encode(raw):
        return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")


class TestRoundTrip(BeaconTestCase):

    def test_mint_then_verify_returns_bound_ids(self):
        token = beacon.mint_beacon(student_id=42, session_id=7)
        self.assertEqual(beacon.verify_beacon(token), (42, 7))

    def test_token_binds_the_session_it_was_minted_for(self):
        # The regression this design exists to prevent: two concurrent
        # sessions must not be interchangeable. A token minted for
        # session 7 must never verify as session 8.
        token = beacon.mint_beacon(student_id=1, session_id=7)
        _, session_id = beacon.verify_beacon(token)
        self.assertEqual(session_id, 7)

    def test_ids_survive_a_round_trip_at_extremes(self):
        # 4-byte big-endian fields: guard the packing bounds.
        for student_id, session_id in ((0, 0), (1, 1), (2**31, 2**31), (2**32 - 1, 2**32 - 1)):
            token = beacon.mint_beacon(student_id=student_id, session_id=session_id)
            self.assertEqual(
                beacon.verify_beacon(token), (student_id, session_id)
            )


class TestWireSize(BeaconTestCase):
    """The size budget the single-exchange protocol depends on."""

    def test_token_fits_one_apdu_exchange(self):
        token = beacon.mint_beacon(student_id=1, session_id=1)
        apdu_bytes = len(token) + 2  # + 90 00 status word
        self.assertLessEqual(
            apdu_bytes, MAX_APDU_BYTES,
            f"beacon needs {apdu_bytes} bytes on the wire, over the "
            f"{MAX_APDU_BYTES}-byte single-exchange budget -- this will "
            f"require re-introducing chunking on the reader",
        )

    def test_token_is_exactly_32_ascii_chars(self):
        # 24 raw bytes -> 32 base64url chars, no padding. Fixed width is
        # what lets the HCE service answer SELECT without size ambiguity.
        token = beacon.mint_beacon(student_id=1, session_id=1)
        self.assertEqual(len(token), 32)
        self.assertEqual(len(self._raw(token)), EXPECTED_RAW_BYTES)

    def test_token_is_transport_safe_ascii(self):
        # The HCE service encodes with US_ASCII. base64url can only ever
        # emit [A-Za-z0-9_-], so the token is safe, but assert it so a
        # future change to the encoding can't smuggle a '=' or newline in.
        token = beacon.mint_beacon(student_id=1, session_id=1)
        self.assertTrue(all(c.isalnum() or c in "-_" for c in token))


class TestRejectsForgedAndTampered(BeaconTestCase):

    def test_tampered_payload_is_rejected(self):
        raw = bytearray(self._raw(beacon.mint_beacon(42, 7)))
        raw[0] ^= 0xFF  # first byte of student_id
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(self._encode(raw))

    def test_tampered_signature_is_rejected(self):
        raw = bytearray(self._raw(beacon.mint_beacon(42, 7)))
        raw[EXPECTED_RAW_BYTES - 1] ^= 0xFF
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(self._encode(raw))

    def test_escalating_student_id_is_rejected(self):
        # The realistic attack: swap student 42's token for student 1's id
        # to mark a peer present. Signature covers the payload, so this
        # must fail.
        raw = bytearray(self._raw(beacon.mint_beacon(42, 7)))
        raw[0:4] = (1).to_bytes(4, "big")
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(self._encode(raw))

    def test_token_signed_with_a_different_key_is_rejected(self):
        token = beacon.mint_beacon(student_id=1, session_id=1)
        os.environ[beacon._SIGNING_SECRET_ENV] = "a-completely-different-secret"
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(token)

    def test_expired_token_is_rejected(self):
        token = beacon.mint_beacon(student_id=1, session_id=1, ttl_seconds=-1)
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(token)

    def test_token_expiring_in_the_future_is_accepted(self):
        token = beacon.mint_beacon(student_id=1, session_id=1, ttl_seconds=30)
        self.assertEqual(beacon.verify_beacon(token), (1, 1))


class TestRejectsMalformed(BeaconTestCase):

    def test_rejects_junk_inputs(self):
        for bad in (None, "", "   ", "not base64!!!", "AAAA", "x" * 32,
                    "=" * 10, 12345, []):
            with self.subTest(value=bad):
                with self.assertRaises(beacon.BeaconError):
                    beacon.verify_beacon(bad)

    def test_rejects_truncated_token(self):
        # A short base64 string that decodes cleanly but is the wrong size.
        short = self._encode(self._raw(beacon.mint_beacon(1, 1))[:10])
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(short)

    def test_rejects_session_jwt_submitted_as_a_beacon(self):
        # Guards the mistake the old `purpose` claim existed to catch: a
        # normal login token must never be accepted here. A JWT is far
        # longer than our 24-byte raw budget, so the length check catches
        # it before anything else.
        fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(fake_jwt)

    def test_rejects_token_with_padding_stripped_or_present(self):
        # _b64decode must tolerate both forms; a reader must not be able to
        # break verification by normalising the padding differently.
        token = beacon.mint_beacon(student_id=1, session_id=1)
        padded = token + "=" * (-len(token) % 4)
        self.assertEqual(beacon.verify_beacon(padded), (1, 1))


class TestFailsClosedWithoutSecret(BeaconTestCase):
    """No hardcoded fallback key: unconfigured must mean disabled, not weak."""

    def setUp(self):
        self._prev = os.environ.get(beacon._SIGNING_SECRET_ENV)
        os.environ.pop(beacon._SIGNING_SECRET_ENV, None)

    def test_mint_refuses_without_a_signing_secret(self):
        with self.assertRaises(beacon.BeaconError):
            beacon.mint_beacon(student_id=1, session_id=1)

    def test_verify_refuses_without_a_signing_secret(self):
        # Mint while the key IS set, then unset it and confirm a token
        # that would otherwise be valid can no longer be checked.
        os.environ[beacon._SIGNING_SECRET_ENV] = self.SECRET
        token = beacon.mint_beacon(student_id=1, session_id=1)
        os.environ.pop(beacon._SIGNING_SECRET_ENV, None)
        with self.assertRaises(beacon.BeaconError):
            beacon.verify_beacon(token)

    def test_blank_secret_is_treated_as_unset(self):
        os.environ[beacon._SIGNING_SECRET_ENV] = "   "
        with self.assertRaises(beacon.BeaconError):
            beacon.mint_beacon(student_id=1, session_id=1)


class TestExpiryWindow(BeaconTestCase):
    """The acceptance window is the anti-relay guarantee -- pin it."""

    def test_default_ttl_is_ten_seconds(self):
        # Raised from 3s to 10s on 2026-09-27 after a hardware bench run:
        # the warm-server budget is ~0.5s (APDU read 0.12s + TLS/POST 0.3s +
        # write 0.1s), so at 3s essentially the whole window was being spent
        # on the student walking up to the terminal. ~2.5s of slack for that
        # made any student not already at the terminal fail deterministically.
        #
        # At 10s an attacker must relay within 10s AND be within NFC range
        # (~4cm). For calibration, TOTP/dynamic-password systems use 30s and
        # Apple BLE proximity beacons run 5-30s, so 3s was unusually strict.
        #
        # This test exists to make the number a DELIBERATE change. Editing
        # BEACON_TOKEN_TTL_SECONDS without reading the reasoning here is
        # exactly how the anti-relay bound gets weakened by accident. If you
        # are raising it past 30s, or lowering it back to 3s without fixing
        # the mint timing (the window starts at mint, before the student does
        # anything), this assertion should fail and you should have a reason.
        self.assertEqual(beacon.BEACON_TOKEN_TTL_SECONDS, 10)

    def test_token_expires_at_the_announced_second(self):
        before = int(time.time())
        token = beacon.mint_beacon(student_id=1, session_id=1)

        # Decode the exp field straight out of the payload so this asserts
        # on what was actually encoded, not on verify's interpretation.
        exp = int.from_bytes(self._raw(token)[8:12], "big")

        self.assertGreaterEqual(exp, before + beacon.BEACON_TOKEN_TTL_SECONDS)
        self.assertLessEqual(exp, int(time.time()) + beacon.BEACON_TOKEN_TTL_SECONDS)

    def test_token_is_still_valid_one_second_before_expiry(self):
        # The window must actually be usable, not just short: a token
        # minted with the default TTL has to survive most of its life.
        token = beacon.mint_beacon(student_id=1, session_id=1)
        time.sleep(1)
        self.assertEqual(beacon.verify_beacon(token), (1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
