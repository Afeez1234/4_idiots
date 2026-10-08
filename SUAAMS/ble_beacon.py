"""Rotating BLE check-in codes.

Why this module exists
----------------------
NFC check-in (beacon.py) only works on Android phones that can emulate a
card. iPhones can't (Apple restricts card emulation to the EEA), and many
budget Android phones have no NFC at all. BLE is the fallback: every phone
has Bluetooth.

The direction is the reverse of NFC. With NFC the phone holds a credential
and the terminal reads it. With BLE the TERMINAL broadcasts a short-lived
code, the phone hears it, and the phone submits it to the server over its
own authenticated connection. Hearing the code is the proof of presence.

Wire format (the advertisement's manufacturer data, after the 2-byte
company ID):

    terminal(2B BE) || slot(4B BE) || code(8B)          -> 14 bytes

    slot = floor(unix_time / SLOT_SECONDS)
    code = HMAC-SHA256(BLE_BEACON_SECRET,
                       b"SUAAMS-BLE" || terminal || slot)[:8]

The ESP32 computes the same thing from its NTP-synced clock. The b"SUAAMS-
BLE" prefix keeps these codes from ever colliding with an HMAC computed
for some other purpose under the same key.

Security properties
-------------------
* Unforgeable without BLE_BEACON_SECRET. 64 bits of HMAC is far more than
  enough for a code that lives ~10 seconds behind a rate-limited endpoint.
* Short-lived: accepted for the current slot and the one before it, about
  10 seconds -- the same window as the NFC beacon (BEACON_TOKEN_TTL_SECONDS).
* The terminal number is covered by the HMAC, so a code can't be relabelled
  as coming from a different terminal.

Known weakness, accepted deliberately
-------------------------------------
A code is not bound to the phone that heard it. Someone in the room can
read it and pass it to an absent student, who submits it within the window.
That still needs the absent student's own bound phone, fingerprint and
login, and an unmodified app only takes codes from its own Bluetooth scan
-- but a determined pair with a script can do it. NFC's ~4cm range does
not have this hole, which is why BLE is the fallback and not the default,
and why every attendance row records which method was used.

Signal strength (RSSI) is reported by the phone, so it can be faked. It is
logged for diagnostics and used by the app to say "move closer"; it is
never used to accept or reject a check-in.
"""
# Annotations as strings, so `float | None` works whatever Python version
# Render runs (the repo doesn't pin one).
from __future__ import annotations

import hashlib
import hmac
import os
import struct
import time

# How long one code is broadcast before the terminal rotates to the next.
# The server accepts the current and previous slot, so a code heard just
# before rotation is still good for one more slot: ~10s in total, matching
# the NFC beacon's window.
SLOT_SECONDS = 5

# Slots accepted either side of the server's own current slot. One behind
# is the validity window above. One AHEAD tolerates the terminal's NTP
# clock running slightly ahead of the server's -- without it, a terminal a
# second fast would have its freshest code rejected for its first second.
_SLOTS_BEHIND = 1
_SLOTS_AHEAD = 1

_TERMINAL_LEN = 2
_SLOT_LEN = 4
_CODE_LEN = 8
PAYLOAD_LEN = _TERMINAL_LEN + _SLOT_LEN + _CODE_LEN  # 14

_DOMAIN = b"SUAAMS-BLE"

# Read at call time, never defaulted -- same rule as BEACON_SIGNING_SECRET.
# Unset means BLE check-in is disabled, not "signed with a known value".
_SECRET_ENV = "BLE_BEACON_SECRET"


class BleBeaconError(Exception):
    """A payload was malformed, forged, or outside the time window.

    Callers map this to a 401 with a deliberately vague message, so the
    endpoint can't be used to learn which check failed.
    """


class BleBeaconDisabled(BleBeaconError):
    """BLE_BEACON_SECRET is not configured on the server."""


def is_enabled() -> bool:
    """Whether BLE check-in is switched on for this deployment."""
    return bool(os.environ.get(_SECRET_ENV, "").strip())


