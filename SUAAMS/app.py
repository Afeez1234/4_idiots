from flask import Flask, jsonify, redirect, request, session, url_for
from datetime import timedelta
from flask_migrate import Migrate
from campus_time import campus_fmt
from db_pool import engine_options
import os
import logging
from flask_jwt_extended import JWTManager
from models import db, HOD, Lecturer, Course, Semester, Student, User
from utils import courses_taught_by, current_courses, close_stale_sessions
from extensions import limiter, csrf
import app_version
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.lecturer import lecturer_bp
from blueprints.student import student_bp
from blueprints.hod import hod_bp
from api.auth import api_auth_bp, install_account_check
from api.student import api_student_bp
from api.lecturer import api_lecturer_bp
from api.terminal import api_terminal_bp

# Gives the "suaams" logger (see extensions.py's log_exception/
# api_error_response) an actual handler + format. Without this, exceptions
# logged via logger.exception() still surface (Python's logging module logs
# WARNING+ to stderr by default even unconfigured), but without timestamps
# or a named source -- this makes server-side logs actually readable when
# debugging a reported issue, instead of just a bare traceback.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
)
# Load a local .env if python-dotenv is available. Guarded so a production
# deploy that supplies everything through real environment variables isn't
# broken by the optional import, and so `python app.py` works from a checkout
# the same way `flask run` does.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _require_env(name):
    """Fetch a required environment variable, failing loudly if absent.

    There is deliberately no `default` parameter, and that is the whole
    point. This function used to be a set of os.environ.get(NAME, <literal>)
    calls holding the real production Clever Cloud host, user, password and
    database, plus the session and JWT signing keys. Two things were wrong
    with that:

      1. Those credentials sat in version control for months, in five
         separate commits, and are still in the history now.
      2. The "_missing = [k for k, v in _required.items() if not v]" check
         below them could NEVER fire. os.environ.get had already returned
         the non-empty hardcoded fallback, so every value was truthy. The
         check read like enforcement and enforced nothing -- which is how a
         misconfigured deploy could silently run on published credentials.

    A credential has no safe default. Absent means the app refuses to start.
    """
    value = os.environ.get(name, '').strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            "Set it in your environment or a local .env file (see .env.example). "
            "Do not hardcode credentials in source."
        )
    return value


# Session-cookie and JWT signing keys. Both are load-bearing for
# authentication: SECRET_KEY signs the web portal's session cookie, and
# JWT_SECRET_KEY signs every mobile API token. A value published in the repo
# lets anyone mint an admin session or a valid JWT.
SECRET_KEY = _require_env('SECRET_KEY')
JWT_SECRET = _require_env('JWT_SECRET_KEY')

# Database connection settings.
DB_HOST = _require_env('DB_HOST')
DB_USER = _require_env('DB_USER')
DB_PASSWORD = _require_env('DB_PASSWORD')
DB_NAME = _require_env('DB_NAME')
# Port is not a credential, so a default is fine here.
DB_PORT = os.environ.get('DB_PORT', '3306')

# Beacon/terminal credentials are validated lazily where they're used (see
# beacon._signing_secret and api/student._check_terminal_auth) rather than
# here, so that a deployment without them still serves the rest of the app
# and only check-in is disabled -- with a logged reason, not a crash loop.

app = Flask(__name__)

# Core config
app.secret_key = SECRET_KEY
# Send the web session cookie over HTTPS only. Without this, someone typing
# http://suaams... on public Wi-Fi sends their signed-in cookie unencrypted
# before the redirect to HTTPS, where anyone on that network can copy it.
# Local development still works: browsers treat http://localhost as secure.
app.config['SESSION_COOKIE_SECURE'] = True
app.config['JWT_SECRET_KEY'] = JWT_SECRET

# Explicit JWT lifetimes -- previously unset, which silently rode on
# Flask-JWT-Extended's built-in 15-minute access-token default with no
# refresh token at all. Now explicit and paired with a real refresh flow
# (see api/auth.py's /refresh endpoint and User.current_refresh_jti in
# models.py for the rotation/revocation mechanics).
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=14)

# SQLAlchemy config
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# A fixed pool with no overflow (DB_POOL_SIZE, default 4), because the
# database plan allows only 5 connections at once. See db_pool.py for the
# numbers and the rule for changing them. The old SQLALCHEMY_POOL_SIZE/
# _RECYCLE/_TIMEOUT keys were removed: Flask-SQLAlchemy 3 ignores them, so
# they never took effect. Engine options go in this dict.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options()

