"""Compact HCE check-in beacon tokens.

Why this module exists
----------------------
The phone-to-terminal check-in used to broadcast a Flask-JWT-Extended
access token (~360 bytes) over NFC HCE. That is far too large for the
channel: the ESP32/PN532 radio link was measured corrupting after ~119
bytes, forcing a 64-byte chunked protocol with 61xx status words and GET
RESPONSE chaining -- six round-trips and ~650ms of RF occupancy, all
inside a 3-second acceptance window that a cold backend can consume on
its own.

The credential therefore no longer needs to be self-verifying by the
reader. The ESP32 terminal does not verify anything (it has no crypto
verification path and never did) -- it relays what it physically read to
Flask, which is the only party that actually checks the credential. So we
use the wire bytes for a lookup handle rather than a signed JWT:

    payload = student_id(4B BE) || session_id(4B BE) || exp_unix(4B BE)
    sig     = HMAC-SHA256(BEACON_SIGNING_SECRET, payload)[:12]
    token   = base64url(payload || sig)          -> 32 ASCII characters

At 32 chars + 2 status bytes this is 34 bytes: a single APDU exchange,
~30ms, one round-trip. No chunking, no GET RESPONSE, no offset state
machine, and ~13x more forgiving of RF drift than the old flow.

Security properties
-------------------
* Unforgeable without BEACON_SIGNING_SECRET -- the phone cannot mint its
  own credentials, and neither can an attacker who captures a token.
* Bound to one student AND one session, both fixed at mint time. This
  replaces the old "pick the most recently started active session across
  all courses" lookup, which could credit a tap at a room-A terminal to a
  concurrent room-B session.
* Verified in constant time via hmac.compare_digest.

Known tradeoff: this is stateless, so it is not strictly single-use. A
replay is still bounded and harmless -- the token can only ever re-mark
the same student in the same session, and both attendance_already_recorded
and the uq_attendance_student_session unique constraint make that
idempotent. A DB-backed handle would give strict single-use, but this
project has no cache layer and no working migration path, so that would
mean a new table plus two extra round-trips inside the 3-second window.
"""

import base64
import hashlib
import hmac
import os
import struct
import time

# How long a minted beacon stays valid. Deliberately short -- this is NOT
# the student's login session JWT. CLAUDE.md's threat model calls 3
# seconds the canonical, strict handshake-acceptance window for HCE/BLE
# proximity tokens; this must stay at 3 to match. Reusing the long-lived
# session token here would defeat the anti-relay requirement entirely.
BEACON_TOKEN_TTL_SECONDS = 3

# Fixed field widths, big-endian. 12-byte payload + 12-byte signature.
# 24 bytes divides evenly into 8 base64 triplets, so the encoded token is
# exactly 32 characters with no '=' padding -- which is what lets the
# HCE service return it in one APDU without size ambiguity.
_PAYLOAD_LEN = 12
_SIG_LEN = 12
_TOKEN_LEN = _PAYLOAD_LEN + _SIG_LEN  # 24

# Env var name holding the HMAC key. Deliberately read at call time (not
# at import) so the value picks up without a module reload, and so a
# missing key fails CLOSED at the point of use with a clear message
# rather than crashing the whole app at import time.
_SIGNING_SECRET_ENV = "BEACON_SIGNING_SECRET"


class BeaconError(Exception):
    """Raised when a beacon is malformed, forged, or expired.

    Callers map this to a 401. The message is intentionally vague about
    *which* check failed, so the endpoint doesn't become an oracle for
    probing the signature scheme.
    """


def _signing_secret():
    """Fetch the HMAC key, failing closed if it isn't configured.

    There is deliberately NO fallback default here. A hardcoded default
    (the pattern used elsewhere in app.py for SECRET_KEY/JWT_SECRET) is
    worse than no key at all: it makes every deployment sign and verify
    with a value published in the repo, and it also defeats any
    "is this configured?" startup check, since the resolved value is
    never empty. Raise loudly instead.
    """
    secret = os.environ.get(_SIGNING_SECRET_ENV, "").strip()
    if not secret:
        raise BeaconError(
            f"{_SIGNING_SECRET_ENV} is not configured on the server; "
            "beacon check-in is disabled until it is set."
        )
    return secret.encode("utf-8")


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 with padding stripped (JWT-style alphabet)."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    """Inverse of _b64encode, tolerant of stripped or present padding."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def mint_beacon(student_id: int, session_id: int, ttl_seconds: int = BEACON_TOKEN_TTL_SECONDS) -> str:
    """Build a signed beacon bound to this student and this session.

    Callers must pass the session the attendance should land against --
    resolved at mint time, not at submit time. That binding is the whole
    point: it is what stops a tap being credited to whichever session
    happens to be newest when the terminal's POST lands.
    """
    secret = _signing_secret()
    expires_at = int(time.time()) + int(ttl_seconds)
    payload = struct.pack(">III", int(student_id), int(session_id), expires_at)
    signature = hmac.new(secret, payload, hashlib.sha256).digest()[:_SIG_LEN]
    return _b64encode(payload + signature)


def verify_beacon(token: str):
    """Verify a beacon and return ``(student_id, session_id)``.

    Raises BeaconError if the token is the wrong shape, fails the
    signature check, or has expired. The signature is checked against
    the raw payload bytes BEFORE any field is parsed, so an attacker
    cannot get a field read out of a forged token.
    """
    student_id, session_id, expires_at = verify_beacon_signature(token)

    if time.time() > expires_at:
        raise BeaconError("Beacon token has expired.")

    return student_id, session_id


def verify_beacon_signature(token: str):
    """Verify a beacon's signature and return ``(student_id, session_id, expires_at)``.

    Identical to verify_beacon() EXCEPT that it does not reject an expired
    token. Expiry is returned rather than enforced, so the caller can see
    when the token was minted.

    This exists for one caller: the offline backlog sync, where every
    record is necessarily expired and expiry is the expected case rather
    than a failure. Splitting it out keeps the "ignore the expiry window"
    behaviour explicit and named, instead of it being smuggled in as a
    flag on verify_beacon that someone could pass on the live check-in
    path by mistake -- which would hand out a 3-hour replay window.

    A token that still has to pass the signature check is still safe to
    trust for WHO and WHAT it is bound to; it is only the freshness
    guarantee that's absent, and the caller is responsible for not
    treating it as a live credential.
    """
    if not token or not isinstance(token, str):
        raise BeaconError("Beacon token missing.")

    try:
        raw = _b64decode(token.strip())
    except Exception:
        raise BeaconError("Beacon token is not valid base64url.")

    if len(raw) != _TOKEN_LEN:
        raise BeaconError("Beacon token has the wrong length.")

    payload, signature = raw[:_PAYLOAD_LEN], raw[_PAYLOAD_LEN:]

    expected = hmac.new(_signing_secret(), payload, hashlib.sha256).digest()[:_SIG_LEN]
    # Constant-time: a plain == would leak timing information about how
    # many leading signature bytes an attacker guessed correctly.
    if not hmac.compare_digest(signature, expected):
        raise BeaconError("Beacon signature does not match.")

    return struct.unpack(">III", payload)
