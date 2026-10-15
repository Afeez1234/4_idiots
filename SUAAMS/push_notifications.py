"""
Firebase Cloud Messaging helper: persists an in-app Notification row and
best-effort pushes it to every device the recipient has registered. Kept as
its own module (not folded into extensions.py) since it depends on models.py
(Notification, DeviceToken), and extensions.py is deliberately model-free to
avoid a circular import with models.py -> app.py -> extensions.py.
"""
import os
import logging
from concurrent.futures import ThreadPoolExecutor

import firebase_admin
from flask import current_app
from firebase_admin import credentials, messaging
from sqlalchemy import insert as sa_insert

from models import db, DeviceToken, Notification

logger = logging.getLogger("suaams")

# Defaults to a gitignored file living next to this module -- see
# SUAAMS/.gitignore. Overridable via env var for deployment (e.g. Render),
# where the key should be provided as a secret file / env-mounted path
# rather than committed to the repo.
_FIREBASE_CREDENTIALS_PATH = os.environ.get(
    'FIREBASE_CREDENTIALS_PATH',
    os.path.join(os.path.dirname(__file__), 'firebase-service-account.json'),
)

_firebase_app = None


def _get_firebase_app():
    # Lazy init, not at import time: importing this module must never crash
    # app.py just because the key file isn't present yet (e.g. local dev
    # before Firebase is set up) -- the failure should surface only when a
    # push actually needs sending, and only as a logged/caught exception
    # (see send_push_notification below), not an app-boot crash.
    global _firebase_app
    if _firebase_app is None:
        if not os.path.exists(_FIREBASE_CREDENTIALS_PATH):
            raise RuntimeError(
                f"Firebase service account key not found at {_FIREBASE_CREDENTIALS_PATH}. "
                "Set FIREBASE_CREDENTIALS_PATH or place the key at that path."
            )
        cred = credentials.Certificate(_FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


# Rows per bulk INSERT / IN (...) lookup.
_DB_CHUNK = 500

# Messages per FCM send_each() call. send_each sends every message as its
# own HTTPS request, in parallel, with ONE THREAD PER MESSAGE (see
# firebase_admin.messaging). 500 is FCM's ceiling; 100 keeps a batch to 100
# threads on Render's small free-tier instance while still being ~100x
# faster than one-at-a-time.
_PUSH_BATCH = 100


# Phone pushes run here, AFTER the request has answered (see notify_users).
# Two threads: enough to keep up with a busy hall (a push is ~0.3-0.5s, a
# tap arrives every second or two per terminal), and a burst of taps queues
# instead of starting hundreds of threads on Render's small instance. Each
# gunicorn worker process gets its own pool, started on first use.
_push_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='push')


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def notify_users(user_ids, notif_type, title, body, data=None):
    """Save an in-app notification for each user, then push it to their phones.

    The Notification rows are saved (and committed) here, in the request --
    they're what the app's notification list reads, so a student who was
    offline or never allowed notifications still sees it. The phone push is
    handed to a background thread (_push_pool) and the caller returns at
    once; it's best-effort, and its failures are logged, never raised.

    Why in the background: check-in calls this between saving attendance
    and answering the terminal, and the terminal reads one student at a
    time. A push is ~0.3-0.5s (token lookup + the Firebase round trip), so
    every student in the queue waited for the previous one's push -- for a
    200-student hall, 1-1.7 extra minutes at the door. The attendance is
    already saved before the push, and the app confirms a tap by asking
    the server (/checkin/status), not by waiting for the push.

    Under TESTING the push runs inline, so tests can check what was sent
    without waiting on a thread. tests/test_notifications.py also pins the
    background path.

    PERF: announcements used to call send_push_notification once per
    student: a commit, a token lookup and a blocking FCM request each, ~0.3-
    0.5s per student. A university-wide announcement to 1,000 students ran
    for minutes, was killed at Render's 30s limit (502) half-way through,
    and the admin's retry posted it twice. Now: one bulk INSERT, one token
    lookup and one FCM call per 100 phones -- and none of it holds up the
    admin's page.

    `data` is an optional dict (e.g. {"session_id": 5}) the app uses to open
    the right screen when the notification is tapped.
    """
    user_ids = list(dict.fromkeys(user_ids))  # de-duplicate, keep order
    if not user_ids:
        return

    for chunk in _chunks(user_ids, _DB_CHUNK):
        db.session.execute(sa_insert(Notification), [
            {'user_id': uid, 'type': notif_type, 'title': title, 'body': body, 'data': data}
            for uid in chunk
        ])
    db.session.commit()

    if current_app.testing:
        _push_to_phones(user_ids, notif_type, title, body, data)
    else:
        _push_pool.submit(_push_in_background, current_app._get_current_object(),
                          user_ids, notif_type, title, body, data)


def _push_in_background(app, *args):
    """Runs on a _push_pool thread: its own app context, so its own database
    session (released when the context ends). Anything that escapes is
    logged -- the pool would otherwise drop the error silently."""
    try:
        with app.app_context():
            _push_to_phones(*args)
    except Exception:
        logger.exception("Background push failed")


def _push_to_phones(user_ids, notif_type, title, body, data):
    """Send one notification to every phone the users have registered, in
    batches, pruning tokens Firebase says are dead."""
    tokens = []
    for chunk in _chunks(user_ids, _DB_CHUNK):
        tokens.extend(DeviceToken.query.filter(DeviceToken.user_id.in_(chunk)).all())
    if not tokens:
        return

    try:
        app = _get_firebase_app()
    except Exception:
        logger.exception("Firebase not configured -- skipping push send, notification saved in-app only")
        return

    # FCM data-message payload values must all be strings.
    payload = {str(k): str(v) for k, v in (data or {}).items()}
    payload['type'] = notif_type

    stale_token_ids = []
    for batch in _chunks(tokens, _PUSH_BATCH):
        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload,
                token=t.fcm_token,
            )
            for t in batch
        ]
        try:
            response = messaging.send_each(messages, app=app)
        except Exception:
            logger.exception("Push batch failed (%d messages)", len(messages))
            continue
        for device_token, result in zip(batch, response.responses):
            if result.success:
                continue
            if isinstance(result.exception, messaging.UnregisteredError):
                # The app instance behind this token no longer exists
                # (uninstalled, or Firebase issued it a new token) -- prune
                # it so it isn't retried on every future push.
                stale_token_ids.append(device_token.id)
            else:
                logger.warning("Push send failed for device_token id=%s: %s",
                               device_token.id, result.exception)

    if stale_token_ids:
        DeviceToken.query.filter(DeviceToken.id.in_(stale_token_ids)).delete(synchronize_session=False)
        db.session.commit()


def send_push_notification(user, notif_type, title, body, data=None):
    """One user's notification (check-in confirmed, device unlocked, ...).
    Same path as notify_users, so there is one way notifications are sent."""
    notify_users([user.id], notif_type, title, body, data)
