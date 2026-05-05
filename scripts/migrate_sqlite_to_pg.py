"""
Migrate existing SQLite data to PostgreSQL.

Assigns all rows to SYSTEM_OWNER_ID. Idempotent — safe to run multiple times.

Usage:
    uv run python scripts/migrate_sqlite_to_pg.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.db import get_conn
from config.settings import SQLITE_DIR, SYSTEM_OWNER_ID

SQLITE_PATH = SQLITE_DIR / "portfolio.db"
UID = SYSTEM_OWNER_ID


def migrate():
    if not SQLITE_PATH.exists():
        print(f"SQLite DB not found at {SQLITE_PATH}, skipping.")
        return

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    print(f"Source: {SQLITE_PATH}")

    def rows(table):
        return src.execute(f"SELECT * FROM {table}").fetchall()

    with get_conn() as conn:
        # 1. platforms — ensure all SQLite platforms exist in PG, build name→pg_id map
        print("  platforms...", end=" ")
        sqlite_platform_id_to_name = {r["id"]: r["name"] for r in rows("platforms")}
        for r in rows("platforms"):
            conn.execute(
                "INSERT INTO platforms (name, display_name) VALUES (%s,%s) ON CONFLICT (name) DO NOTHING",
                (r["name"], r["display_name"]),
            )
        # Build mapping: sqlite platform_id → postgres platform_id (keyed by name)
        pg_platform_rows = conn.execute("SELECT id, name FROM platforms").fetchall()
        pg_name_to_id = {r["name"]: r["id"] for r in pg_platform_rows}
        sqlite_pid_to_pg_pid = {
            sqlite_id: pg_name_to_id[name]
            for sqlite_id, name in sqlite_platform_id_to_name.items()
            if name in pg_name_to_id
        }
        conn.execute("SELECT setval('platforms_id_seq', (SELECT MAX(id) FROM platforms))")
        print(f"{len(sqlite_pid_to_pg_pid)} mapped")

        # 2. accounts — use pg platform_id via name mapping
        print("  accounts...", end=" ")
        n = skipped = 0
        sqlite_account_id_to_pg = {}
        for r in rows("accounts"):
            pg_pid = sqlite_pid_to_pg_pid.get(r["platform_id"])
            if pg_pid is None:
                skipped += 1
                continue
            # Check if this account already exists (by account_key + platform + user)
            existing = conn.execute(
                "SELECT id FROM accounts WHERE platform_id=%s AND account_key=%s AND user_id=%s",
                (pg_pid, r["account_key"], UID),
            ).fetchone()
            if existing:
                sqlite_account_id_to_pg[r["id"]] = existing["id"]
                n += 1
                continue
            cur = conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (pg_pid, r["account_key"], r["label"], UID),
            )
            new_id = cur.fetchone()["id"]
            sqlite_account_id_to_pg[r["id"]] = new_id
            n += 1
        if skipped:
            print(f"{n} rows ({skipped} skipped — unknown platform)")
        else:
            print(f"{n} rows")

        conn.execute("SELECT setval('accounts_id_seq', (SELECT MAX(id) FROM accounts))")

        # 3. batches
        print("  batches...", end=" ")
        n = 0
        for r in rows("batches"):
            conn.execute(
                """INSERT INTO batches (id, started_at, finished_at, status, user_id)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["started_at"], r["finished_at"], r["status"], UID),
            )
            n += 1
        print(f"{n} rows")

        # 4. source_runs — map sqlite account_id to pg account_id
        print("  source_runs...", end=" ")
        n = skipped = 0
        sqlite_sr_ids = set()
        for r in rows("source_runs"):
            pg_account_id = sqlite_account_id_to_pg.get(r["account_id"])
            if pg_account_id is None:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO source_runs
                   (id, batch_id, account_id, started_at, finished_at, status, error_message, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["batch_id"], pg_account_id, r["started_at"],
                 r["finished_at"], r["status"], r["error_message"], UID),
            )
            sqlite_sr_ids.add(r["id"])
            n += 1
        if skipped:
            print(f"{n} rows ({skipped} skipped)")
        else:
            print(f"{n} rows")

        # 5. raw_payloads
        print("  raw_payloads...", end=" ")
        n = 0
        for r in rows("raw_payloads"):
            conn.execute(
                """INSERT INTO raw_payloads
                   (id, source_run_id, resource_type, file_path, payload_hash, fetched_at, parser_status, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["source_run_id"], r["resource_type"], r["file_path"],
                 r["payload_hash"], r["fetched_at"], r["parser_status"], UID),
            )
            n += 1
        print(f"{n} rows")

        # 6. normalized_holdings
        print("  normalized_holdings...", end=" ")
        n = 0
        for r in rows("normalized_holdings"):
            conn.execute(
                """INSERT INTO normalized_holdings
                   (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                    asset_type, quantity, price, value, original_currency,
                    price_source, snapshot_date, parser_version, chain, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["source_run_id"], r["raw_payload_id"],
                 r["platform_symbol"], r["platform_asset_name"], r["asset_type"],
                 r["quantity"], r["price"], r["value"], r["original_currency"],
                 r["price_source"], r["snapshot_date"], r["parser_version"],
                 r["chain"], UID),
            )
            n += 1
        print(f"{n} rows")

        # 7. account_snapshots — map sqlite account_id to pg account_id
        print("  account_snapshots...", end=" ")
        n = skipped = 0
        for r in rows("account_snapshots"):
            pg_account_id = sqlite_account_id_to_pg.get(r["account_id"])
            if pg_account_id is None:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO account_snapshots
                   (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, snapshot_date, batch_id) DO NOTHING""",
                (r["id"], r["batch_id"], pg_account_id, r["snapshot_date"],
                 r["total_value"], r["currency"], r["created_at"], UID),
            )
            n += 1
        if skipped:
            print(f"{n} rows ({skipped} skipped)")
        else:
            print(f"{n} rows")

        # 8. portfolio_snapshots
        print("  portfolio_snapshots...", end=" ")
        n = 0
        for r in rows("portfolio_snapshots"):
            conn.execute(
                """INSERT INTO portfolio_snapshots (id, batch_id, snapshot_date, note, created_at)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["batch_id"], r["snapshot_date"], r["note"], r["created_at"]),
            )
            n += 1
        print(f"{n} rows")

        # 9. category_snapshots
        print("  category_snapshots...", end=" ")
        n = 0
        for r in rows("category_snapshots"):
            conn.execute(
                """INSERT INTO category_snapshots
                   (id, snapshot_date, category, total_value, currency, source, batch_id, created_at, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (snapshot_date, category, user_id) DO NOTHING""",
                (r["id"], r["snapshot_date"], r["category"], r["total_value"],
                 r["currency"], r["source"], r["batch_id"], r["created_at"], UID),
            )
            n += 1
        print(f"{n} rows")

        # 10. fx_rates
        print("  fx_rates...", end=" ")
        n = 0
        for r in rows("fx_rates"):
            conn.execute(
                "INSERT INTO fx_rates (date, usdtwd) VALUES (%s,%s) ON CONFLICT (date) DO NOTHING",
                (r["date"], r["usdtwd"]),
            )
            n += 1
        print(f"{n} rows")

        # 11. benchmark_prices
        print("  benchmark_prices...", end=" ")
        n = 0
        for r in rows("benchmark_prices"):
            conn.execute(
                """INSERT INTO benchmark_prices (date, ticker, open, high, low, close)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (date, ticker) DO NOTHING""",
                (r["date"], r["ticker"], r["open"], r["high"], r["low"], r["close"]),
            )
            n += 1
        print(f"{n} rows")

    src.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
