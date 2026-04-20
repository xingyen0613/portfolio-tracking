"""
Backward reconstruction of daily holdings from Yuanta parsed.json.

Reads: data/raw/yuanta_poc/<YYYY-MM>/parsed.json  (Phase 1A output)
Writes: data/derived/yuanta_poc/<YYYY-MM>/daily_holdings.json
        data/derived/yuanta_poc/<YYYY-MM>/cross_check.json  (if previous month available)

Algorithm: Start from month-end Position Anchor (owned + pledged shares summed per symbol),
reverse each transaction backward to derive holdings list for every day in the period.
margin_balance is reconstructed backward using named columns from margin_transactions.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"
DERIVED_DIR = PROJECT_ROOT / "data" / "derived" / "yuanta_poc"


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
# Helpers
# ---------------------------------------------------------------------------

def _holdings_key(h: dict) -> str:
    """Internal dict key for a holding: symbol if known, else 'name:<name>'."""
    return h["symbol"] if h.get("symbol") else f"name:{h['name']}"


def _str_to_decimal(s) -> Decimal:
    if not s:
        return Decimal(0)
    return Decimal(str(s).replace(",", ""))


def _decimal_to_str(d: Decimal) -> str:
    """Return integer string if no fractional part, else decimal string."""
    if d == d.to_integral_value():
        return str(int(d))
    return str(d)


def _holdings_list_to_dict(holdings: list[dict]) -> dict[str, int]:
    """Convert [{symbol, name, shares}] list to {key: shares} dict for computation."""
    return {_holdings_key(h): h["shares"] for h in holdings}


# ---------------------------------------------------------------------------
# Name → symbol lookup (best-effort)
# ---------------------------------------------------------------------------

def build_name_symbol_map(parsed: dict) -> dict[str, str]:
    """Build {name: symbol} from owned holdings + transactions of a single parsed dict."""
    mapping: dict[str, str] = {}
    for h in parsed.get("holdings_owned", []):
        sym = h.get("symbol")
        name = h.get("name")
        if sym and name:
            mapping[name] = sym
    for t in parsed.get("transactions", []):
        sym = t.get("symbol")
        name = t.get("name")
        if sym and name:
            mapping[name] = sym
    return mapping


def build_global_name_symbol_map(all_parsed: list[dict]) -> dict[str, str]:
    """Merge name→symbol maps across all months for consistent key resolution."""
    mapping: dict[str, str] = {}
    for parsed in all_parsed:
        mapping.update(build_name_symbol_map(parsed))
    return mapping


# ---------------------------------------------------------------------------
# Position Anchor
# ---------------------------------------------------------------------------

def compute_anchor(
    parsed: dict,
    global_name_sym: dict[str, str] | None = None,
) -> tuple[list[dict], str]:
    """
    Return (anchor_holdings, anchor_margin).

    anchor_holdings: list of {symbol: str|None, name: str, shares: int}
      symbol is None for pledged collateral not resolvable from any transaction history.
    anchor_margin: str (period-end margin_balance from summary)

    Combines owned + pledged shares. Uses global_name_sym for cross-month name resolution;
    falls back to single-month map if not provided.
    """
    name_sym = global_name_sym if global_name_sym is not None else build_name_symbol_map(parsed)

    # Accumulate by key to merge owned + pledged for same stock
    merged: dict[str, dict] = {}

    for h in parsed.get("holdings_owned", []):
        sym = h.get("symbol")
        if not sym:
            continue
        name = h.get("name", "")
        qty = int(h.get("shares_collateral_free") or 0)
        key = sym
        if key in merged:
            merged[key]["shares"] += qty
        else:
            merged[key] = {"symbol": sym, "name": name, "shares": qty}

    for h in parsed.get("holdings_pledged", []):
        name = h.get("name", "")
        sym = name_sym.get(name) or None  # None if not resolvable
        key = sym if sym else f"name:{name}"
        qty = int(h.get("shares_balance") or 0)
        if key in merged:
            merged[key]["shares"] += qty
        else:
            merged[key] = {"symbol": sym, "name": name, "shares": qty}

    anchor_holdings = list(merged.values())
    anchor_margin = str(parsed["summary"].get("margin_balance") or "0")
    return anchor_holdings, anchor_margin


# ---------------------------------------------------------------------------
# Shares backward reconstruction
# ---------------------------------------------------------------------------

def _date_range(start: str, end: str) -> list[str]:
    """Return all calendar dates from start to end inclusive, as YYYY-MM-DD strings."""
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    days = []
    cur = d0
    while cur <= d1:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def reconstruct_shares(
    parsed: dict,
    anchor_holdings: list[dict],
) -> dict[str, dict[str, int]]:
    """
    Backward reconstruction of shares for every day in the Statement Period.

    Returns {date_str: {key: shares}} where key = symbol or 'name:<name>'.
    Transactions only affect symbol-keyed entries (pledged-only stocks are unchanged).
    """
    meta = parsed["meta"]
    period_start = meta["period_start"]
    period_end = meta["period_end"]
    all_days = _date_range(period_start, period_end)

    # Index transactions by trade_date
    txns_by_date: dict[str, list[dict]] = defaultdict(list)
    for t in parsed.get("transactions", []):
        txns_by_date[t["trade_date"]].append(t)

    # Start from period_end anchor, go backwards
    state: dict[str, int] = _holdings_list_to_dict(anchor_holdings)
    series: dict[str, dict[str, int]] = {}
    series[period_end] = dict(state)

    for day in reversed(all_days[:-1]):  # period_end already set
        next_day = all_days[all_days.index(day) + 1]
        # Reverse next_day's transactions
        net_buy: dict[str, int] = defaultdict(int)
        for t in txns_by_date.get(next_day, []):
            sym = t.get("symbol")
            if not sym:
                continue
            qty = int(t.get("shares") or 0)
            if t.get("side") == "買":
                net_buy[sym] += qty
            else:
                net_buy[sym] -= qty
        prev_state: dict[str, int] = {}
        all_syms = set(state) | set(net_buy)
        for sym in all_syms:
            prev_state[sym] = state.get(sym, 0) - net_buy.get(sym, 0)
        state = prev_state
        series[day] = dict(state)

    return series


# ---------------------------------------------------------------------------
# Margin backward reconstruction
# ---------------------------------------------------------------------------

def _reconstruct_margin(
    parsed: dict,
    anchor_margin: str,
) -> dict[str, str]:
    """
    Backward-reconstruct daily margin_balance using named margin_transaction columns.

    Returns {date_str: margin_balance_str} for all days in the Statement Period.
    Formula: margin[day] = margin[day+1] - borrow[day+1] + cash_repay[day+1] + repay_via_sell[day+1]
    """
    meta = parsed["meta"]
    period_start = meta["period_start"]
    period_end = meta["period_end"]
    all_days = _date_range(period_start, period_end)

    margin_txns_by_date: dict[str, list[dict]] = defaultdict(list)
    for mt in parsed.get("margin_transactions", []):
        margin_txns_by_date[mt["date"]].append(mt)

    cur = _str_to_decimal(anchor_margin)
    series: dict[str, str] = {}
    series[period_end] = _decimal_to_str(cur)

    for day in reversed(all_days[:-1]):
        next_day = all_days[all_days.index(day) + 1]
        # Undo next_day's margin transactions
        for mt in margin_txns_by_date.get(next_day, []):
            cur -= _str_to_decimal(mt.get("borrow"))
            cur += _str_to_decimal(mt.get("cash_repay"))
            cur += _str_to_decimal(mt.get("repay_via_sell"))
        series[day] = _decimal_to_str(cur)

    return series


# ---------------------------------------------------------------------------
# Build daily entries
# ---------------------------------------------------------------------------

def _series_to_holdings_list(
    day_dict: dict[str, int],
    anchor_holdings: list[dict],
) -> list[dict]:
    """
    Convert {key: shares} dict to [{symbol, name, shares}] list.
    Uses anchor_holdings to recover symbol/name metadata for each key.
    """
    key_info: dict[str, dict] = {_holdings_key(h): h for h in anchor_holdings}
    result = []
    for key, shares in sorted(day_dict.items()):
        if key in key_info:
            h = key_info[key]
            result.append({"symbol": h["symbol"], "name": h["name"], "shares": shares})
        else:
            # symbol introduced mid-month by transaction (no pledged entry)
            result.append({"symbol": key, "name": "", "shares": shares})
    return result


def build_daily_entries(
    parsed: dict,
    shares_series: dict[str, dict[str, int]],
    anchor_holdings: list[dict],
    anchor_margin: str,
) -> list[dict]:
    """Assemble the rich daily entry list for daily_holdings.json."""
    meta = parsed["meta"]
    period_start = meta["period_start"]
    period_end = meta["period_end"]
    source_month = meta.get("period_end", "")[:7]  # YYYY-MM

    txns_by_date: dict[str, list[dict]] = defaultdict(list)
    for t in parsed.get("transactions", []):
        txns_by_date[t["trade_date"]].append(t)

    margin_txns_by_date: dict[str, list[dict]] = defaultdict(list)
    for mt in parsed.get("margin_transactions", []):
        margin_txns_by_date[mt["date"]].append(mt)

    margin_series = _reconstruct_margin(parsed, anchor_margin)

    all_days = _date_range(period_start, period_end)
    entries = []
    for day in all_days:
        day_txns = txns_by_date.get(day, [])

        # daily_change_shares from this day's transactions (symbol-keyed, no name-only)
        net_buy: dict[str, int] = defaultdict(int)
        for t in day_txns:
            sym = t.get("symbol")
            if not sym:
                continue
            qty = int(t.get("shares") or 0)
            if t.get("side") == "買":
                net_buy[sym] += qty
            else:
                net_buy[sym] -= qty

        day_margin_txns = margin_txns_by_date.get(day, [])

        # daily borrow/repay summary
        daily_borrow = _decimal_to_str(
            sum(_str_to_decimal(mt.get("borrow")) for mt in day_margin_txns) or Decimal(0)
        ) if day_margin_txns else None
        daily_repay = _decimal_to_str(
            sum(
                _str_to_decimal(mt.get("cash_repay")) + _str_to_decimal(mt.get("repay_via_sell"))
                for mt in day_margin_txns
            ) or Decimal(0)
        ) if day_margin_txns else None

        entry = {
            "date": day,
            "holdings": _series_to_holdings_list(shares_series[day], anchor_holdings),
            "margin_balance": margin_series[day],
            "daily_change_shares": dict(net_buy),
            "daily_borrow": daily_borrow,
            "daily_repay": daily_repay,
            "transactions_today": day_txns,
            "margin_transactions_today": day_margin_txns,
            "source_pdf_month": source_month,
        }
        entries.append(entry)

    return entries


def _sanity_check(entries: list[dict]) -> list[str]:
    """Return list of warning strings for any negative share counts."""
    warnings = []
    for entry in entries:
        for h in entry["holdings"]:
            if h["shares"] < 0:
                key = h["symbol"] or f"name:{h['name']}"
                warnings.append(
                    f"  WARN negative shares: {entry['date']} {key} = {h['shares']}"
                )
    return warnings


# ---------------------------------------------------------------------------
# Reconstruct one month
# ---------------------------------------------------------------------------

def reconstruct_one(
    month: str,
    global_name_sym: dict[str, str] | None = None,
) -> dict:
    """Reconstruct and write daily_holdings.json for one month. Returns parsed dict."""
    parsed = load_parsed(month)
    meta = parsed["meta"]

    anchor_holdings, anchor_margin = compute_anchor(parsed, global_name_sym)
    shares_series = reconstruct_shares(parsed, anchor_holdings)
    entries = build_daily_entries(parsed, shares_series, anchor_holdings, anchor_margin)

    warnings = _sanity_check(entries)
    if warnings:
        print(f"[{month}] Sanity check warnings:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    # anchor_holdings for meta (as {key: shares} for readability)
    anchor_shares_meta = {_holdings_key(h): h["shares"] for h in anchor_holdings}

    output = {
        "meta": {
            "month": month,
            "period_start": meta["period_start"],
            "period_end": meta["period_end"],
            "source_pdf_month": month,
            "reconstruction_method": "backward",
            "anchor_holdings": anchor_holdings,
            "anchor_total_shares": anchor_shares_meta,
            "anchor_margin_balance": anchor_margin,
            "margin_reconstruction_quality": "full_daily",
        },
        "daily": entries,
    }

    out_path = DERIVED_DIR / month / "daily_holdings.json"
    write_json(output, out_path)
    print(f"[{month}] wrote {out_path}", file=sys.stderr)
    return parsed


# ---------------------------------------------------------------------------
# Cross-check
# ---------------------------------------------------------------------------

def chain_check(
    current_parsed: dict,
    previous_parsed: dict,
    global_name_sym: dict[str, str] | None = None,
) -> dict:
    """
    Compare current month's implicit Day 0 vs previous month's Position Anchor.

    Day 0 = state before period_start = period_start's holdings minus period_start's transactions.
    """
    cur_meta = current_parsed["meta"]
    cur_month = cur_meta["period_end"][:7]
    prev_meta = previous_parsed["meta"]
    prev_month = prev_meta["period_end"][:7]
    prev_period_end = prev_meta["period_end"]

    prev_anchor_holdings, prev_anchor_margin = compute_anchor(previous_parsed, global_name_sym)
    prev_anchor_dict = _holdings_list_to_dict(prev_anchor_holdings)

    # Load current month's daily_holdings.json
    daily_path = DERIVED_DIR / cur_month / "daily_holdings.json"
    with open(daily_path, encoding="utf-8") as f:
        daily = json.load(f)

    first_entry = daily["daily"][0]
    first_day_holdings = _holdings_list_to_dict(
        {h["symbol"] or f"name:{h['name']}": h for h in first_entry["holdings"]}.values()
        if isinstance(first_entry["holdings"][0], dict) else []
    ) if first_entry["holdings"] else {}
    # simpler: build dict directly
    first_day_shares: dict[str, int] = {}
    for h in first_entry["holdings"]:
        key = h["symbol"] if h.get("symbol") else f"name:{h['name']}"
        first_day_shares[key] = h["shares"]
    first_day_change = first_entry["daily_change_shares"]

    # Implicit day 0 shares = first day shares - first day net buy
    implicit_prev_end: dict[str, int] = {}
    all_syms = set(first_day_shares) | set(first_day_change)
    for sym in all_syms:
        implicit_prev_end[sym] = first_day_shares.get(sym, 0) - first_day_change.get(sym, 0)

    def drop_zeros(d: dict) -> dict:
        return {k: v for k, v in d.items() if v != 0}

    implicit_clean = drop_zeros(implicit_prev_end)
    prev_clean = drop_zeros(prev_anchor_dict)

    all_diff_syms = set(implicit_clean) | set(prev_clean)
    diff_shares = {}
    for sym in sorted(all_diff_syms):
        chained = implicit_clean.get(sym, 0)
        prev_end = prev_clean.get(sym, 0)
        diff = chained - prev_end
        if diff != 0:
            diff_shares[sym] = {
                "chained": chained,
                "previous_month_end": prev_end,
                "diff": diff,
            }

    # Implicit day 0 margin = first day margin - first day margin delta
    first_margin = _str_to_decimal(first_entry.get("margin_balance"))
    first_borrow = _str_to_decimal(first_entry.get("daily_borrow"))
    first_repay = _str_to_decimal(first_entry.get("daily_repay"))
    implicit_margin = first_margin - first_borrow + first_repay
    implicit_margin_str = _decimal_to_str(implicit_margin)
    margin_diff = implicit_margin - _str_to_decimal(prev_anchor_margin)

    status = "match" if not diff_shares and margin_diff == 0 else "mismatch"

    check = {
        "current_month": cur_month,
        "compared_with": prev_month,
        "anchor_date": prev_period_end,
        "status": status,
        "diff_shares": diff_shares,
        "diff_margin_balance": {
            "chained": implicit_margin_str,
            "previous_month_end": prev_anchor_margin,
            "diff": _decimal_to_str(margin_diff),
        },
    }

    out_path = DERIVED_DIR / cur_month / "cross_check.json"
    write_json(check, out_path)
    return check


# ---------------------------------------------------------------------------
# Timeline view
# ---------------------------------------------------------------------------

def render_timeline_markdown(
    months: list[str],
    start: str | None = None,
    end: str | None = None,
    symbol_filter: str | None = None,
) -> str:
    """Load daily_holdings.json files and render a markdown table."""
    all_entries = []
    for month in months:
        path = DERIVED_DIR / month / "daily_holdings.json"
        if not path.exists():
            print(f"[timeline] missing {path}", file=sys.stderr)
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        all_entries.extend(data["daily"])

    if start:
        all_entries = [e for e in all_entries if e["date"] >= start]
    if end:
        all_entries = [e for e in all_entries if e["date"] <= end]

    if not all_entries:
        return "_No data in range._"

    # Collect all symbols (or name-keys) from holdings list
    all_keys: set[str] = set()
    for e in all_entries:
        for h in e["holdings"]:
            all_keys.add(h["symbol"] if h.get("symbol") else f"name:{h['name']}")
    if symbol_filter:
        all_keys = {symbol_filter} if symbol_filter in all_keys else set()
    sorted_keys = sorted(all_keys)

    cols = ["date"] + sorted_keys + ["margin_balance"]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"

    rows = [header, sep]
    for entry in all_entries:
        # Convert holdings list to dict for easy lookup
        shares_dict: dict[str, int] = {}
        for h in entry["holdings"]:
            key = h["symbol"] if h.get("symbol") else f"name:{h['name']}"
            shares_dict[key] = h["shares"]
        cells = [entry["date"]]
        for key in sorted_keys:
            cells.append(str(shares_dict.get(key, 0)))
        cells.append(str(entry.get("margin_balance") or ""))
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backward-reconstruct daily holdings from Yuanta parsed.json"
    )
    parser.add_argument("--month", help="Reconstruct a single month, e.g. 2026-02")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Reconstruct all months found under data/raw/yuanta_poc/*/parsed.json",
    )
    parser.add_argument(
        "--timeline",
        nargs=2,
        metavar=("START", "END"),
        help="Print markdown timeline table for date range, e.g. 2026-01-01 2026-03-31",
    )
    parser.add_argument("--symbol", help="Filter timeline to a single symbol")
    args = parser.parse_args()

    if args.month:
        reconstruct_one(args.month)
        return 0

    if args.batch:
        months = sorted(
            p.parent.name
            for p in RAW_DIR.glob("*/parsed.json")
        )
        if not months:
            print("No parsed.json files found.", file=sys.stderr)
            return 1

        print(f"# batch: {len(months)} months", file=sys.stderr)

        all_parsed_for_map = []
        for month in months:
            try:
                all_parsed_for_map.append(load_parsed(month))
            except Exception:
                pass
        global_name_sym = build_global_name_symbol_map(all_parsed_for_map)

        parsed_by_month: dict[str, dict] = {}
        failures = []

        for month in months:
            try:
                parsed_by_month[month] = reconstruct_one(month, global_name_sym)
            except Exception as e:
                failures.append((month, str(e)))
                print(f"[{month}] ERROR: {e}", file=sys.stderr)

        successful = [m for m in months if m in parsed_by_month]
        checks_match = 0
        checks_mismatch = 0
        for i in range(1, len(successful)):
            cur = successful[i]
            prev = successful[i - 1]
            try:
                check = chain_check(parsed_by_month[cur], parsed_by_month[prev], global_name_sym)
                status = check["status"]
                if status == "match":
                    checks_match += 1
                    print(f"[cross-check] {prev}→{cur}: match", file=sys.stderr)
                else:
                    checks_mismatch += 1
                    diff_summary = {
                        sym: d["diff"] for sym, d in check["diff_shares"].items()
                    }
                    margin_diff = check["diff_margin_balance"]["diff"]
                    print(
                        f"[cross-check] {prev}→{cur}: MISMATCH shares={diff_summary} margin_diff={margin_diff}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"[cross-check] {prev}→{cur}: ERROR {e}", file=sys.stderr)

        total_checks = checks_match + checks_mismatch
        print(
            f"# {len(successful)} months processed, "
            f"{total_checks} cross-checks: {checks_match} match / {checks_mismatch} mismatch",
            file=sys.stderr,
        )
        if failures:
            print(f"# {len(failures)} failures", file=sys.stderr)
            return 1
        return 0

    if args.timeline:
        start, end = args.timeline
        months = sorted(p.parent.name for p in DERIVED_DIR.glob("*/daily_holdings.json"))
        print(render_timeline_markdown(months, start, end, args.symbol))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
