import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.models.schema import CREATE_TABLES, SEED_ACCOUNTS, SEED_PLATFORMS
from config.settings import DB_PATH, LOGS_DIR, SQLITE_DIR


def init_db() -> None:
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(CREATE_TABLES)
        conn.executescript(SEED_PLATFORMS)
        conn.executescript(SEED_ACCOUNTS)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def execute(query: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        conn.execute(query, params)


def get_account_id(platform_name: str, account_key: str) -> int:
    row = fetch_one(
        """
        SELECT a.id FROM accounts a
        JOIN platforms p ON a.platform_id = p.id
        WHERE p.name = ? AND a.account_key = ?
        """,
        (platform_name, account_key),
    )
    if row is None:
        raise ValueError(f"Account not found: {platform_name}/{account_key}")
    return row["id"]
