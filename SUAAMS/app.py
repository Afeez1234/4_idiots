from flask import Flask
from datetime import timedelta
from flask_migrate import Migrate
import os
import logging
from flask_jwt_extended import JWTManager
from models import db
from extensions import limiter, csrf
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.lecturer import lecturer_bp
from blueprints.student import student_bp
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
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'bikxczmqtd1kynudsfrp-mysql.services.clever-cloud.com'),
    'user': os.environ.get('DB_USER', 'uo5woagbfvcducyy'),
    'password': os.environ.get('DB_PASSWORD', 'edVtI3biNQmhQrfJwRe8'),
    'database': os.environ.get('DB_NAME', 'bikxczmqtd1kynudsfrp'),
    'port': int(os.environ.get('DB_PORT', 3306))
}

SECRET_KEY = os.environ.get('SECRET_KEY', 'suaams_secret_key_2025')



SECRET_KEY = os.environ.get('SECRET_KEY', 'suaams_secret_key_2025')
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'suaams_jwt_secret_key_2025')

# Database connection string for SQLAlchemy
DB_HOST = os.environ.get('DB_HOST', 'bikxczmqtd1kynudsfrp-mysql.services.clever-cloud.com')
DB_USER = os.environ.get('DB_USER', 'uo5woagbfvcducyy')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'edVtI3biNQmhQrfJwRe8')
DB_NAME = os.environ.get('DB_NAME', 'bikxczmqtd1kynudsfrp')
DB_PORT = os.environ.get('DB_PORT', '3306')

_required = {
    'SECRET_KEY': SECRET_KEY, 'JWT_SECRET_KEY': JWT_SECRET, 'DB_HOST': DB_HOST,
    'DB_USER': DB_USER, 'DB_PASSWORD': DB_PASSWORD, 'DB_NAME': DB_NAME,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "Set them in your environment or a local .env — do not hardcode credentials in source."
    )

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


# The ESP32-facing routes (/, /sessions/active, /sessions/active/<id>,
# /attendance) and their helper functions used to live here. Moved to
# api/hardware.py (api_hardware_bp, registered above) -- same kind of JSON
# API blueprint as api/auth.py and api/student.py, just never migrated
# when those were extracted.


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)