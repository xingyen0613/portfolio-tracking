"""
Insert Yuanta monthly parsed data into PostgreSQL (Supabase).

For each month:
  - Creates batch + source_run records
  - Creates raw_payload (payload_json = parsed.json content)
  - Writes normalized_holdings (per stock per trading day, shares > 0)
  - Writes account_snapshots (daily total_value, TWD)
  - Writes category_snapshots (tw_stock, TWD)

Usage:
  uv run python scripts/yuanta_insert_poc.py --month YYYY-MM
  uv run python scripts/yuanta_insert_poc.py --batch
  uv run python scripts/yuanta_insert_poc.py --month YYYY-MM --dry-run
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVED_DIR  = Path(os.environ.get("DERIVED_DATA_DIR", str(PROJECT_ROOT / "data" / "derived"))) / "yuanta_poc"
RAW_DIR      = Path(os.environ.get("RAW_DATA_DIR",     str(PROJECT_ROOT / "data" / "raw")))     / "yuanta_poc"

CURRENCY       = "TWD"
PARSER_VERSION = "1.0.0"
YUANTA_ACCOUNT_ID = 5  # PostgreSQL integer ID

sys.path.insert(0, str(PROJECT_ROOT))
import config.settings  # triggers load_dotenv
from config.db import get_conn
from config.settings import SYSTEM_OWNER_ID, PLATFORM_CATEGORY


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_net_asset(month: str) -> list[dict]:
    path = DERIVED_DIR / month / "daily_net_asset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["daily"]


def load_daily_holdings(month: str) -> list[dict]:
    path = DERIVED_DIR / month / "daily_holdings.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["daily"]


def load_prices(month: str) -> dict[str, dict[str, float]]:
    """Return {date: {symbol: price_float}} for the month."""
    path = DERIVED_DIR / "prices" / f"{month}.json"
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)["prices"]
        return {
            date_str: {sym: float(p) for sym, p in day_prices.items()}
            for date_str, day_prices in raw.items()
        }
    except FileNotFoundError:
        return {}


def load_parsed_json(month: str) -> dict | None:
    path = RAW_DIR / month / "parsed.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect_months() -> list[str]:
    return sorted(
        p.parent.name
        for p in DERIVED_DIR.glob("*/daily_net_asset.json")
    )


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

def _existing_snapshot_dates(month: str) -> set[str]:
    """Return the set of yyyy-mm-dd strings that already have an account_snapshot."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT CAST(snapshot_date AS TEXT) AS d FROM account_snapshots "
            "WHERE account_id = %s AND CAST(snapshot_date AS TEXT) LIKE %s",
            (YUANTA_ACCOUNT_ID, f"{month}-%"),
        ).fetchall()
        return {r["d"] for r in rows}