# Initialize extensions
db.init_app(app)
migrate = Migrate(app,db)
jwt = JWTManager(app)
# Every app request re-checks that the account is still active (see
# api/auth.install_account_check), not only at login and refresh.
install_account_check(jwt)
# See extensions.py for the in-memory-vs-Redis storage tradeoff note.
limiter.init_app(app)
csrf.init_app(app)
# Outdated app builds get 426 "UPDATE REQUIRED" once MIN_APP_BUILD is set.
# See app_version.py for which routes are gated and why readers aren't.
app_version.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(lecturer_bp)
app.register_blueprint(student_bp)
app.register_blueprint(hod_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(api_student_bp)
app.register_blueprint(api_lecturer_bp)
app.register_blueprint(api_terminal_bp)  # reader door-screen status

# CSRFProtect covers the whole app by default -- exempt the JSON API
# blueprints here rather than relying on per-route decorators, since every
# route in these blueprints is either JWT-header-authenticated (the mobile
# ones) or authenticated by reader headers (api_terminal_bp and the check-in
# routes, hit by the ESP32 firmware) -- never cookie-authenticated (see extensions.py's csrf comment
# for why that means they aren't CSRF-vulnerable in the first place).
# Without this, every mobile request would fail with a CSRF error the
# moment CSRFProtect went live, since neither the Flutter app nor the
# ESP32 firmware has a csrf_token to send.
csrf.exempt(api_auth_bp)
csrf.exempt(api_student_bp)
csrf.exempt(api_lecturer_bp)
csrf.exempt(api_terminal_bp)


# End sessions left open from earlier days (utils.close_stale_sessions; does
# real work at most every 10 minutes). Guarded: a failed sweep is logged and
# the request carries on, rather than every page failing with it.
@app.before_request
def _close_stale_sessions():
    if request.endpoint in (None, 'static', 'healthz'):
        return
    try:
        close_stale_sessions()
    except Exception:
        db.session.rollback()
        logging.getLogger('suaams').exception('Stale session sweep failed')


# Registered app-wide (not on hod_bp/lecturer_bp individually) because
# base_portal.html -- the single shared shell for both roles -- needs both
# the "Department" and "My Courses" sidebar sections available no matter
# which blueprint actually rendered the current page. A blueprint-scoped
# context_processor only fires for that blueprint's own routes, which is
# exactly what broke the old two-portal layout: visiting a lecturer page
# had no HOD data available to render an HOD nav section, and vice versa.
# Replaces the old inject_hod_context() (hod.py) and inject_lecturer_context()
# (lecturer.py), which this consolidates.
# `{{ value|campus }}` / `{{ value|campus('%d %b %Y, %H:%M') }}`: shows a
# stored UTC moment in campus time. Timetable times (planned_start etc.)
# are already campus time and must NOT go through it. See campus_time.py.
app.jinja_env.filters['campus'] = campus_fmt


@app.context_processor
def inject_portal_context():
    user_id = session.get('user_id')
    if not user_id or session.get('role') not in ('lecturer', 'hod'):
        return {}

    hod = HOD.query.filter_by(user_id=user_id).first()
    lecturer = Lecturer.query.filter_by(user_id=user_id).first()

    context = {
        'has_hod_profile': hod is not None,
        'has_lecturer_profile': lecturer is not None,
    }
    if hod:
        context['hod_department'] = hod.department
    if lecturer:
        # This semester's courses only (utils.current_courses).
        context['sidebar_courses'] = current_courses(courses_taught_by(lecturer)).order_by(Course.course_code).all()
        context['active_semester'] = Semester.query.filter_by(is_active=True).first()
    return context



# Who is signed in, for the rail's footer (_shell.html): the person's name
# from their profile and a properly cased role. The footer used to show the
# session username -- a staff ID or matric number -- and capitalise the role
# as "Hod". An admin has no profile, so their username stays. Two indexed
# lookups per page; nothing for a signed-out visitor.
ROLE_LABELS = {'admin': 'Admin', 'lecturer': 'Lecturer', 'hod': 'HOD', 'student': 'Student'}


@app.context_processor
def inject_rail_identity():
    user_id = session.get('user_id')
    if not user_id:
        return {}
    role = session.get('role')
    profile_model = {'student': Student, 'lecturer': Lecturer, 'hod': HOD}.get(role)
    profile = profile_model.query.filter_by(user_id=user_id).first() if profile_model else None
    name = profile.full_name if profile else session.get('username')
    return {'rail_name': name, 'rail_role': ROLE_LABELS.get(role, '')}


# Keep-warm target for an external scheduler (e.g. an uptime-monitor ping or
# a GitHub Actions cron job) hitting this every ~10-14 minutes, so Render's
# free-tier dyno never fully spins down from inactivity in the first place --
# a cold dyno is what turned a single beacon-token POST into a ~1.8s round
# trip during hardware testing, which is enough on its own to blow past the
# BEACON_TOKEN_TTL_SECONDS window (10s; see beacon.py). Deliberately
# doesn't touch the DB: this only needs to keep the web process itself alive,
# and a DB failure here would give the external monitor a false "down".
@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok"}), 200


# The site root sends visitors to the login page. It had a blueprint of its
# own (api/hardware.py) until 2026-10-23: all that was left of the old
# RFID-card terminal's routes, POST /attendance and GET /sessions/active,
# removed on 2026-10-12. Nothing called them, and /attendance credited "the
# newest active session in any course", the mistake the signed check-in code
# exists to prevent. The retired card sketches still point at /attendance
# and get a 404.
@app.route('/')
def home():
    return redirect(url_for('auth.login'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)