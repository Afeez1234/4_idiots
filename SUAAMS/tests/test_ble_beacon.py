"""Tests for the rotating BLE check-in code (ble_beacon.py).

What these pin down:

  1. The wire format. REFERENCE_* below is a fixed known-answer vector,
     computed independently from the spec. The ESP32 firmware must produce
     exactly this payload for the same key, terminal and slot -- if the
     firmware and server ever disagree on the layout or the HMAC input,
     every Bluetooth check-in fails, and only on real hardware.
  2. The payload fits one BLE advertisement. A legacy advertisement carries
     31 bytes; ours must leave room for the flags and the manufacturer-data
     header around it.
  3. Verification rejects anything forged, tampered, relabelled, stale or
     malformed, and fails closed when the key is unset.

Run with:  python -m pytest tests/ -v
(the module also runs standalone via `python tests/test_ble_beacon.py`)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ble_beacon  # noqa: E402

# Known-answer vector shared with the firmware. Do not regenerate this from
# ble_beacon itself; it was computed from the spec with a bare HMAC:
#   HMAC-SHA256(key, b"SUAAMS-BLE" || 0x0001 || 352000000 as 4 bytes BE)[:8]
REFERENCE_KEY = b"suaams-ble-reference-key"
REFERENCE_TERMINAL = 1
REFERENCE_SLOT = 352000000
REFERENCE_PAYLOAD_HEX = "000114fb1800d7ce23374ff4cccb"

# Legacy advertisement budget: 31 bytes, minus flags (3) and the
# manufacturer-data AD header (2: length + type) and company ID (2).
MAX_PAYLOAD_IN_ADVERT = 31 - 3 - 2 - 2


class BleBeaconTestCase(unittest.TestCase):
    SECRET = "unit-test-ble-secret"

    def setUp(self):
        self._prev = os.environ.get(ble_beacon._SECRET_ENV)
        os.environ[ble_beacon._SECRET_ENV] = self.SECRET

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(ble_beacon._SECRET_ENV, None)
        else:
            os.environ[ble_beacon._SECRET_ENV] = self._prev

    @staticmethod
    def _now_for(slot):
        """A wall-clock time in the middle of `slot`."""
        return slot * ble_beacon.SLOT_SECONDS + ble_beacon.SLOT_SECONDS / 2


class WireFormatTests(BleBeaconTestCase):
    def test_reference_vector(self):
        payload = ble_beacon.build_payload(REFERENCE_TERMINAL, REFERENCE_SLOT, REFERENCE_KEY)
        self.assertEqual(payload.hex(), REFERENCE_PAYLOAD_HEX)

    def test_payload_fits_one_advertisement(self):
        self.assertEqual(ble_beacon.PAYLOAD_LEN, 14)
        self.assertLessEqual(ble_beacon.PAYLOAD_LEN, MAX_PAYLOAD_IN_ADVERT)

    def test_round_trip(self):
        slot = 352000000
        payload = ble_beacon.build_payload(7, slot)
        self.assertEqual(ble_beacon.verify_payload(payload, now=self._now_for(slot)), (7, slot))


class WindowTests(BleBeaconTestCase):
    SLOT = 352000000

    def _verify_at(self, server_slot):
        payload = ble_beacon.build_payload(1, self.SLOT)
        return ble_beacon.verify_payload(payload, now=self._now_for(server_slot))

    def test_accepts_current_slot(self):
        self._verify_at(self.SLOT)

    def test_accepts_previous_slot(self):
        # Heard just before the terminal rotated.
        self._verify_at(self.SLOT + 1)

    def test_accepts_one_slot_ahead_for_clock_skew(self):
        # Terminal clock slightly ahead of the server's.
        self._verify_at(self.SLOT - 1)

    def test_rejects_two_slots_old(self):
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify_at(self.SLOT + 2)

    def test_rejects_far_future(self):
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify_at(self.SLOT - 2)

    def test_window_is_about_ten_seconds(self):
        # Keep in step with the NFC beacon's window (BEACON_TOKEN_TTL_SECONDS).
        self.assertEqual(ble_beacon.SLOT_SECONDS * (ble_beacon._SLOTS_BEHIND + 1), 10)


class RejectionTests(BleBeaconTestCase):
    SLOT = 352000000

    def _verify(self, payload):
        return ble_beacon.verify_payload(payload, now=self._now_for(self.SLOT))

    def test_rejects_wrong_key(self):
        forged = ble_beacon.build_payload(1, self.SLOT, b"some-other-key")
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify(forged)

    def test_rejects_flipped_code_bit(self):
        payload = bytearray(ble_beacon.build_payload(1, self.SLOT))
        payload[-1] ^= 0x01
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify(bytes(payload))

    def test_rejects_relabelled_terminal(self):
        # Same code, different terminal number: the HMAC covers the terminal.
        payload = bytearray(ble_beacon.build_payload(1, self.SLOT))
        payload[1] = 2
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify(bytes(payload))

    def test_rejects_replayed_code_with_fresh_slot(self):
        # An old code with its slot field bumped to "now" must not pass.
        old = ble_beacon.build_payload(1, self.SLOT - 10)
        bumped = old[:2] + (self.SLOT).to_bytes(4, "big") + old[6:]
        with self.assertRaises(ble_beacon.BleBeaconError):
            self._verify(bumped)

    def test_rejects_wrong_lengths(self):
        good = ble_beacon.build_payload(1, self.SLOT)
        for bad in (b"", good[:-1], good + b"\x00"):
            with self.assertRaises(ble_beacon.BleBeaconError):
                self._verify(bad)

    def test_fails_closed_without_secret(self):
        payload = ble_beacon.build_payload(1, self.SLOT)
        os.environ.pop(ble_beacon._SECRET_ENV, None)
        self.assertFalse(ble_beacon.is_enabled())
        with self.assertRaises(ble_beacon.BleBeaconDisabled):
            self._verify(payload)

    def test_blank_secret_counts_as_unset(self):
        os.environ[ble_beacon._SECRET_ENV] = "   "
        self.assertFalse(ble_beacon.is_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
