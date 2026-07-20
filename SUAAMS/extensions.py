# Shared Flask extension instances that need to be importable from both
# app.py and the blueprint/api modules without circular imports -- same
# reason models.py declares `db = SQLAlchemy()` on its own and app.py calls
# `db.init_app(app)` later, instead of blueprints importing `app` directly.
import logging
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect

# Single named logger for the whole backend. Using Python's logging module
# instead of bare print() gives us: (1) full stack traces via
# logger.exception() -- print(f"...: {e}") only ever captured str(e), which
# is often useless for actually debugging a production failure, and
# (2) log levels/timestamps, so this is filterable in whatever log viewer
# Render surfaces. See app.py for the logging.basicConfig() call that gives
# this a handler + format.
logger = logging.getLogger("suaams")

# PERF/SCALE NOTE: no storage_uri is set, so Flask-Limiter defaults to its
# in-memory backend. That only enforces limits correctly as long as this
# Flask process is the SOLE worker handling traffic -- if Render is ever
# configured to run more than one gunicorn worker/instance, each process
# keeps its own separate counters, so a "5 per minute" limit effectively
# becomes "5 x worker-count per minute". To fix that when/if this scales
# past a single worker, set storage_uri to a redis:// URL (Render Redis
# add-on or Upstash) here -- none of the @limiter.limit(...) call sites
# elsewhere in the codebase need to change.
limiter = Limiter(key_func=get_remote_address)

# CSRF protection for the session-cookie-authenticated web dashboards
# (blueprints/auth.py, admin.py, lecturer.py). Applies to the whole app by
# default once initialized, which is why the mobile API blueprints and the
# bare ESP32-facing /attendance route in app.py are explicitly exempted --
# both are authenticated via an Authorization header (JWT) or not
# authenticated via cookies at all, never via a browser-managed session
# cookie, so they aren't CSRF-vulnerable the way the web forms are, and a
# non-browser client (Flutter's http package, the ESP32's HTTPClient) has
# no CSRF token to send in the first place.
csrf = CSRFProtect()


def jwt_identity_or_ip():
    """
    Rate-limit key_func for JWT-protected routes: keys by the logged-in
    user's id instead of their IP, so limits track "this account" rather
    than "this network address" (matters for shared campus WiFi/NAT, where
    many students share one public IP). Falls back to IP if no valid JWT is
    present, so it's also safe to use as a defensive key_func even on routes
    that don't strictly require a token.

    Calls verify_jwt_in_request() directly rather than relying on
    @jwt_required() having already run: Flask-Limiter evaluates key_func
    while checking the limit, which happens BEFORE the route's own
    @jwt_required() decorator executes (decorators closer to the route
    function run first). verify_jwt_in_request(optional=True) is safe to
    call here even though @jwt_required() will call the equivalent
    verification again immediately after -- it just re-parses the same
    Authorization header, no side effects.
    """
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            return f"user:{identity}"
    except Exception:
        pass
    return get_remote_address()


def log_exception(label):
    """
    Call this from inside an `except` block (any block, web or API). Logs
    the exception currently being handled -- message AND full stack trace,
    via logger.exception(), which reads it off sys.exc_info() automatically
    -- under `label` so it's greppable in server logs (e.g. "Dashboard
    Error", "Start Session Error"). This replaces the old
    print(f"...: {e}") calls scattered through the blueprints, which only
    ever logged the exception's string form and never a traceback.
    """
    logger.exception(label)


def api_error_response(label, client_message, status=500):
    """
    Call this from inside an `except` block on a JSON API route in place of
    hand-writing `jsonify({"error": ..., "details": str(e)})`. Logs the full
    exception server-side (see log_exception) and returns ONLY the generic
    `client_message` to the caller -- never the original exception text,
    which can leak DB schema/table/column names, query fragments, or file
    paths to whoever is calling the API.
    """
    log_exception(label)
    return jsonify({"error": client_message}), status
