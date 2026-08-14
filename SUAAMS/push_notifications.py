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


def send_push_notification(user, notif_type, title, body, data=None):
    """
    Call this from inside the same request/transaction as the event that
    triggers it (e.g. right after an Attendance row is committed). Always
    persists the in-app Notification row first -- that's the source of
    truth the notification list screen reads from, so a student who was
    offline (or never granted notification permission) still sees it next
    time they open the app. The FCM push itself is best-effort on top: any
    failure here is logged and swallowed, never raised, so a transient push
    failure can't fail the caller's own request (e.g. attendance still gets
    recorded even if FCM is down).

    `data` is an optional dict of extra fields (e.g. {"session_id": 5}) used
    for deep-linking a notification tap to the relevant screen client-side.
    """
    notification = Notification(
        user_id=user.id, type=notif_type, title=title, body=body, data=data,
    )
    db.session.add(notification)
    db.session.commit()

    tokens = DeviceToken.query.filter_by(user_id=user.id).all()
    if not tokens:
        return notification

    try:
        app = _get_firebase_app()
    except Exception:
        logger.exception("Firebase not configured -- skipping push send, notification saved in-app only")
        return notification

    # FCM data-message payload values must all be strings.
    payload = {str(k): str(v) for k, v in (data or {}).items()}
    payload['type'] = notif_type

    stale_token_ids = []
    for device_token in tokens:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=payload,
            token=device_token.fcm_token,
        )
        try:
            messaging.send(message, app=app)
        except messaging.UnregisteredError:
            # Token belongs to an app instance that no longer exists
            # (uninstalled, or Firebase reissued a new token for it) --
            # prune it so it isn't retried forever on every future push.
            stale_token_ids.append(device_token.id)
        except Exception:
            logger.exception(f"Push send failed for device_token id={device_token.id}")

    if stale_token_ids:
        DeviceToken.query.filter(DeviceToken.id.in_(stale_token_ids)).delete(synchronize_session=False)
        db.session.commit()

    return notification
