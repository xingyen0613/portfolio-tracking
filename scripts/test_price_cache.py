"""
Price cache test script.

Tests three scenarios:
1. Cache miss → fetch from API → save to cache
2. Cache hit → return from DB (no API call)
3. Two-user scenario for CEX crypto prices

Usage:
    uv run python scripts/test_price_cache.py
    uv run python scripts/test_price_cache.py --clear-test-dates
"""

import argparse
import sys
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
# Helpers
# ---------------------------------------------------------------------------

def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _cache_status(symbol: str, price_date: str) -> str:
    result = get_cached_prices([symbol], price_date)
    price = result.get(symbol)
    if price is not None:
        return f"HIT  → {price:.4f}"
    return "MISS"


def clear_test_dates(symbols: list[str], dates: list[str]) -> None:
    print(f"Clearing price_cache for {symbols} on {dates} ...")
    with get_conn() as conn:
        for sym in symbols:
            for d in dates:
                conn.execute(
                    "DELETE FROM price_cache WHERE symbol=%s AND price_date=%s",
                    (sym, d),
                )
    print("Done.")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_crypto_cache(symbol: str = "ETH", dates: list[str] | None = None) -> None:
    _print_section(f"Crypto cache test: {symbol}")

    if dates is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        two_weeks_ago = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        dates = [two_weeks_ago, today]

    for price_date in dates:
        print(f"\n--- {symbol} on {price_date} ---")
        before = _cache_status(symbol, price_date)
        print(f"  Before: {before}")

        if "MISS" in before:
            print(f"  → fetching from API via yfinance ...")
            price = fetch_historical_price(symbol, price_date, currency="USD")
            if price:
                print(f"  → fetched: {price:.4f} USD, saved to cache")
            else:
                print(f"  → could not fetch price (market closed / weekend?)")

        after = _cache_status(symbol, price_date)
        print(f"  After:  {after}")

    # 2nd pass: verify all are now cache hits
    print(f"\n--- 2nd pass (should be all hits) ---")
    for price_date in dates:
        status = _cache_status(symbol, price_date)
        marker = "✓" if "HIT" in status else "✗"
        print(f"  {marker} {symbol} on {price_date}: {status}")


def test_stock_cache(symbol: str, dates: list[str], currency: str = "USD") -> None:
    _print_section(f"Stock cache test: {symbol} (currency={currency})")

    for price_date in dates:
        print(f"\n--- {symbol} on {price_date} ---")
        before = _cache_status(symbol, price_date)
        print(f"  Before: {before}")

        if "MISS" in before:
            print(f"  → fetching from API via yfinance ...")
            price = fetch_historical_price(symbol, price_date, currency=currency)
            if price:
                unit = "TWD" if currency == "TWD" else "USD"
                print(f"  → fetched: {price:.2f} {unit}, saved to cache")
            else:
                print(f"  → could not fetch (market closed / weekend?)")

        after = _cache_status(symbol, price_date)
        print(f"  After:  {after}")

    print(f"\n--- 2nd pass (should be all hits) ---")
    for price_date in dates:
        status = _cache_status(symbol, price_date)
        marker = "✓" if "HIT" in status else "✗"
        print(f"  {marker} {symbol} on {price_date}: {status}")


def test_two_user_sharing(symbol: str = "BTC") -> None:
    """
    Simulate two CEX users fetching the same symbol on the same date.
    User A fetches → price goes to cache. User B should hit cache.
    """
    _print_section(f"Two-user sharing test: {symbol}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Ensure clean state for this symbol today
    with get_conn() as conn:
        conn.execute("DELETE FROM price_cache WHERE symbol=%s AND price_date=%s", (symbol, today))

    print(f"\n[User A batch] fetching {symbol} price for {today} ...")
    from app.valuation.pricer import fetch_prices
    prices_a = fetch_prices([symbol])
    price_a = prices_a.get(symbol)
    if price_a:
        save_prices({symbol: price_a}, today, source="market")
        print(f"  → fetched: {price_a:.4f} USD, saved to cache")
    else:
        print(f"  → fetch failed, cannot continue test")
        return

    print(f"\n[User B batch] checking cache for {symbol} on {today} ...")
    cached_b = get_cached_prices([symbol], today)
    if cached_b.get(symbol) is not None:
        print(f"  ✓ CACHE HIT: {symbol} = {cached_b[symbol]:.4f} USD (no API call)")
    else:
        print(f"  ✗ CACHE MISS: unexpected — user B re-fetched from API")


def show_cache_summary() -> None:
    _print_section("Current price_cache contents (last 30 entries)")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT symbol, price_date::text, price, currency, source, fetched_at::text
            FROM price_cache
            ORDER BY fetched_at DESC
            LIMIT 30
        """).fetchall()

    if not rows:
        print("  (empty)")
        return

    print(f"  {'Symbol':<12} {'Date':<12} {'Price':>12} {'Currency':<6} {'Source':<20} {'Fetched at'}")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*6} {'-'*20} {'-'*20}")
    for row in rows:
        print(f"  {row['symbol']:<12} {row['price_date']:<12} {row['price']:>12.4f} "
              f"{row['currency']:<6} {row['source']:<20} {row['fetched_at'][:19]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Test price_cache behavior")
    parser.add_argument("--clear-test-dates", action="store_true",
                        help="Clear test dates from cache before running")
    args = parser.parse_args()

    # Test dates: one recent trading day, one two weeks ago (should both be on weekdays)
    two_weeks_ago = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    four_weeks_ago = (datetime.now(timezone.utc) - timedelta(days=28)).strftime("%Y-%m-%d")
    test_dates = [four_weeks_ago, two_weeks_ago]
    test_symbols = ["ETH", "TSLA", "0050"]

    if args.clear_test_dates:
        clear_test_dates(test_symbols, test_dates)
        print()

    # 1. Crypto: ETH (USD)
    test_crypto_cache("ETH", dates=test_dates)

    # 2. US stock: TSLA (USD)
    test_stock_cache("TSLA", dates=test_dates, currency="USD")

    # 3. Taiwan stock: 0050 (TWD)
    test_stock_cache("0050", dates=test_dates, currency="TWD")

    # 4. Two-user sharing with BTC
    test_two_user_sharing("BTC")

    # Summary
    show_cache_summary()


if __name__ == "__main__":
    main()
