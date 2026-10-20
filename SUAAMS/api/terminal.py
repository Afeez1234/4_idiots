# Routes the reader (ESP32 terminal) calls for itself, rather than to submit
# a student's check-in. See terminal_status.py for what the door screen
# shows and why.
from flask import Blueprint, jsonify

import terminal_rooms
from extensions import limiter, api_error_response
from api.student import _check_terminal_auth, terminal_or_ip_key
from terminal_status import status_for

api_terminal_bp = Blueprint('api_terminal', __name__, url_prefix='/api/v1/terminal')


# A reader asks once a minute; 10 leaves room for reboots and retries
# without letting a runaway one hammer the database.
@api_terminal_bp.route('/status', methods=['GET'])
@limiter.limit("10 per minute", key_func=terminal_or_ip_key)
def terminal_status():
    """The class in this reader's room now, and the next one today.

    Signed like a check-in (X-Terminal-Id / X-Terminal-Secret): course codes
    and counts aren't secret, but there's no reason to hand them out, and
    the answer depends on which reader is asking.
    """
    if not _check_terminal_auth():
        return jsonify({"error": "Unauthorized terminal"}), 401
    try:
        _ok, terminal = terminal_rooms.authenticate()
        return jsonify(status_for(terminal)), 200
    except Exception:
        return api_error_response("Terminal Status Error", "Failed to load status")
