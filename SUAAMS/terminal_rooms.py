"""Readers (ESP32 terminals): who is calling, and are they in the class's room?

Two jobs, both new on 2026-10-16:

1. AUTHENTICATE A READER. Each reader has its own code and secret
   (models.Terminal), sent as X-Terminal-Id / X-Terminal-Secret. The old
   shared pair in the environment (TERMINAL_ID / TERMINAL_SECRET) is still
   accepted during the changeover, so readers can be moved over one at a
   time; remove those two variables once every reader has its own secret.

2. CHECK THE ROOM. A class's room is the room its lecturer gave when
   starting it (Session.room), else its timetable slot's room. A reader's
   room is set on the Terminals page. If both are known and differ, the
   check-in is in the wrong room. ROOM_CHECK decides what that means:

     flag     (default)  record it, marked wrong_room, shown to the lecturer
     enforce             refuse it ("wrong room")
     off                 don't check

   Flag is the default while readers and rooms are being set up: a typo in
   a room name or a reader moved without updating the page would otherwise
   block a whole class. Switch to enforce once rooms are right.

Rooms are compared loosely ("LT 1" = "LT1" = "lt-1"), because timetables
and the Terminals page are typed by hand.
"""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import request

from models import db, Terminal

ROOM_CHECK_MODES = ('flag', 'enforce', 'off')

# last_seen_at is written at most this often per reader: a busy hall sends
# a request every second or two, and the Terminals page only needs "about
# now", not a database write per tap.
_SEEN_EVERY = timedelta(seconds=30)

_LEGACY = object()      # authenticated with the old shared secret


def new_secret():
    """A fresh reader secret: shown to the admin once, never stored."""
    return secrets.token_urlsafe(32)


def hash_secret(secret):
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def room_check_mode():
    """ROOM_CHECK from the environment. Not a credential, so a default is
    fine: an unknown value falls back to flag, never to off."""
    mode = os.environ.get('ROOM_CHECK', 'flag').strip().lower()
    return mode if mode in ROOM_CHECK_MODES else 'flag'


def _legacy_ok(supplied_id, supplied_secret):
    expected_id = os.environ.get('TERMINAL_ID', '').strip()
    expected_secret = os.environ.get('TERMINAL_SECRET', '').strip()
    if not expected_id or not expected_secret:
        return False
    # Constant-time on the secret so it can't be found a byte at a time.
    return (hmac.compare_digest(supplied_secret, expected_secret)
            and hmac.compare_digest(supplied_id, expected_id))


def _touch(terminal):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if terminal.last_seen_at is None or now - terminal.last_seen_at > _SEEN_EVERY:
        terminal.last_seen_at = now
        db.session.commit()


def authenticate():
    """(ok, terminal) for this request's reader headers.

    ok is False for anything that isn't a registered, active reader with
    its own secret, or the old shared pair. terminal is the Terminal row,
    or None when the old shared pair was used by a reader nobody has
    registered (its room is unknown, so it is never flagged). Cached for
    the request: the rate limiter and the route both ask.

    The cache lives in the request's WSGI environ, never in flask.g: g
    belongs to the app context, which code running inside an outer context
    (tests, scripts) shares across requests -- a later request with a wrong
    secret would have reused an earlier request's "yes"."""
    cached = request.environ.get('suaams.terminal_auth')
    if cached is not None:
        return cached
    supplied_id = request.headers.get('X-Terminal-Id', '')
    supplied_secret = request.headers.get('X-Terminal-Secret', '')
    result = (False, None)
    if supplied_id and supplied_secret:
        terminal = Terminal.query.filter_by(code=supplied_id).first()
        if (terminal is not None and terminal.is_active
                and hmac.compare_digest(hash_secret(supplied_secret), terminal.secret_hash)):
            _touch(terminal)
            result = (True, terminal)
        elif (terminal is None or terminal.is_active) and _legacy_ok(supplied_id, supplied_secret):
            # The changeover: a reader still on the shared secret. If an
            # admin registered it under the same code, use its room. A
            # reader the admin DISABLED is refused whatever it sends.
            if terminal is not None:
                _touch(terminal)
            result = (True, terminal)
    request.environ['suaams.terminal_auth'] = result
    return result


def terminal_for_ble(number):
    """The registered, active reader broadcasting Bluetooth number
    `number`, or None."""
    return Terminal.query.filter_by(ble_number=number, is_active=True).first()


def ble_reader_disabled(number):
    """True if Bluetooth number `number` belongs to a reader an admin has
    DISABLED on the Terminals page.

    A Bluetooth code is checked against BLE_BEACON_SECRET, which every
    reader shares, so a disabled (lost, stolen, decommissioned) board keeps
    broadcasting codes that verify. terminal_for_ble() skips disabled
    readers, which made such a code look like one from an unregistered
    reader: accepted, with no room check. This is the check that refuses
    it. A number no reader is registered under is still accepted, for the
    changeover -- the same rule as the shared NFC secret."""
    return Terminal.query.filter_by(ble_number=number, is_active=False).first() is not None


def normalize_room(room):
    return re.sub(r'[^A-Z0-9]', '', (room or '').upper())


def class_room(session):
    """Where the class is: the room given when it started, else its
    timetable slot's room, else None."""
    if session.room:
        return session.room
    slot = session.timetable
    return slot.room if slot is not None else None


def wrong_room(terminal, session):
    """True if the reader is in a different room from the class, False if
    it's the same room, None if either room is unknown (no check)."""
    if terminal is None or room_check_mode() == 'off':
        return None
    reader, where = normalize_room(terminal.room), normalize_room(class_room(session))
    if not reader or not where:
        return None
    return reader != where


def wrong_room_message(terminal, session):
    return (f"Wrong room: this reader is in {terminal.room}, "
            f"but the class is in {class_room(session)}.")
