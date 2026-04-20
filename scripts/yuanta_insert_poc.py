"""
Insert Yuanta PoC daily_net_asset.json into main system SQLite.

Reads:  data/derived/yuanta_poc/<YYYY-MM>/daily_net_asset.json
Writes: account_snapshots (account_id=4, currency=TWD)
        category_snapshots (tw_stock, currency=TWD) — replaces all existing rows

Usage:
  --batch       Insert all months found under data/derived/yuanta_poc/
  --month YYYY-MM  Insert one month only
  --dry-run     Print rows without writing to DB
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVED_DIR = PROJECT_ROOT / "data" / "derived" / "yuanta_poc"
DB_PATH = PROJECT_ROOT / "data" / "sqlite" / "portfolio.db"

YUANTA_ACCOUNT_ID = 4
CURRENCY = "TWD"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_net_asset(month: str) -> list[dict]:
    path = DERIVED_DIR / month / "daily_net_asset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["daily"]


def collect_months() -> list[str]:
    return sorted(
        p.parent.name
        for p in DERIVED_DIR.glob("*/daily_net_asset.json")
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_tw_stock_account_ids(conn) -> list[int]:
    """Return all account_ids belonging to tw_stock platforms."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from config.settings import PLATFORM_CATEGORY
    tw_platforms = [name for name, cat in PLATFORM_CATEGORY.items() if cat == "tw_stock"]
    rows = conn.execute(
        f"SELECT a.id FROM accounts a JOIN platforms p ON a.platform_id = p.id "
        f"WHERE p.name IN ({','.join('?' for _ in tw_platforms)})",
        tw_platforms,
    ).fetchall()
    return [r[0] for r in rows]


def compute_category_snapshots(conn, tw_account_ids: list[int]) -> dict[str, float]:
    """
    For each date that has tw_stock account data, return {date: total_value}.
    Uses the latest non-null value per account per date (dedup by created_at).
    Only includes dates where at least one account has a non-null value.
    """
    if not tw_account_ids:
        return {}

    placeholders = ",".join("?" for _ in tw_account_ids)
    rows = conn.execute(f"""
        SELECT acs.snapshot_date, SUM(acs.total_value)
        FROM account_snapshots acs
        WHERE acs.account_id IN ({placeholders})
          AND acs.total_value IS NOT NULL
          AND acs.id = (
              SELECT id FROM account_snapshots
              WHERE account_id = acs.account_id
                AND snapshot_date = acs.snapshot_date
                AND total_value IS NOT NULL
              ORDER BY created_at DESC LIMIT 1
          )
        GROUP BY acs.snapshot_date
        HAVING SUM(acs.total_value) IS NOT NULL
        ORDER BY acs.snapshot_date
    """, tw_account_ids).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

def insert_months(months: list[str], dry_run: bool = False) -> None:
    import sqlite3
    conn = sqlite3.connect(DB_PATH)

    # Step 1: Create batch
    batch_id = str(uuid.uuid4())
    now = _now()

    if not dry_run:
        conn.execute(
            "INSERT INTO batches (id, started_at, finished_at, status) VALUES (?,?,?,?)",
            (batch_id, now, now, "completed"),
        )

    # Step 2: Insert account_snapshots
    total_inserted = 0
    total_null = 0

    for month in months:
        try:
            entries = load_net_asset(month)
        except FileNotFoundError:
            print(f"  WARN: no daily_net_asset.json for {month}, skipping", file=sys.stderr)
            continue

        for entry in entries:
            date = entry["date"]
            raw = entry.get("net_asset")
            total_value = float(raw) if raw is not None else None

            if dry_run:
                print(f"  [dry] account_snapshots account_id={YUANTA_ACCOUNT_ID} "
                      f"date={date} value={total_value} currency={CURRENCY}")
            else:
                conn.execute(
                    """INSERT INTO account_snapshots
                       (id, batch_id, account_id, snapshot_date, total_value, currency, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), batch_id, YUANTA_ACCOUNT_ID,
                     date, total_value, CURRENCY, now),
                )

            if total_value is None:
                total_null += 1
            else:
                total_inserted += 1

        print(f"  [{month}] {len(entries)} days processed", file=sys.stderr)

    print(f"  account_snapshots: {total_inserted} non-null + {total_null} null rows",
          file=sys.stderr)

    # Step 3: Rebuild tw_stock category_snapshots
    if not dry_run:
        conn.execute("DELETE FROM category_snapshots WHERE category = 'tw_stock'")
        print("  deleted all tw_stock category_snapshots", file=sys.stderr)

    tw_account_ids = get_tw_stock_account_ids(conn) if not dry_run else [YUANTA_ACCOUNT_ID]

    if not dry_run:
        category_totals = compute_category_snapshots(conn, tw_account_ids)
    else:
        # For dry-run: compute from local JSON data
        category_totals: dict[str, float] = {}
        for month in months:
            try:
                entries = load_net_asset(month)
            except FileNotFoundError:
                continue
            for entry in entries:
                raw = entry.get("net_asset")
                if raw is not None:
                    category_totals[entry["date"]] = float(raw)

    cat_inserted = 0
    for date, total in sorted(category_totals.items()):
        if dry_run:
            print(f"  [dry] category_snapshots date={date} tw_stock={total} currency={CURRENCY}")
        else:
            conn.execute(
                """INSERT OR REPLACE INTO category_snapshots
                   (id, snapshot_date, category, total_value, currency, source, batch_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), date, "tw_stock", total, CURRENCY, "auto", batch_id, now),
            )
        cat_inserted += 1

    print(f"  category_snapshots tw_stock: {cat_inserted} rows", file=sys.stderr)

    if not dry_run:
        conn.commit()
        print(f"  batch_id: {batch_id}", file=sys.stderr)

    conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert Yuanta PoC net_asset data into main SQLite DB"
    )
    parser.add_argument("--batch", action="store_true",
                        help="Insert all months under data/derived/yuanta_poc/")
    parser.add_argument("--month", help="Insert one month, e.g. 2026-03")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rows without writing to DB")
    args = parser.parse_args()

    if args.month:
        months = [args.month]
    elif args.batch:
        months = collect_months()
        if not months:
            print("No daily_net_asset.json files found.", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1

    print(f"# {'DRY RUN — ' if args.dry_run else ''}inserting {len(months)} months: "
          f"{months[0]} ~ {months[-1]}", file=sys.stderr)

    insert_months(months, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
