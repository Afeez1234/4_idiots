from flask import Flask, jsonify, session
from datetime import timedelta
from flask_migrate import Migrate
import os
import logging
from flask_jwt_extended import JWTManager
from models import db, HOD, Lecturer, Course, Semester
from extensions import limiter, csrf
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.lecturer import lecturer_bp
from blueprints.student import student_bp
from blueprints.hod import hod_bp
from api.auth import api_auth_bp
from api.student import api_student_bp
from api.lecturer import api_lecturer_bp
from api.hardware import api_hardware_bp

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

# Kept because other modules read these keys. Every value is now sourced from
# a required environment variable above -- the dict itself is no longer a
# place secrets can hide.
DB_CONFIG = {
    'host': DB_HOST,
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'port': int(DB_PORT),
}

# Beacon/terminal credentials are validated lazily where they're used (see
# beacon._signing_secret and api/student._check_terminal_auth) rather than
# here, so that a deployment without them still serves the rest of the app
# and only check-in is disabled -- with a logged reason, not a crash loop.

app = Flask(__name__)

# Core config
app.secret_key = SECRET_KEY
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
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 280  # Recycle connections before MySQL times them out
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 20
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,   # Recycle connections before the 300-second cloud timeout
    'pool_pre_ping': True  # Test the connection to ensure it's alive before querying
}

# Initialize extensions
db.init_app(app)
migrate = Migrate(app,db)
jwt = JWTManager(app)
# See extensions.py for the in-memory-vs-Redis storage tradeoff note.
limiter.init_app(app)
csrf.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(lecturer_bp)
app.register_blueprint(student_bp)
app.register_blueprint(hod_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(api_student_bp)
app.register_blueprint(api_lecturer_bp)
app.register_blueprint(api_hardware_bp)

# CSRFProtect covers the whole app by default -- exempt the JSON API
# blueprints here rather than relying on per-route decorators, since every
# route in these blueprints is either JWT-header-authenticated (the mobile
# ones) or has no session/auth at all (api_hardware_bp, hit by the ESP32
# firmware) -- never cookie-authenticated (see extensions.py's csrf comment
# for why that means they aren't CSRF-vulnerable in the first place).
# Without this, every mobile request would fail with a CSRF error the
# moment CSRFProtect went live, since neither the Flutter app nor the
# ESP32 firmware has a csrf_token to send.
csrf.exempt(api_auth_bp)
csrf.exempt(api_student_bp)
csrf.exempt(api_lecturer_bp)
csrf.exempt(api_hardware_bp)


# Registered app-wide (not on hod_bp/lecturer_bp individually) because
# base_portal.html -- the single shared shell for both roles -- needs both
# the "Department" and "My Courses" sidebar sections available no matter
# which blueprint actually rendered the current page. A blueprint-scoped
# context_processor only fires for that blueprint's own routes, which is
# exactly what broke the old two-portal layout: visiting a lecturer page
# had no HOD data available to render an HOD nav section, and vice versa.
# Replaces the old inject_hod_context() (hod.py) and inject_lecturer_context()
# (lecturer.py), which this consolidates.
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
        context['sidebar_courses'] = Course.query.filter_by(lecturer_id=lecturer.id).order_by(Course.course_code).all()
        context['active_semester'] = Semester.query.filter_by(is_active=True).first()
    return context


# Keep-warm target for an external scheduler (e.g. an uptime-monitor ping or
# a GitHub Actions cron job) hitting this every ~10-14 minutes, so Render's
# free-tier dyno never fully spins down from inactivity in the first place --
# a cold dyno is what turned a single beacon-token POST into a ~1.8s round
# trip during hardware testing, which is enough on its own to blow past the
# 3-second BEACON_TOKEN_TTL_SECONDS window (see api/student.py). Deliberately
# doesn't touch the DB: this only needs to keep the web process itself alive,
# and a DB failure here would give the external monitor a false "down".
@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok"}), 200


# The ESP32-facing routes (/, /sessions/active, /sessions/active/<id>,
# /attendance) and their helper functions used to live here. Moved to
# api/hardware.py (api_hardware_bp, registered above) -- same kind of JSON
# API blueprint as api/auth.py and api/student.py, just never migrated
# when those were extracted.


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)