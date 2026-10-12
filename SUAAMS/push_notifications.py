"""
Firebase Cloud Messaging helper: persists an in-app Notification row and
best-effort pushes it to every device the recipient has registered. Kept as
its own module (not folded into extensions.py) since it depends on models.py
(Notification, DeviceToken), and extensions.py is deliberately model-free to
avoid a circular import with models.py -> app.py -> extensions.py.
"""
import os
import logging

import firebase_admin
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


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def notify_users(user_ids, notif_type, title, body, data=None):
    """Save an in-app notification for each user, then push it to their phones.

    The Notification rows are saved (and committed) first -- they're what
    the app's notification list reads, so a student who was offline or never
    allowed notifications still sees it. The push on top is best-effort:
    failures are logged and swallowed, never raised, so a Firebase outage
    can't fail the caller's request (e.g. attendance is still recorded).

    PERF: announcements used to call send_push_notification once per
    student: a commit, a token lookup and a blocking FCM request each, ~0.3-
    0.5s per student. A university-wide announcement to 1,000 students ran
    for minutes, was killed at Render's 30s limit (502) half-way through,
    and the admin's retry posted it twice. Now: one bulk INSERT, one token
    lookup and one FCM call per 100 phones.

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