def insert_months(months: list[str], dry_run: bool = False) -> None:
    now = _now()
    batch_id = str(uuid.uuid4())

    if not dry_run:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s,%s,%s,%s)",
                (batch_id, now, "running", SYSTEM_OWNER_ID),
            )

    total_holdings = 0
    total_snapshots = 0

    for month in months:
        print(f"\n# --- {month} ---", file=sys.stderr)

        # Load data
        try:
            net_asset_entries = load_net_asset(month)
        except FileNotFoundError:
            print(f"  WARN: no daily_net_asset.json for {month}, skipping", file=sys.stderr)
            continue

        try:
            daily_holdings = load_daily_holdings(month)
        except FileNotFoundError:
            daily_holdings = []

        prices = load_prices(month)
        parsed_json = load_parsed_json(month)

        if dry_run:
            _dry_run_month(month, net_asset_entries, daily_holdings, prices)
            continue

        source_run_id = str(uuid.uuid4())

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO source_runs (id, batch_id, account_id, started_at, status, user_id) VALUES (%s,%s,%s,%s,%s,%s)",
                (source_run_id, batch_id, YUANTA_ACCOUNT_ID, now, "running", SYSTEM_OWNER_ID),
            )

        # Create raw_payload from parsed.json (one per month = one per statement)
        raw_payload_id = str(uuid.uuid4())
        if parsed_json is not None:
            file_path = str(RAW_DIR / month / "parsed.json")
            content = json.dumps(parsed_json, ensure_ascii=False)
            payload_hash = hashlib.sha256(content.encode()).hexdigest()
        else:
            file_path = f"yuanta_poc/{month}/parsed.json"
            payload_hash = ""

        with get_conn() as conn:
            conn.execute(
                """INSERT INTO raw_payloads
                   (id, source_run_id, resource_type, file_path, payload_hash, fetched_at, parser_status, payload_json, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (raw_payload_id, source_run_id, "yuanta_parsed_statement",
                 file_path, payload_hash, now, "parsed",
                 json.dumps(parsed_json) if parsed_json else None,
                 SYSTEM_OWNER_ID),
            )

        # normalized_holdings: per stock per trading day (shares > 0, price available)
        holdings_written = 0
        with get_conn() as conn:
            for day in daily_holdings:
                date_str = day["date"]
                day_prices = prices.get(date_str, {})

                for h in day.get("holdings", []):
                    symbol = h.get("symbol")
                    shares = h.get("shares", 0)
                    if not symbol or shares <= 0:
                        continue

                    price = day_prices.get(symbol)
                    value = round(shares * price, 2) if price is not None else None

                    conn.execute(
                        """INSERT INTO normalized_holdings
                           (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                            asset_type, quantity, price, value, original_currency,
                            price_source, snapshot_date, parser_version, chain, user_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            str(uuid.uuid4()), source_run_id, raw_payload_id,
                            symbol, h.get("name"),
                            "tw_stock",
                            float(shares),
                            price,
                            value,
                            CURRENCY,
                            "historical" if price is not None else None,
                            date_str,
                            PARSER_VERSION,
                            None,
                            SYSTEM_OWNER_ID,
                        ),
                    )
                    holdings_written += 1

        total_holdings += holdings_written
        print(f"  normalized_holdings: {holdings_written} rows", file=sys.stderr)

        # account_snapshots: one per day — skip days that already exist
        existing_dates = _existing_snapshot_dates(month)
        snapshots_written = 0
        snapshots_skipped = 0
        with get_conn() as conn:
            for entry in net_asset_entries:
                date_str = entry["date"]
                if date_str in existing_dates:
                    snapshots_skipped += 1
                    continue
                raw = entry.get("net_asset")
                total_value = float(raw) if raw is not None else None

                conn.execute(
                    """INSERT INTO account_snapshots
                       (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (account_id, snapshot_date, batch_id) DO NOTHING""",
                    (str(uuid.uuid4()), batch_id, YUANTA_ACCOUNT_ID,
                     date_str, total_value, CURRENCY, now, SYSTEM_OWNER_ID),
                )
                snapshots_written += 1
        total_snapshots += snapshots_written
        print(
            f"  account_snapshots: {snapshots_written} rows written, {snapshots_skipped} skipped (already exist)",
            file=sys.stderr,
        )

        with get_conn() as conn:
            conn.execute(
                "UPDATE source_runs SET status='success', finished_at=%s WHERE id=%s",
                (now, source_run_id),
            )

    if dry_run:
        return

    # Rebuild tw_stock category_snapshots from account_snapshots
    _rebuild_category_snapshots(batch_id, now)

    with get_conn() as conn:
        conn.execute(
            "UPDATE batches SET status='success', finished_at=%s WHERE id=%s",
            (now, batch_id),
        )

    print(f"\n# done — {total_holdings} normalized_holdings, {total_snapshots} account_snapshots", file=sys.stderr)
    print(f"  batch_id: {batch_id}", file=sys.stderr)


def _rebuild_category_snapshots(batch_id: str, now: str) -> None:
    """Upsert tw_stock category_snapshots from all account_snapshots."""
    tw_platforms = [name for name, cat in PLATFORM_CATEGORY.items() if cat == "tw_stock"]

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT acs.snapshot_date, SUM(acs.total_value) AS total_value
            FROM account_snapshots acs
            JOIN accounts a ON acs.account_id = a.id
            JOIN platforms p ON a.platform_id = p.id
            WHERE p.name = ANY(%s)
              AND acs.total_value IS NOT NULL
              AND acs.user_id = %s
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
        """, (tw_platforms, SYSTEM_OWNER_ID)).fetchall()

        written = 0
        for row in rows:
            conn.execute(
                """INSERT INTO category_snapshots
                   (id, snapshot_date, category, total_value, currency, source, batch_id, created_at, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (snapshot_date, category, user_id) DO UPDATE SET
                     total_value = EXCLUDED.total_value,
                     source = EXCLUDED.source,
                     batch_id = EXCLUDED.batch_id,
                     created_at = EXCLUDED.created_at
                   WHERE category_snapshots.source <> 'manual'""",
                (str(uuid.uuid4()), row["snapshot_date"], "tw_stock",
                 row["total_value"], CURRENCY, "auto", batch_id, now, SYSTEM_OWNER_ID),
            )
            written += 1

    print(f"  category_snapshots tw_stock: {written} rows upserted", file=sys.stderr)


def _dry_run_month(month: str, net_asset_entries: list, daily_holdings: list, prices: dict) -> None:
    for entry in net_asset_entries[:3]:
        print(f"  [dry] account_snapshots date={entry['date']} value={entry.get('net_asset')}")
    print(f"  [dry] ... {len(net_asset_entries)} total days")

    count = sum(
        1
        for day in daily_holdings
        for h in day.get("holdings", [])
        if h.get("symbol") and h.get("shares", 0) > 0 and prices.get(day["date"], {}).get(h["symbol"])
    )
    print(f"  [dry] normalized_holdings: ~{count} rows with price")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Insert Yuanta data into PostgreSQL")
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
