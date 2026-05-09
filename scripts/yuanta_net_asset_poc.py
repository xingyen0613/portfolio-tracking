"""
Compute daily net_asset for Yuanta PoC from daily_holdings.json + prices.

Reads:  data/derived/yuanta_poc/<YYYY-MM>/daily_holdings.json  (Phase 2)
        data/derived/yuanta_poc/prices/<YYYY-MM>.json           (Phase 1B)
Writes: data/derived/yuanta_poc/<YYYY-MM>/daily_net_asset.json

Formula: net_asset = market_value + pending_cash − margin_balance
  - market_value: sum(shares × close_price) for the day's holdings
  - pending_cash: running sum of net_cashflow from all transactions + margin txns
                  starting from the very first month (baseline=0). This captures
                  the cash that's "in-flight" between trade_date and settle_date,
                  preventing artificial drops when stocks are sold but settlement
                  hasn't happened yet.
  - margin_balance: from the parsed monthly statement

Non-trading days: forward-fill market_value from previous trading day. pending_cash
and margin_balance are tracked daily regardless of trading.
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


def load_official_month_end_net_asset(month: str) -> Decimal | None:
    """Read yuanta-official month-end net_asset from parsed.json summary."""
    raw_dir = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"
    path = raw_dir / month / "parsed.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        parsed = json.load(f)
    raw = parsed.get("summary", {}).get("net_asset")
    if raw in (None, ""):
        return None
    return Decimal(str(raw).replace(",", ""))


def load_other_assets(month: str) -> dict[str, Decimal]:
    """Extract non-stock holdings from yuanta summary.asset_categories.

    Stocks (上市/上櫃/興櫃) and pledged collateral are already in our
    market_value via daily_holdings. This pulls out the rest — primarily
    futures equity (期貨權益總值) — so they can be tracked as separate
    holding positions instead of being absorbed into cum_cash.

    Returns: {label: Decimal value}, e.g. {"期貨權益": 979030}.
    """
    raw_dir = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"
    path = raw_dir / month / "parsed.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        parsed = json.load(f)
    cats = parsed.get("summary", {}).get("asset_categories") or []
    other: dict[str, Decimal] = {}
    for c in cats:
        category = c.get("category", "")
        # Skip the stock-related categories already in our market_value
        if "上市" in category or "上櫃" in category or "興櫃" in category:
            continue
        if "擔保品" in category or "不限用途" in category:
            continue
        # Anything else (期貨, 認購權證 etc.) becomes a separate position
        try:
            value = Decimal(str(c.get("value", "0")).replace(",", ""))
        except Exception:
            continue
        if value != 0:
            # Strip any parenthesised qualifier for cleaner labels
            label = category.split("(")[0].strip() or category
            other[label] = value
    return other


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


def _sum_daily_cashflow(entry: dict) -> Decimal:
    """Sum net_cashflow from both transactions and margin transactions for a day.

    Yuanta's accounting has several "internal offset" cases where the same
    cash flow is recorded twice in the statement (once as a stock tx, once
    as a margin sub-account tx). To avoid double-counting:

    - ``repay_via_sell``: sale proceeds redirected directly to margin
      repayment. Already counted as the sale's net_cashflow on trade_date.
      Subtract here to neutralize.

    - ``advance_settlement_out``: yuanta advances cash for a same-day sale
      so the user gets proceeds without waiting T+2. Already counted as
      the sale's net_cashflow on trade_date. Subtract to avoid duplicating.

    - ``advance_settlement_in``: settles the advance internally on the
      original settle_date. Yuanta records net_cashflow=0 on the margin_tx
      (no real cash impact). No adjustment needed beyond the offset above.

    Note: we use *trade_date* throughout — every cash event is anchored
    to the day the trade happened, mirroring how the user perceives it.
    """
    total = Decimal(0)
    for tx in entry.get("transactions_today", []) or []:
        v = tx.get("net_cashflow")
        if v not in (None, ""):
            total += Decimal(str(v).replace(",", ""))
    for mt in entry.get("margin_transactions_today", []) or []:
        v = mt.get("net_cashflow")
        if v not in (None, ""):
            total += Decimal(str(v).replace(",", ""))
        repay_sell = mt.get("repay_via_sell")
        if repay_sell not in (None, ""):
            total -= Decimal(str(repay_sell).replace(",", ""))
        adv_out = mt.get("advance_settlement_out")
        if adv_out not in (None, ""):
            total -= Decimal(str(adv_out).replace(",", ""))
    return total


def _fmt_dec(d: Decimal) -> str:
    return str(int(d)) if d == d.to_integral_value() else str(d)


def compute_net_asset(month: str, start_cum_cash: Decimal = Decimal(0)) -> tuple[dict, Decimal]:
    """Compute daily net_asset for one month.

    start_cum_cash: cumulative cash flow at the END of the previous month
                    (= START of this month). For the very first month this is 0.

    Returns (result_dict, end_cum_cash) so callers can chain months.
    """
    holdings_doc = load_daily_holdings(month)
    prices_raw = load_prices(month)
    other_assets = load_other_assets(month)
    other_assets_total = sum(other_assets.values(), Decimal(0))

    all_days = [e["date"] for e in holdings_doc["daily"]]
    price_series = build_price_series(prices_raw, all_days)

    daily_results = []
    warnings = []

    cum_cash = start_cum_cash

    for entry in holdings_doc["daily"]:
        day = entry["date"]
        margin_raw = str(entry.get("margin_balance") or "0")
        margin = Decimal(margin_raw.replace(",", ""))

        # Update cum_cash with today's flows (regardless of trading day)
        cum_cash += _sum_daily_cashflow(entry)

        if day not in price_series:
            # Non-trading day: no market_value, but still track pending_cash + margin
            daily_results.append({
                "date": day,
                "market_value": None,
                "pending_cash": _fmt_dec(cum_cash),
                "margin_balance": margin_raw,
                "other_assets": {k: _fmt_dec(v) for k, v in other_assets.items()},
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

        # net_asset = stock holdings (owned + pledged) + other yuanta assets
        # (futures equity etc., from monthly statement) + pending_cash − margin
        net_asset = market_value + other_assets_total + cum_cash - margin

        daily_results.append({
            "date": day,
            "market_value": _fmt_dec(market_value),
            "pending_cash": _fmt_dec(cum_cash),
            "margin_balance": margin_raw,
            "other_assets": {k: _fmt_dec(v) for k, v in other_assets.items()},
            "net_asset": _fmt_dec(net_asset),
            "holdings_value": holdings_value,
            "unpriced_holdings": unpriced,
        })

    # Month-end calibration: align our last-day calculated net_asset with
    # yuanta-official month-end net_asset. The difference represents cash that
    # left the yuanta account through external transfers (which yuanta's
    # statement does not record). Without this anchor, "phantom cash" from
    # external withdrawals would carry forward to subsequent months and inflate
    # net_asset over time.
    correction = Decimal(0)
    official_end = load_official_month_end_net_asset(month)
    last_priced_idx = None
    for i in range(len(daily_results) - 1, -1, -1):
        if daily_results[i].get("net_asset") is not None:
            last_priced_idx = i
            break
    if official_end is not None and last_priced_idx is not None:
        our_end_na = Decimal(daily_results[last_priced_idx]["net_asset"])
        correction = official_end - our_end_na
        # Apply correction to the LAST trading day onward (jump-aligns to official
        # value). Earlier days keep the smooth in-month curve.
        for entry in daily_results[last_priced_idx:]:
            if entry.get("pending_cash") is not None:
                entry["pending_cash"] = _fmt_dec(Decimal(entry["pending_cash"]) + correction)
            if entry.get("net_asset") is not None:
                entry["net_asset"] = _fmt_dec(Decimal(entry["net_asset"]) + correction)
        cum_cash += correction

    result = {
        "meta": {
            "month": month,
            "source_holdings": f"data/derived/yuanta_poc/{month}/daily_holdings.json",
            "source_prices": f"data/derived/yuanta_poc/prices/{month}.json",
            "start_cum_cash": _fmt_dec(start_cum_cash),
            "end_cum_cash": _fmt_dec(cum_cash),
            "month_end_correction": _fmt_dec(correction),
            "official_month_end_net_asset": _fmt_dec(official_end) if official_end is not None else None,
        },
        "daily": daily_results,
        "warnings": warnings,
    }
    return result, cum_cash


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

    # Always compute in chronological order to chain pending_cash baseline
    all_months = sorted(
        p.parent.name
        for p in DERIVED_DIR.glob("*/daily_holdings.json")
        if (PRICES_DIR / f"{p.parent.name}.json").exists()
    )
    if not all_months:
        print("No matching month pairs found.", file=sys.stderr)
        return 1

    if args.month:
        if args.month not in all_months:
            print(f"month {args.month} not available (need both daily_holdings.json + prices)", file=sys.stderr)
            return 1
        # Chain through all earlier months silently to build baseline
        target_months = all_months[: all_months.index(args.month) + 1]
    elif args.batch:
        target_months = all_months
    else:
        parser.print_help()
        return 1

    cum_cash = Decimal(0)
    for month in target_months:
        result, cum_cash = compute_net_asset(month, start_cum_cash=cum_cash)
        # Only write the requested month(s) — when --month X, skip writing earlier ones
        if args.batch or month == args.month:
            out_path = DERIVED_DIR / month / "daily_net_asset.json"
            write_json(result, out_path)
            n_warn = len(result["warnings"])
            print(
                f"[{month}] wrote {out_path}  start_cash={result['meta']['start_cum_cash']}  end_cash={result['meta']['end_cum_cash']}"
                + (f" ({n_warn} warnings)" if n_warn else ""),
                file=sys.stderr,
            )
            for w in result["warnings"]:
                print(f"  WARN {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