def _secret() -> bytes:
    secret = os.environ.get(_SECRET_ENV, "").strip()
    if not secret:
        raise BleBeaconDisabled(
            f"{_SECRET_ENV} is not configured; BLE check-in is disabled."
        )
    return secret.encode("utf-8")


def current_slot(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // SLOT_SECONDS)


def compute_code(terminal: int, slot: int, secret: bytes | None = None) -> bytes:
    """The 8-byte code a terminal broadcasts for one slot.

    `secret` is only for tests and reference vectors; the app path always
    reads it from the environment.
    """
    key = _secret() if secret is None else secret
    message = _DOMAIN + struct.pack(">HI", terminal, slot)
    return hmac.new(key, message, hashlib.sha256).digest()[:_CODE_LEN]


def build_payload(terminal: int, slot: int, secret: bytes | None = None) -> bytes:
    """The full 14-byte payload. Mirrors what the ESP32 advertises."""
    return struct.pack(">HI", terminal, slot) + compute_code(terminal, slot, secret)


def verify_payload(payload: bytes, now: float | None = None) -> tuple[int, int]:
    """Check a payload the phone heard. Returns (terminal, slot).

    Raises BleBeaconDisabled if the feature is off, BleBeaconError for
    anything malformed, forged, or outside the window.
    """
    key = _secret()  # first, so "disabled" is reported as such

    if len(payload) != PAYLOAD_LEN:
        raise BleBeaconError("wrong payload length")

    terminal, slot = struct.unpack(">HI", payload[:_TERMINAL_LEN + _SLOT_LEN])
    supplied = payload[_TERMINAL_LEN + _SLOT_LEN:]

    expected = compute_code(terminal, slot, key)
    if not hmac.compare_digest(supplied, expected):
        raise BleBeaconError("bad code")

    # Window checked after the signature, so an unsigned payload can't be
    # used to probe the server's clock.
    now_slot = current_slot(now)
    if not (now_slot - _SLOTS_BEHIND <= slot <= now_slot + _SLOTS_AHEAD):
        raise BleBeaconError("outside window")

    return terminal, slot


def _bench_check(hex_text: str) -> int:
    """Diagnose one payload copied off the terminal or a BLE scanner app.

    Unlike verify_payload this says WHICH check failed -- fine for a
    developer at a bench, never for the public endpoint.
    """
    payload = bytes.fromhex("".join(hex_text.split()))
    if len(payload) != PAYLOAD_LEN:
        print(f"FAIL: {len(payload)} bytes, expected {PAYLOAD_LEN}")
        return 1

    terminal, slot = struct.unpack(">HI", payload[:6])
    try:
        expected = compute_code(terminal, slot)
    except BleBeaconDisabled as e:
        print(f"FAIL: {e}")
        return 1
    if not hmac.compare_digest(payload[6:], expected):
        print(f"FAIL: code does not match -- the terminal's BLE_BEACON_SECRET "
              f"differs from this one (terminal {terminal}, slot {slot})")
        return 1

    age = current_slot() - slot
    print(f"OK: signature valid -- terminal {terminal}, slot {slot}, "
          f"{age * SLOT_SECONDS}s old by this machine's clock")
    if not (-_SLOTS_AHEAD <= age <= _SLOTS_BEHIND):
        print("    (outside the live window now -- expected if you copied it "
              "more than ~10s ago; a large gap means the clocks disagree)")
    return 0


if __name__ == "__main__":
    # Bench check:  python ble_beacon.py 00 01 14 FB 18 00 D7 CE 23 37 4F F4 CC CB
    # Reads BLE_BEACON_SECRET from the environment or SUAAMS/.env.
    import sys
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass
    if len(sys.argv) < 2:
        print("usage: python ble_beacon.py <payload hex, spaces allowed>")
        sys.exit(2)
    sys.exit(_bench_check(" ".join(sys.argv[1:])))
