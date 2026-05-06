"""
Migrate data from local PostgreSQL to Supabase PostgreSQL.

Reads from local PG, writes to Supabase (DATABASE_URL in .env).
Run AFTER alembic upgrade head on Supabase.

Usage:
    uv run python scripts/migrate_local_pg_to_supabase.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
from config.settings import DATABASE_URL

LOCAL_URL = "postgresql://portfolio:portfolio_dev@localhost:5432/portfolio"
SUPABASE_URL = DATABASE_URL


def conn_dict(url, disable_timeout=False):
    c = psycopg2.connect(url)
    c.autocommit = True
    if disable_timeout:
        c.cursor().execute("SET statement_timeout = 0")
    return c


def rows(src, table):
    cur = src.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM {table}")
    return cur.fetchall()


def upsert(dst, table, data, conflict_cols):
    if not data:
        return 0
    cur = dst.cursor()
    cols = list(data[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    conflict = ", ".join(conflict_cols)
    update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict_cols)
    sql = (
        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {update_set}"
    )
    for row in data:
        cur.execute(sql, list(row.values()))
    return len(data)


def main():
    print(f"Source: {LOCAL_URL[:50]}...")
    print(f"Target: {SUPABASE_URL[:50]}...")

    src = conn_dict(LOCAL_URL)
    dst = conn_dict(SUPABASE_URL, disable_timeout=True)

    tables = [
        ("platforms",           ["name"]),
        ("users",               ["id"]),
        ("accounts",            ["platform_id", "account_key", "user_id"]),
        ("batches",             ["id"]),
        ("source_runs",         ["id"]),
        ("raw_payloads",        ["id"]),
        ("normalized_holdings", ["id"]),
        ("account_snapshots",   ["account_id", "snapshot_date", "batch_id"]),
        ("portfolio_snapshots", ["id"]),
        ("category_snapshots",  ["snapshot_date", "category", "user_id"]),
        ("fx_rates",            ["date"]),
        ("benchmark_prices",    ["date", "ticker"]),
    ]

    try:
        for table, conflict_cols in tables:
            print(f"  {table}...", end=" ", flush=True)
            data = rows(src, table)
            n = upsert(dst, table, data, conflict_cols)
            print(f"{n} rows")

        print("\nMigration complete.")

    except Exception as e:
        print(f"\nERROR: {e}")
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
