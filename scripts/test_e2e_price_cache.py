"""
E2E test: price cache behavior with xingyen02 historical positions.

Scenario:
  - Pre-populate price_cache for DATE_A (simulates another user already fetched these prices)
  - Insert holdings for xingyen02 with price=NULL for DATE_A and DATE_B
  - Run price fill:
      DATE_A → cache HIT → no API call
      DATE_B → cache MISS → fetch from API → saved to cache
  - Re-run price fill to verify DATE_B is now also a cache hit

Assets tested:  ETH (crypto), TSLA (US stock), 0050 (TW stock)

Usage:
    uv run python scripts/test_e2e_price_cache.py
    uv run python scripts/test_e2e_price_cache.py --cleanup  # remove test records after run
"""

import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from config.db import get_conn
from app.valuation.price_cache import get_cached_prices, save_prices, fetch_historical_price

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

XINGYEN02_ID = "c11baf9b-a920-4b32-ba14-8d86eeb37818"

# Pick two past weekdays (avoid weekends for stock markets)
# DATE_A: 4 weeks ago (we'll pre-seed cache for this date)
# DATE_B: 2 weeks ago (cache starts empty, must fetch from API)
_today = datetime.now(timezone.utc)
DATE_A = (_today - timedelta(days=28)).strftime("%Y-%m-%d")   # pre-cached
DATE_B = (_today - timedelta(days=14)).strftime("%Y-%m-%d")   # not cached initially

TEST_HOLDINGS = [
    # symbol, quantity, asset_type, original_currency, price_currency
    ("ETH",  1.0, "crypto",   "USD", "USD"),
    ("TSLA", 1.0, "stock",    "USD", "USD"),
    ("0050", 1.0, "etf",      "TWD", "TWD"),
]

TEST_TAG = "e2e_price_cache_test"   # used to find / cleanup records

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def _print_section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


# ---------------------------------------------------------------------------
# DB helpers: create / cleanup test records
# ---------------------------------------------------------------------------

def _ensure_test_account(platform_id: int, account_key: str) -> int:
    """Return account.id for xingyen02's test account, creating it if needed."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO accounts (platform_id, account_key, label, user_id)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
            (platform_id, account_key, "e2e test account", XINGYEN02_ID),
        )
        row = conn.execute(
            "SELECT id FROM accounts WHERE platform_id=%s AND account_key=%s AND user_id=%s",
            (platform_id, account_key, XINGYEN02_ID),
        ).fetchone()
    return row["id"]


def insert_test_holdings(dates: list[str]) -> list[str]:
    """
    Insert minimal normalized_holdings records for xingyen02 with price=NULL.
    Returns list of batch_ids created.
    """
    _log(f"Inserting test holdings for xingyen02 on dates: {dates}")

    # Use a fake "binance" platform for crypto, "ibkr" for TSLA, "sinopac" for 0050
    PLATFORM_MAP = {
        "ETH":  (1,  "test_crypto"),   # binance platform_id=1
        "TSLA": (10, "test_us"),        # ibkr platform_id=10
        "0050": (11, "test_tw"),        # sinopac platform_id=11
    }

    batch_ids = []

    for snapshot_date in dates:
        batch_id = str(uuid.uuid4())
        batch_ids.append(batch_id)

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s,%s,%s,%s)",
                (batch_id, _now(), "success", XINGYEN02_ID),
            )

        for symbol, qty, asset_type, orig_currency, _ in TEST_HOLDINGS:
            platform_id, account_key = PLATFORM_MAP[symbol]
            account_id = _ensure_test_account(platform_id, account_key)
            source_run_id = str(uuid.uuid4())
            raw_payload_id = str(uuid.uuid4())

            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO source_runs
                       (id, batch_id, account_id, started_at, finished_at, status, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (source_run_id, batch_id, account_id, _now(), _now(), "success", XINGYEN02_ID),
                )
                conn.execute(
                    """INSERT INTO raw_payloads
                       (id, source_run_id, resource_type, file_path, payload_hash,
                        fetched_at, parser_status, payload_json, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (raw_payload_id, source_run_id, "spot", f"test/{symbol}_{snapshot_date}.json",
                     "test", _now(), "parsed", "{}", XINGYEN02_ID),
                )
                # Insert holding with price=NULL
                conn.execute(
                    """INSERT INTO normalized_holdings
                       (id, source_run_id, raw_payload_id, platform_symbol,
                        asset_type, quantity, price, value, original_currency,
                        price_source, snapshot_date, parser_version, user_id, resource_type)
                       VALUES (%s,%s,%s,%s,%s,%s,NULL,NULL,%s,NULL,%s,%s,%s,%s)""",
                    (
                        str(uuid.uuid4()), source_run_id, raw_payload_id,
                        symbol, asset_type, qty,
                        orig_currency, snapshot_date,
                        TEST_TAG,       # parser_version used as test tag for cleanup
                        XINGYEN02_ID, "spot",
                    ),
                )
            _log(f"  inserted {symbol} × {qty} on {snapshot_date} (price=NULL)")

    return batch_ids


