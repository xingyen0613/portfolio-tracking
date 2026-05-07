import subprocess
import sys

from config.db import get_conn
from config.settings import LOGS_DIR


def init_db() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()


def execute(query: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        conn.execute(query, params)


def get_account_id(platform_name: str, account_key: str, user_id: str) -> int:
    row = fetch_one(
        """
        SELECT a.id FROM accounts a
        JOIN platforms p ON a.platform_id = p.id
        WHERE p.name = %s AND a.account_key = %s AND a.user_id = %s
        """,
        (platform_name, account_key, user_id),
    )
    if row is None:
        raise ValueError(f"Account not found: {platform_name}/{account_key} for user {user_id}")
    return row["id"]
