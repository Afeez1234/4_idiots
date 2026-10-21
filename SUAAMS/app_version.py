"""Minimum app build: tell an outdated phone to update instead of failing.

The wire format between the app and this API has changed before (the
check-in beacon was rebuilt on 2026-09-25), and an old build talking to a
new server doesn't get a clear error -- its taps just stop working, or a
screen fails to parse a response it no longer understands. Nothing could
tell the student "please update", so nobody knew to.

The app sends its build number (pubspec `version: x.y.z+BUILD`, the part
after the +) as `X-App-Build` on every request. When MIN_APP_BUILD is set,
any app request below it -- or without the header at all, which is every
build from before this existed -- gets:

    426 {"error": "UPDATE REQUIRED", "min_build": <n>, "message": "..."}

and the app swaps to a full-screen "update required" page. `message` is
APP_UPDATE_MESSAGE, present only when set: where to get the new build
("Download it at suaams.com.ng/app"). It comes from the server, not the
app, because the app is sideloaded (no store page to link to) and the
screen showing it ships in builds made long before anyone knows where the
next one will be hosted.

Rules:
  * MIN_APP_BUILD unset, empty or 0 means the gate is OFF. That's the
    default, because when this shipped every installed copy lacked the
    header: set it only once the first build that sends one is out.
  * A value that isn't a whole number is logged and treated as off. A typo
    in Render's environment shouldn't lock every phone out of the app.
  * Only the app's blueprints are gated. The ESP32 readers call
    /api/v1/terminal/status, /api/v1/student/checkin and
    /api/v1/student/checkin/backlog; they don't send an app build and must
    never be told to update. The two student ones are listed by name in
    _TERMINAL_ENDPOINTS because they share the student blueprint.
  * Any change to the wire format bumps MIN_APP_BUILD in the same deploy.

This is a compatibility check, not a security control: the header is
trivially forged. Its job is to turn silent breakage into a clear message.
"""

import logging
import os

from flask import jsonify, request

log = logging.getLogger(__name__)

HEADER = 'X-App-Build'

# Blueprints the Flutter app talks to.
_GATED_BLUEPRINTS = frozenset({'api_auth', 'api_student', 'api_lecturer'})

# Endpoints in those blueprints that the ESP32 readers call, not the app.
_TERMINAL_ENDPOINTS = frozenset({
    'api_student.submit_checkin_beacon',
    'api_student.sync_offline_checkin_backlog',
})


def min_app_build():
    """The configured minimum build, or 0 when the gate is off."""
    raw = os.environ.get('MIN_APP_BUILD', '').strip()
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        log.error('MIN_APP_BUILD=%r is not a whole number; version gate is off', raw)
        return 0


def _client_build():
    try:
        return int(request.headers.get(HEADER, ''))
    except ValueError:
        return None


def check_app_build():
    """before_request hook: a response ends the request, None lets it through."""
    if request.blueprint not in _GATED_BLUEPRINTS:
        return None
    if request.endpoint in _TERMINAL_ENDPOINTS:
        return None
    minimum = min_app_build()
    if not minimum:
        return None
    build = _client_build()
    if build is not None and build >= minimum:
        return None
    body = {'error': 'UPDATE REQUIRED', 'min_build': minimum}
    message = os.environ.get('APP_UPDATE_MESSAGE', '').strip()
    if message:
        body['message'] = message
    return jsonify(body), 426


def init_app(app):
    app.before_request(check_app_build)
