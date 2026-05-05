"""PostgreSQL connection pool and context manager.

Replaces app/storage/sqlite.py's get_conn() for all database access.
Uses psycopg2 SimpleConnectionPool so connections are reused across requests.
"""

from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

from config.settings import DATABASE_URL

_pool: psycopg2.pool.SimpleConnectionPool | None = None


def get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


class _ConnWrapper:
    """Wraps a psycopg2 connection to expose a sqlite3-compatible execute() interface.

    sqlite3 allows calling conn.execute(sql, params) directly.
    psycopg2 requires conn.cursor().execute(sql, params).
    This wrapper bridges the gap so existing call sites need minimal changes.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> Any:
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, params_list: list) -> Any:
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.executemany(sql, params_list)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    # Allow pandas.read_sql_query(sql, conn) to work by passing the raw connection
    @property
    def raw(self) -> Any:
        return self._conn


@contextmanager
def get_conn():
    """Context manager that yields a _ConnWrapper backed by a pooled psycopg2 connection.

    Commits on clean exit, rolls back on exception, returns connection to pool on exit.
    The yielded object supports conn.execute(sql, params) like sqlite3.
    """
    pool = get_pool()
    conn = pool.getconn()
    wrapped = _ConnWrapper(conn)
    try:
        yield wrapped
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
