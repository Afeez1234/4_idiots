"""Database connection-pool settings, kept apart from app.py so a test can
check them without starting the app (app.py needs real credentials).

Why a hard cap: Clever Cloud's MySQL plan allows each database user only
5 connections at once (`max_user_connections`, checked 2026-10-16 on both
the production and dev databases). SQLAlchemy's default pool opens up to
15 per worker (5 + 10 overflow), and production runs 8 request threads plus
2 push threads (push_notifications._push_pool). When a class tapped in all
at once, connection 6 would be refused by MySQL and that request would
fail with a 500. With a fixed pool and no overflow, the 6th request waits
for a free connection instead of failing.

The rule: gunicorn workers x DB_POOL_SIZE + 1 <= the plan's connection
limit. The +1 is kept free for the nightly backup (.github/workflows/
db-backup.yml) or someone running a script against production. Render's
start command runs 1 worker, so the default is 4. On a bigger plan, or with
more workers, change DB_POOL_SIZE on Render; no code change is needed.
"""

import logging
import os

logger = logging.getLogger('suaams')

DEFAULT_POOL_SIZE = 4

# How long a request waits for a free connection before giving up. Matches
# BEACON_TOKEN_TTL_SECONDS (beacon.py): the terminal's /checkin looks the
# reader up in the database BEFORE it checks the token's expiry, so time
# spent waiting here comes out of the student's 10 seconds. Past that the
# token is dead anyway, and waiting longer only ties up a thread.
# SQLAlchemy's default is 30.
POOL_TIMEOUT_SECONDS = 10


def pool_size(environ=os.environ):
    """DB_POOL_SIZE from the environment. Not a credential, so a default is
    fine. A typo falls back to the default with a warning rather than
    stopping the app or opening an unlimited pool."""
    raw = environ.get('DB_POOL_SIZE', '').strip()
    if not raw:
        return DEFAULT_POOL_SIZE
    try:
        size = int(raw)
    except ValueError:
        size = 0
    if size < 1:
        logger.warning("DB_POOL_SIZE=%r is not a whole number of at least 1; "
                       "using %d", raw, DEFAULT_POOL_SIZE)
        return DEFAULT_POOL_SIZE
    return size


def engine_options(environ=os.environ):
    """SQLALCHEMY_ENGINE_OPTIONS for app.py."""
    return {
        'pool_size': pool_size(environ),
        # 0 is what makes pool_size a ceiling. Without it pool_size is only
        # how many connections stay open; overflow could still exceed the cap.
        'max_overflow': 0,
        'pool_timeout': POOL_TIMEOUT_SECONDS,
        'pool_recycle': 280,   # Recycle connections before the 300-second cloud timeout
        'pool_pre_ping': True,  # Test the connection to ensure it's alive before querying
    }
