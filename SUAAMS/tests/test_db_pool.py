"""Tests for the database connection pool cap (db_pool.py).

The database plan allows 5 connections at once. These pin that the pool
can never open more than DB_POOL_SIZE, so nobody quietly removes the cap:

  * the default is 4 with no overflow,
  * DB_POOL_SIZE changes it, and a bad value falls back to 4,
  * a real engine built from these options refuses a connection past the
    cap after pool_timeout, instead of opening another one.

Run with:  python tests/test_db_pool.py
(also collected by pytest if it is installed)
"""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, exc  # noqa: E402
from sqlalchemy.pool import QueuePool  # noqa: E402

import db_pool  # noqa: E402


class PoolOptionsTestCase(unittest.TestCase):

    def test_default_is_four_with_no_overflow(self):
        opts = db_pool.engine_options({})
        self.assertEqual(opts['pool_size'], 4)
        self.assertEqual(opts['max_overflow'], 0)
        # Keeps the check-in window: a wait longer than the token's life is useless.
        self.assertEqual(opts['pool_timeout'], 10)
        self.assertTrue(opts['pool_pre_ping'])

    def test_size_comes_from_the_environment(self):
        self.assertEqual(db_pool.engine_options({'DB_POOL_SIZE': '2'})['pool_size'], 2)
        self.assertEqual(db_pool.engine_options({'DB_POOL_SIZE': ' 9 '})['pool_size'], 9)

    def test_bad_value_falls_back_to_the_default(self):
        for bad in ('0', '-3', 'four', '2.5'):
            with self.subTest(bad=bad), self.assertLogs('suaams', 'WARNING'):
                self.assertEqual(db_pool.pool_size({'DB_POOL_SIZE': bad}), 4)


class PoolCapTestCase(unittest.TestCase):
    """Builds a real engine with the same QueuePool production uses (SQLite
    would otherwise pick its own pool type) and holds every connection, to
    show the next request is refused or waits, never given an extra one.
    check_same_thread=False because the "waits" test frees a connection
    from another thread, as a finishing gunicorn request thread would."""

    def test_no_connection_past_the_cap(self):
        opts = dict(db_pool.engine_options({'DB_POOL_SIZE': '2'}), pool_timeout=0.2)
        engine = create_engine('sqlite:///file:pooltest?mode=memory&uri=true',
                               poolclass=QueuePool,
                               connect_args={'check_same_thread': False},
                               **opts)
        held = [engine.connect(), engine.connect()]
        try:
            with self.assertRaises(exc.TimeoutError):
                engine.connect()
            self.assertEqual(engine.pool.checkedout(), 2)
        finally:
            for c in held:
                c.close()
            engine.dispose()

    def test_waiting_request_gets_a_freed_connection(self):
        # A request that finds the pool full waits its turn rather than failing.
        opts = dict(db_pool.engine_options({'DB_POOL_SIZE': '1'}), pool_timeout=2)
        engine = create_engine('sqlite:///file:pooltest2?mode=memory&uri=true',
                               poolclass=QueuePool,
                               connect_args={'check_same_thread': False},
                               **opts)
        first = engine.connect()
        threading.Timer(0.2, first.close).start()
        try:
            second = engine.connect()   # blocks until the timer frees `first`
            second.close()
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