def cleanup_test_records() -> None:
    _log("Cleaning up test records from DB ...")
    with get_conn() as conn:
        # Delete in FK-safe order: holdings → raw_payloads → source_runs → batches → accounts
        conn.execute(
            "DELETE FROM normalized_holdings WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM raw_payloads WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM source_runs WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM account_snapshots WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM category_snapshots WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM batches WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
        conn.execute(
            "DELETE FROM accounts WHERE user_id=%s",
            (XINGYEN02_ID,),
        )
    _log("Cleanup done.")


# ---------------------------------------------------------------------------
# Price fill: simulate the pipeline pricing logic for given holdings
# ---------------------------------------------------------------------------

def fill_prices_for_date(snapshot_date: str, log_prefix: str = "") -> dict[str, float | None]:
    """
    For holdings belonging to xingyen02 on snapshot_date that have price=NULL,
    check price_cache first, then fetch from API for missing ones.
    Returns {symbol: price} for all processed symbols.
    """
    prefix = f"[{log_prefix}] " if log_prefix else ""

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT platform_symbol, original_currency
               FROM normalized_holdings
               WHERE user_id=%s AND snapshot_date=%s AND price IS NULL
                 AND parser_version=%s""",
            (XINGYEN02_ID, snapshot_date, TEST_TAG),
        ).fetchall()

    if not rows:
        _log(f"{prefix}No unpriced holdings on {snapshot_date}")
        return {}

    symbols = [r["platform_symbol"] for r in rows]
    currency_map = {r["platform_symbol"]: r["original_currency"] for r in rows}
    _log(f"{prefix}Unpriced holdings on {snapshot_date}: {symbols}")

    # Step 1: cache lookup
    cached = get_cached_prices(symbols, snapshot_date)
    missing = [s for s in symbols if cached.get(s) is None]

    _log(f"{prefix}Cache check → HIT: {[s for s in symbols if cached.get(s) is not None]}")
    _log(f"{prefix}Cache check → MISS: {missing}")

    # Step 2: fetch missing from API (yfinance)
    if missing:
        _log(f"{prefix}Fetching {len(missing)} prices from external API ...")
        for sym in missing:
            currency = currency_map.get(sym, "USD")
            price = fetch_historical_price(sym, snapshot_date, currency=currency)
            if price is not None:
                cached[sym] = price
                _log(f"{prefix}  API → {sym} on {snapshot_date} = {price:.4f} {currency} (saved to cache)")
            else:
                _log(f"{prefix}  API → {sym}: unavailable")
    else:
        _log(f"{prefix}All prices served from cache — no API calls made")

    # Step 3: update normalized_holdings with resolved prices
    with get_conn() as conn:
        for sym, price in cached.items():
            if price is not None:
                conn.execute(
                    """UPDATE normalized_holdings
                       SET price=%s, value=%s, price_source=%s
                       WHERE user_id=%s AND snapshot_date=%s
                         AND platform_symbol=%s AND parser_version=%s""",
                    (price, round(price, 8),  # qty=1 so value=price
                     "price_cache", XINGYEN02_ID, snapshot_date, sym, TEST_TAG),
                )

    return {s: cached.get(s) for s in symbols}


# ---------------------------------------------------------------------------
# Show holding prices from DB
# ---------------------------------------------------------------------------

def show_holdings(dates: list[str]) -> None:
    _print_section("xingyen02 holdings (price_source reflects cache/API origin)")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT platform_symbol, snapshot_date, quantity, price, price_source
               FROM normalized_holdings
               WHERE user_id=%s AND parser_version=%s
               ORDER BY snapshot_date, platform_symbol""",
            (XINGYEN02_ID, TEST_TAG),
        ).fetchall()
    if not rows:
        print("  (none)")
        return
    print(f"  {'Symbol':<8} {'Date':<12} {'Qty':>5} {'Price':>12} {'Source'}")
    print(f"  {'-'*8} {'-'*12} {'-'*5} {'-'*12} {'-'*15}")
    for r in rows:
        price_str = f"{r['price']:.4f}" if r["price"] is not None else "NULL"
        print(f"  {r['platform_symbol']:<8} {str(r['snapshot_date']):<12} {r['quantity']:>5.1f} "
              f"{price_str:>12} {r['price_source'] or '-'}")


