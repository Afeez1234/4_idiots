"""Audit trail: who changed what through the admin dashboard.

Why this exists
---------------
Several people share admin access. Each has a personal login (made with
create_admin.py), and every change they make through the dashboard is
recorded here with their name on it. The admin Activity page
(/admin/activity) reads it back.

How to record something
-----------------------
Call log_action() just BEFORE the db.session.commit() that saves the change,
so the change and its log entry are saved together or not at all:

    db.session.add(student)
    log_action('student.create', f"Created student {name} ({matric})",
               'student', student.id, {'department': dept.name})
    db.session.commit()

The model itself (AuditLog) lives in models.py with the other tables, so
Flask-Migrate sees it.
"""
from flask import has_request_context, session

from extensions import client_ip
from models import db, AuditLog

# Keys whose values are never written to the log, at any depth in
# `details`. Exact key names only: "code" is NOT here even though it sounds
# secret, because the course form's field for "MCT 401" is called `code`,
# and hiding course codes would make the log useless for courses.
SENSITIVE_KEYS = {
    'password', 'new_password', 'confirm_password', 'password_hash',
    'temp_password', 'token', 'access_token', 'refresh_token',
    'beacon_token', 'secret', 'terminal_secret', 'fcm_token',
}


def _current_actor():
    """(id, label, role) for whoever is making the current request.

    The web dashboards keep the logged-in user in Flask's session cookie
    (blueprints/auth.py sets user_id / username / role at login). The mobile
    API uses JWTs instead. Anything else -- a script, a background job --
    passes `actor=` to log_action explicitly.
    """
    if not has_request_context():
        return None, 'system', 'system'

    if session.get('user_id'):
        return session['user_id'], session.get('username') or f"user:{session['user_id']}", session.get('role')

    try:
        from flask_jwt_extended import get_jwt, get_jwt_identity
        identity = get_jwt_identity()
        if identity is not None:
            return int(identity), f'user:{identity}', get_jwt().get('role')
    except Exception:
        # No JWT on this request (or not inside a JWT-protected view).
        pass

    return None, 'anonymous', None


def _client_ip():
    """The user's IP address, or None outside a request. Same rule as the
    rate limiter (extensions.client_ip), so the two never disagree."""
    if not has_request_context():
        return None
    return client_ip()


def _scrub(value):
    """Copy of `value` with every sensitive key's value replaced."""
    if isinstance(value, dict):
        return {
            k: '[redacted]' if str(k).lower() in SENSITIVE_KEYS else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def _jsonable(value):
    """Make dates, times and other non-JSON values storable as text."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def changes(old: dict, new: dict) -> dict:
    """{field: {'from': old, 'to': new}} for only the fields that changed."""
    out = {}
    for key, new_val in new.items():
        old_val = old.get(key)
        if old_val != new_val:
            out[key] = {'from': old_val, 'to': new_val}
    return out


def log_action(action, summary, entity_type=None, entity_id=None,
               details=None, actor=None):
    """Queue an audit entry on the current database session.

    Not committed here -- see the module docstring. `actor` is an optional
    (id, label, role) tuple for code running outside a web request, such as
    create_admin.py.
    """
    actor_id, actor_label, actor_role = actor or _current_actor()
    entry = AuditLog(
        actor_id=actor_id,
        actor_label=str(actor_label)[:100],
        actor_role=actor_role,
        action=action,
        summary=str(summary)[:255],
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=_jsonable(_scrub(details)) if details else None,
        ip_address=_client_ip(),
    )
    db.session.add(entry)
    return entry
