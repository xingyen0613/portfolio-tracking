"""
Fetch daily closing prices for all symbols in Yuanta parsed.json via Yahoo Finance.

Reads: data/raw/yuanta_poc/<YYYY-MM>/parsed.json
Writes: data/derived/yuanta_poc/prices/<YYYY-MM>.json

Exchange routing: try {symbol}.TW (TWSE), fallback to {symbol}.TWO (TPEX).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"
PRICES_DIR = PROJECT_ROOT / "data" / "derived" / "yuanta_poc" / "prices"
NAME_CACHE_PATH = PROJECT_ROOT / "data" / "derived" / "yuanta_poc" / "name_to_symbol_cache.json"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_LIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SLEEP_BETWEEN = 0.5  # seconds between requests


# ---------------------------------------------------------------------------
# Name → Symbol resolver (on-demand + local cache)
# ---------------------------------------------------------------------------

def _fetch_exchange_name_map() -> dict[str, str]:
    """Download TWSE + TPEX listings and return {stock_name: symbol}."""
    result: dict[str, str] = {}
    sources = [
        (TWSE_LIST_URL, "Code", "Name"),
        (TPEX_LIST_URL, "SecuritiesCompanyCode", "CompanyName"),
    ]
    for url, code_key, name_key in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            for item in data:
                name = item.get(name_key, "").strip()
                code = item.get(code_key, "").strip()
                if name and code:
                    result[name] = code
        except Exception as e:
            print(f"  WARN: failed to fetch {url}: {e}", file=sys.stderr)
    return result


def resolve_name_to_symbol(name: str) -> str | None:
    """
    Resolve a stock name (from PDF) to its exchange symbol.
    Checks local cache first; on miss fetches TWSE + TPEX live data and updates cache.
    """
    cache: dict[str, str] = {}
    if NAME_CACHE_PATH.exists():
        with open(NAME_CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    if name in cache:
        return cache[name]

    print(f"  [name-lookup] resolving '{name}' from TWSE/TPEX...", file=sys.stderr)
    name_map = _fetch_exchange_name_map()
    symbol = name_map.get(name)

    if symbol:
        cache[name] = symbol
        NAME_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NAME_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"  [name-lookup] '{name}' → {symbol} (cached)", file=sys.stderr)
    else:
        print(f"  [name-lookup] '{name}' not found in TWSE/TPEX listings", file=sys.stderr)

    return symbol


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_parsed(month: str) -> dict:
    path = RAW_DIR / month / "parsed.json"
    if not path.exists():
        raise FileNotFoundError(f"parsed.json not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Symbol collection
# ---------------------------------------------------------------------------

def collect_symbols(months: list[str]) -> list[str]:
    """
    Collect all unique symbols from parsed.json files across given months.
    Null-symbol entries (pledged collateral) are resolved via name lookup.
    Returns sorted list of stock codes.
    """
    syms: set[str] = set()
    for month in months:
        try:
            parsed = load_parsed(month)
        except FileNotFoundError:
            continue
        for h in parsed.get("holdings_owned", []):
            if h.get("symbol"):
                syms.add(h["symbol"])
        for h in parsed.get("holdings_pledged", []):
            name = h.get("name", "")
            if name:
                resolved = resolve_name_to_symbol(name)
                if resolved:
                    syms.add(resolved)
        for t in parsed.get("transactions", []):
            if t.get("symbol"):
                syms.add(t["symbol"])
    return sorted(syms)


# ---------------------------------------------------------------------------
# Yahoo Finance fetcher
# ---------------------------------------------------------------------------

def _fetch_yahoo_ticker(ticker: str, period1: int, period2: int) -> dict[str, str] | None:
    """
    Fetch daily close prices for a Yahoo Finance ticker in [period1, period2).
    Returns {iso_date: close_str} or None if the ticker doesn't exist (404).
    Raises on other HTTP errors.
    """
    url = YAHOO_URL.format(ticker=ticker)
    params = f"?period1={period1}&period2={period2}&interval=1d"
    req = urllib.request.Request(url + params, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

    result = data.get("chart", {}).get("result")
    if not result:
        return None

    r = result[0]
    timestamps = r.get("timestamp", [])
    closes = r.get("indicators", {}).get("quote", [{}])[0].get("close", [])

    prices: dict[str, str] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        # Convert UTC timestamp to Taiwan date (UTC+8; close at 13:30 CST = 05:30 UTC, same calendar day)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        iso_date = dt.strftime("%Y-%m-%d")
        prices[iso_date] = f"{close:.2f}"
    return prices


def fetch_yahoo(symbol: str, year: int, month: int) -> tuple[dict[str, str], str | None]:
    """
    Fetch closing prices for symbol during year/month.
    Tries {symbol}.TW first, then {symbol}.TWO.
    Returns (prices_dict, exchange_suffix) where exchange_suffix is 'TW', 'TWO', or None if not found.
    """
    # period: full month
    period1 = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
    last_day = monthrange(year, month)[1]
    # period2 = first second of next month (exclusive)
    if month == 12:
        period2 = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    else:
        period2 = int(datetime(year, month + 1, 1, tzinfo=timezone.utc).timestamp())

    for suffix in ("TW", "TWO"):
        ticker = f"{symbol}.{suffix}"
        prices = _fetch_yahoo_ticker(ticker, period1, period2)
        time.sleep(SLEEP_BETWEEN)
        if prices is not None:
            return prices, suffix

    return {}, None


# ---------------------------------------------------------------------------
# Fetch one month
# ---------------------------------------------------------------------------

def fetch_month(
    month: str,
    symbols: list[str],
    exchange_cache: dict[str, str] | None = None,
) -> dict:
    """
    Fetch prices for all symbols for a given month.
    exchange_cache: optional {symbol: 'TW'|'TWO'} to skip auto-detection for known symbols.
    Returns the month price document (meta + prices).
    """
    year, mon = int(month[:4]), int(month[5:7])
    if exchange_cache is None:
        exchange_cache = {}

    prices_by_date: dict[str, dict[str, str]] = {}
    fetched: list[str] = []
    missing: list[str] = []
    symbol_exchange: dict[str, str] = {}

    for sym in symbols:
        known_suffix = exchange_cache.get(sym)
        if known_suffix:
            # Use cached exchange
            period1 = int(datetime(year, mon, 1, tzinfo=timezone.utc).timestamp())
            if mon == 12:
                period2 = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
            else:
                period2 = int(datetime(year, mon + 1, 1, tzinfo=timezone.utc).timestamp())
            ticker = f"{sym}.{known_suffix}"
            sym_prices = _fetch_yahoo_ticker(ticker, period1, period2)
            time.sleep(SLEEP_BETWEEN)
            suffix = known_suffix if sym_prices else None
        else:
            sym_prices, suffix = fetch_yahoo(sym, year, mon)

        if suffix:
            symbol_exchange[sym] = suffix
            exchange_cache[sym] = suffix
            fetched.append(sym)
            for date, close in sym_prices.items():
                if date not in prices_by_date:
                    prices_by_date[date] = {}
                prices_by_date[date][sym] = close
            print(f"  [{month}] {sym}.{suffix}: {len(sym_prices)} trading days", file=sys.stderr)
        else:
            missing.append(sym)
            print(f"  [{month}] {sym}: NOT FOUND (tried .TW and .TWO)", file=sys.stderr)

    return {
        "meta": {
            "month": month,
            "fetched_symbols": fetched,
            "missing_symbols": missing,
            "symbol_exchange": symbol_exchange,
        },
        "prices": dict(sorted(prices_by_date.items())),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch daily closing prices from Yahoo Finance for Yuanta PoC symbols"
    )
    parser.add_argument("--month", help="Fetch prices for one month, e.g. 2026-02")
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Limit to specific symbols (default: all from parsed.json)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Fetch all months found under data/raw/yuanta_poc/*/parsed.json",
    )
    args = parser.parse_args()

    if args.month:
        months = [args.month]
        symbols = args.symbols if args.symbols else collect_symbols(months)
        doc = fetch_month(args.month, symbols)
        out_path = PRICES_DIR / f"{args.month}.json"
        write_json(doc, out_path)
        print(f"[{args.month}] wrote {out_path}", file=sys.stderr)
        missing = doc["meta"]["missing_symbols"]
        if missing:
            print(f"[{args.month}] missing: {missing}", file=sys.stderr)
        return 0

    if args.batch:
        months = sorted(p.parent.name for p in RAW_DIR.glob("*/parsed.json"))
        if not months:
            print("No parsed.json files found.", file=sys.stderr)
            return 1

        all_symbols = collect_symbols(months)
        print(f"# batch: {len(months)} months, {len(all_symbols)} symbols", file=sys.stderr)

        exchange_cache: dict[str, str] = {}
        total_missing: set[str] = set()

        for month in months:
            print(f"[{month}] fetching...", file=sys.stderr)
            doc = fetch_month(month, all_symbols, exchange_cache)
            out_path = PRICES_DIR / f"{month}.json"
            write_json(doc, out_path)
            print(f"[{month}] wrote {out_path}", file=sys.stderr)
            total_missing.update(doc["meta"]["missing_symbols"])

        print(
            f"# done: {len(months)} months, {len(all_symbols)} symbols, "
            f"{len(total_missing)} missing: {sorted(total_missing) or 'none'}",
            file=sys.stderr,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