def show_price_cache(symbols: list[str], dates: list[str]) -> None:
    _print_section("price_cache entries for test assets")
    placeholders = ",".join(["%s"] * len(symbols))
    date_ph = ",".join(["%s"] * len(dates))
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT symbol, price_date::text, price, currency, source, fetched_at::text
                FROM price_cache
                WHERE symbol IN ({placeholders}) AND price_date IN ({date_ph})
                ORDER BY price_date, symbol""",
            (*symbols, *dates),
        ).fetchall()
    if not rows:
        print("  (empty)")
        return
    print(f"  {'Symbol':<8} {'Date':<12} {'Price':>12} {'Cur':<5} {'Source':<25} {'Fetched'}")
    print(f"  {'-'*8} {'-'*12} {'-'*12} {'-'*5} {'-'*25} {'-'*20}")
    for r in rows:
        print(f"  {r['symbol']:<8} {r['price_date']:<12} {r['price']:>12.4f} "
              f"{r['currency']:<5} {r['source']:<25} {r['fetched_at'][:19]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="Remove test records and exit")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_test_records()
        return

    symbols = [s for s, *_ in TEST_HOLDINGS]

    print(f"""
E2E Price Cache Test
====================
User:   xingyen02 ({XINGYEN02_ID[:8]}...)
DATE_A: {DATE_A}  ← will be pre-seeded in price_cache (simulates another user fetched these)
DATE_B: {DATE_B}  ← starts empty in price_cache (must fetch from API)
Assets: {', '.join(symbols)}
""")

    # 0. Clean price_cache for our test dates to start fresh
    _log("Clearing price_cache for test dates (DATE_A, DATE_B) ...")
    with get_conn() as conn:
        for sym in symbols:
            conn.execute(
                "DELETE FROM price_cache WHERE symbol=%s AND price_date IN (%s,%s)",
                (sym, DATE_A, DATE_B),
            )

    # 1. Pre-populate price_cache for DATE_A only (simulates another user's batch already ran)
    _print_section(f"Step 1: Pre-seed price_cache for DATE_A ({DATE_A})")
    _log("Fetching prices from API to populate DATE_A cache (simulates 'User A ran batch first') ...")
    for sym, _, _, _, price_currency in TEST_HOLDINGS:
        price = fetch_historical_price(sym, DATE_A, currency=price_currency)
        if price:
            _log(f"  pre-seeded: {sym} on {DATE_A} = {price:.4f} {price_currency}")
        else:
            _log(f"  WARNING: could not pre-seed {sym} on {DATE_A} (weekend/holiday?)")

    # 2. Insert test holdings with price=NULL for both dates
    _print_section("Step 2: Insert historical holdings for xingyen02 (price=NULL)")
    _log("Removing any previous test holdings ...")
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM normalized_holdings WHERE user_id=%s AND parser_version=%s",
            (XINGYEN02_ID, TEST_TAG),
        )
    insert_test_holdings([DATE_A, DATE_B])
    show_holdings([DATE_A, DATE_B])

    # 3. Run price fill for DATE_A — should be 100% cache hits
    _print_section(f"Step 3: Fill prices for DATE_A ({DATE_A}) — expect ALL cache hits")
    result_a = fill_prices_for_date(DATE_A, log_prefix="DATE_A")

    # 4. Run price fill for DATE_B — should be 100% cache misses → API calls → saved to cache
    _print_section(f"Step 4: Fill prices for DATE_B ({DATE_B}) — expect ALL cache misses")
    result_b = fill_prices_for_date(DATE_B, log_prefix="DATE_B")

    # 5. Re-run price fill for DATE_B — holdings are now priced, but verify cache is populated
    _print_section(f"Step 5: Re-check cache for DATE_B ({DATE_B}) — should now be hits")
    cached_b = get_cached_prices(symbols, DATE_B)
    all_hits = all(cached_b.get(s) is not None for s in symbols)
    for s in symbols:
        val = cached_b.get(s)
        marker = "✓ HIT" if val is not None else "✗ MISS"
        print(f"  {marker}: {s} on {DATE_B} = {val}")
    if all_hits:
        _log("All DATE_B prices are now in cache — subsequent batches will skip API calls ✓")
    else:
        _log("WARNING: some prices still missing from cache")

    # 6. Show final state
    show_holdings([DATE_A, DATE_B])
    show_price_cache(symbols, [DATE_A, DATE_B])

    print(f"\n{'=' * 65}")
    print("  Summary")
    print(f"{'=' * 65}")
    print(f"  DATE_A ({DATE_A}) — pre-cached:")
    for s in symbols:
        p = result_a.get(s)
        print(f"    {s}: {p:.4f}" if p else f"    {s}: unavailable")
    print(f"\n  DATE_B ({DATE_B}) — fetched on first fill, cached for future:")
    for s in symbols:
        p = result_b.get(s)
        print(f"    {s}: {p:.4f}" if p else f"    {s}: unavailable")

    print(f"\n  Test records left in DB. Run with --cleanup to remove them.")


if __name__ == "__main__":
    main()
