"""
Compute daily net_asset for Yuanta PoC from daily_holdings.json + prices.

Reads:  data/derived/yuanta_poc/<YYYY-MM>/daily_holdings.json  (Phase 2)
        data/derived/yuanta_poc/prices/<YYYY-MM>.json           (Phase 1B)
Writes: data/derived/yuanta_poc/<YYYY-MM>/daily_net_asset.json

Formula: net_asset = sum(shares * close_price per holding) - margin_balance
Non-trading days: forward-fill from previous trading day's close.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVED_DIR = PROJECT_ROOT / "data" / "derived" / "yuanta_poc"
PRICES_DIR = DERIVED_DIR / "prices"
NAME_CACHE_PATH = DERIVED_DIR / "name_to_symbol_cache.json"

TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_LIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"


# ---------------------------------------------------------------------------
# Name → Symbol resolver (on-demand + local cache)
# ---------------------------------------------------------------------------

def _fetch_exchange_name_map() -> dict[str, str]:
    """Download TWSE + TPEX listings and return {stock_name: symbol}."""
    import urllib.request
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
# I/O
# ---------------------------------------------------------------------------

def load_daily_holdings(month: str) -> dict:
    path = DERIVED_DIR / month / "daily_holdings.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_prices(month: str) -> dict[str, dict[str, str]]:
    path = PRICES_DIR / f"{month}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["prices"]


def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Price lookup with forward-fill
# ---------------------------------------------------------------------------

def build_price_series(
    prices: dict[str, dict[str, str]],
    all_days: list[str],
) -> dict[str, dict[str, str]]:
    """
    Return raw prices keyed by date (trading days only).
    Non-trading days have no entry — callers receive {} for those days.
    Forward-fill is intentionally NOT done here; it belongs at chart rendering time.
    """
    return {day: prices[day] for day in all_days if day in prices}


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def resolve_symbol(holding: dict) -> str | None:
    """Return the stock code to use for price lookup, or None if unresolvable."""
    sym = holding.get("symbol")
    if sym:
        return sym
    name = holding.get("name", "")
    return resolve_name_to_symbol(name) if name else None


def compute_net_asset(month: str) -> dict:
    holdings_doc = load_daily_holdings(month)
    prices_raw = load_prices(month)

    all_days = [e["date"] for e in holdings_doc["daily"]]
    price_series = build_price_series(prices_raw, all_days)

    daily_results = []
    warnings = []

    for entry in holdings_doc["daily"]:
        day = entry["date"]
        margin_raw = str(entry.get("margin_balance") or "0")
        margin = Decimal(margin_raw.replace(",", ""))

        if day not in price_series:
            # Non-trading day: no price data, leave market_value/net_asset as null
            daily_results.append({
                "date": day,
                "market_value": None,
                "margin_balance": margin_raw,
                "net_asset": None,
                "holdings_value": {},
                "unpriced_holdings": [],
            })
            continue

        day_prices = price_series[day]
        market_value = Decimal(0)
        holdings_value: dict[str, str] = {}
        unpriced: list[str] = []

        for h in entry["holdings"]:
            sym = resolve_symbol(h)
            shares = Decimal(h["shares"])
            if shares == 0:
                continue
            if sym and sym in day_prices:
                price = Decimal(day_prices[sym].replace(",", ""))
                value = shares * price
                market_value += value
                holdings_value[sym] = str(int(value)) if value == value.to_integral_value() else str(value)
            else:
                key = sym or f"name:{h.get('name', '?')}"
                unpriced.append(f"{key}({shares}股)")

        if unpriced:
            msg = f"{day}: 無價格 — {', '.join(unpriced)}"
            warnings.append(msg)

        net_asset = market_value - margin

        def _fmt(d: Decimal) -> str:
            return str(int(d)) if d == d.to_integral_value() else str(d)

        daily_results.append({
            "date": day,
            "market_value": _fmt(market_value),
            "margin_balance": margin_raw,
            "net_asset": _fmt(net_asset),
            "holdings_value": holdings_value,
            "unpriced_holdings": unpriced,
        })

    return {
        "meta": {
            "month": month,
            "source_holdings": f"data/derived/yuanta_poc/{month}/daily_holdings.json",
            "source_prices": f"data/derived/yuanta_poc/prices/{month}.json",
        },
        "daily": daily_results,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute daily net_asset from daily_holdings + prices"
    )
    parser.add_argument("--month", help="Compute for one month, e.g. 2026-02")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Compute for all months that have both daily_holdings.json and prices JSON",
    )
    args = parser.parse_args()

    months = []
    if args.month:
        months = [args.month]
    elif args.batch:
        months = sorted(
            p.parent.name
            for p in DERIVED_DIR.glob("*/daily_holdings.json")
            if (PRICES_DIR / f"{p.parent.name}.json").exists()
        )
        if not months:
            print("No matching month pairs found.", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1

    for month in months:
        result = compute_net_asset(month)
        out_path = DERIVED_DIR / month / "daily_net_asset.json"
        write_json(result, out_path)
        n_warn = len(result["warnings"])
        print(f"[{month}] wrote {out_path}" + (f" ({n_warn} warnings)" if n_warn else ""), file=sys.stderr)
        for w in result["warnings"]:
            print(f"  WARN {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
