"""
Data access layer for the dashboard.
Reads from PostgreSQL and returns aggregated DataFrames.
"""

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.utils.fx import get_fx_rates_series, get_latest_fx_rate, lookup_rate
from config.db import get_conn
from config.settings import PLATFORM_CATEGORY, ROOT_DIR, TWD_PER_USD

warnings.filterwarnings("ignore", "pandas only supports SQLAlchemy")

_YUANTA_DERIVED = ROOT_DIR / "data" / "derived" / "yuanta_poc"
_YUANTA_RAW = ROOT_DIR / "data" / "raw" / "yuanta_poc"


def get_latest_snapshot_date(user_id: str) -> str | None:
    """Return the most recent snapshot date that has holdings."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) AS d FROM normalized_holdings WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return row["d"] if row else None


def get_holdings(user_id: str) -> pd.DataFrame:
    """
    Return the latest holdings per account.
    For each account, picks the most recent successful source_run
    regardless of date or batch, so all platforms are always shown
    even if they were last fetched on different days.

    For sources that store multi-day data in a single source_run
    (e.g. yuanta monthly statements with daily reconstruction), only the
    latest snapshot_date within that source_run is returned.
    """
    sql = """
        SELECT
            p.name        AS platform,
            a.label       AS account_label,
            a.account_key AS account_key,
            nh.platform_symbol,
            nh.platform_asset_name,
            nh.asset_type,
            nh.quantity,
            nh.price,
            nh.value,
            nh.price_source,
            nh.original_currency,
            nh.snapshot_date,
            nh.chain,
            sr.id         AS source_run_id,
            sr.started_at AS fetched_at
        FROM normalized_holdings nh
        JOIN source_runs sr ON nh.source_run_id = sr.id
        JOIN accounts a     ON sr.account_id = a.id
        JOIN platforms p    ON a.platform_id = p.id
        WHERE sr.status = 'success'
          AND a.user_id = %s
          -- Pick only the latest source_run per account (avoids duplicates when
          -- multiple batches ran the same day)
          AND sr.id = (
              SELECT sr2.id FROM source_runs sr2
              WHERE sr2.account_id = a.id AND sr2.status = 'success'
                AND EXISTS (SELECT 1 FROM normalized_holdings WHERE source_run_id = sr2.id)
              ORDER BY sr2.started_at DESC LIMIT 1
          )
          -- Within that source_run, only the latest snapshot_date (handles
          -- yuanta which writes a whole month under one source_run)
          AND nh.snapshot_date = (
              SELECT MAX(snapshot_date) FROM normalized_holdings
              WHERE source_run_id = nh.source_run_id
          )
        ORDER BY p.name, a.account_key, nh.value DESC NULLS LAST
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))

    df["category"] = df["platform"].map(PLATFORM_CATEGORY).fillna("unknown")
    raw = pd.to_numeric(df["value"], errors="coerce")
    fx = get_latest_fx_rate()
    # Some sources (e.g. yuanta) store values in TWD; others already in USD.
    df["value_usd"] = raw.where(df["original_currency"] != "TWD", raw / fx)
    df["value_twd"] = df["value_usd"] * fx
    return df


def get_snapshot_history(user_id: str) -> pd.DataFrame:
    """
    Return category-level daily totals from category_snapshots (materialized layer).
    Used for the time series chart.
    """
    sql = """
        SELECT snapshot_date, category, total_value, currency, source
        FROM category_snapshots
        WHERE user_id = %s
        ORDER BY snapshot_date, category
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")

    rates = get_fx_rates_series()
    df["value_usd"] = df.apply(
        lambda r: r["total_value"] / lookup_rate(r["snapshot_date"], rates)
        if r["currency"] == "TWD"
        else r["total_value"],
        axis=1,
    )
    return df


def get_crypto_platform_daily(user_id: str) -> pd.DataFrame:
    """
    Return per-date per-platform totals for crypto platforms.
    Used only for the hover breakdown in the 幣圈 line.
    Takes the latest account_snapshot per account per date to avoid
    double-counting when multiple batches ran on the same day.
    """
    sql = """
        SELECT
            p.name          AS platform,
            acs.snapshot_date,
            SUM(acs.total_value) AS value_usd
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.total_value IS NOT NULL
          AND acs.user_id = %s
          AND p.name IN ('binance', 'okx', 'mexc', 'bybit', 'sui_wallet')
          AND acs.id = (
              SELECT id FROM account_snapshots
              WHERE account_id = acs.account_id
                AND snapshot_date = acs.snapshot_date
                AND total_value IS NOT NULL
              ORDER BY created_at DESC LIMIT 1
          )
        GROUP BY p.name, acs.snapshot_date
        ORDER BY acs.snapshot_date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_crypto_symbol_breakdown(user_id: str) -> pd.DataFrame:
    """
    Return per-date per-token breakdown for crypto platforms.
    Source: normalized_holdings (only available for dates with actual batch runs).
    Groups by platform_symbol so hover shows individual token percentages.
    """
    sql = """
        SELECT
            nh.snapshot_date,
            nh.platform_symbol AS symbol,
            SUM(nh.value) AS value_usd
        FROM normalized_holdings nh
        JOIN source_runs sr ON nh.source_run_id = sr.id
        JOIN accounts a     ON sr.account_id = a.id
        JOIN platforms p    ON a.platform_id = p.id
        WHERE p.name IN ('binance', 'okx', 'mexc', 'bybit', 'sui_wallet')
          AND nh.value IS NOT NULL
          AND nh.user_id = %s
          AND sr.status = 'success'
          AND sr.id = (
              SELECT sr2.id FROM source_runs sr2
              WHERE sr2.account_id = a.id
                AND sr2.status = 'success'
                AND EXISTS (
                    SELECT 1 FROM normalized_holdings nh2
                    WHERE nh2.source_run_id = sr2.id
                      AND nh2.snapshot_date = nh.snapshot_date
                )
              ORDER BY sr2.started_at DESC LIMIT 1
          )
        GROUP BY nh.snapshot_date, nh.platform_symbol
        ORDER BY nh.snapshot_date, value_usd DESC
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_us_stock_platform_daily(user_id: str) -> pd.DataFrame:
    """Per-date per-platform totals for us_stock (ibkr + firsttrade). Used for hover breakdown."""
    sql = """
        SELECT
            p.name          AS platform,
            acs.snapshot_date,
            SUM(acs.total_value) AS value_usd
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.total_value IS NOT NULL
          AND acs.user_id = %s
          AND p.name IN ('ibkr', 'firsttrade')
          AND acs.currency = 'USD'
          AND acs.id = (
              SELECT id FROM account_snapshots
              WHERE account_id = acs.account_id
                AND snapshot_date = acs.snapshot_date
                AND total_value IS NOT NULL
              ORDER BY created_at DESC LIMIT 1
          )
        GROUP BY p.name, acs.snapshot_date
        ORDER BY acs.snapshot_date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_us_stock_symbol_breakdown(user_id: str) -> pd.DataFrame:
    """Per-date per-stock breakdown for us_stock platforms. Only available on batch-run dates."""
    sql = """
        SELECT
            nh.snapshot_date,
            nh.platform_symbol AS symbol,
            SUM(nh.value) AS value_usd
        FROM normalized_holdings nh
        JOIN source_runs sr ON nh.source_run_id = sr.id
        JOIN accounts a     ON sr.account_id = a.id
        JOIN platforms p    ON a.platform_id = p.id
        WHERE p.name IN ('ibkr', 'firsttrade')
          AND nh.asset_type = 'stock'
          AND nh.value IS NOT NULL
          AND nh.user_id = %s
          AND sr.status = 'success'
          AND sr.id = (
              SELECT sr2.id FROM source_runs sr2
              WHERE sr2.account_id = a.id
                AND sr2.status = 'success'
                AND EXISTS (
                    SELECT 1 FROM normalized_holdings nh2
                    WHERE nh2.source_run_id = sr2.id
                      AND nh2.snapshot_date = nh.snapshot_date
                )
              ORDER BY sr2.started_at DESC LIMIT 1
          )
        GROUP BY nh.snapshot_date, nh.platform_symbol
        ORDER BY nh.snapshot_date, value_usd DESC
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_tw_stock_symbol_breakdown(user_id: str) -> pd.DataFrame:
    """
    Return per-date per-stock breakdown for tw_stock (yuanta).
    Source: daily_net_asset.json holdings_value (TWD per symbol).
    Only includes trading days where holdings_value is non-empty.

    Multi-tenancy guard: data is only returned for users who actually own a
    yuanta account in the DB (currently only SYSTEM_OWNER). Returns an empty
    DataFrame for any other user, since this data file is shared across the
    deployment but the source PDFs are owner-specific.
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT 1 FROM accounts a
               JOIN platforms p ON a.platform_id = p.id
               WHERE p.name='yuanta' AND a.user_id=%s LIMIT 1""",
            (user_id,),
        ).fetchone()
    if not row:
        return pd.DataFrame(columns=["snapshot_date", "symbol", "value_usd"])

    rates = get_fx_rates_series()
    rows = []
    for na_file in sorted(_YUANTA_DERIVED.glob("*/daily_net_asset.json")):
        with open(na_file, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("daily", []):
            hv = entry.get("holdings_value")
            if not hv:
                continue
            date_str = entry["date"]
            rate = lookup_rate(date_str, rates)
            for symbol, value_str in hv.items():
                rows.append({
                    "snapshot_date": date_str,
                    "symbol": symbol,
                    "value_usd": float(value_str) / rate,
                })

    if not rows:
        return pd.DataFrame(columns=["snapshot_date", "symbol", "value_usd"])

    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df.sort_values(["snapshot_date", "value_usd"], ascending=[True, False])


def get_tw_stock_platform_daily(user_id: str) -> pd.DataFrame:
    """Per-date per-platform totals for tw_stock (yuanta, extensible). Used for hover breakdown."""
    sql = """
        SELECT
            p.name          AS platform,
            acs.snapshot_date,
            SUM(acs.total_value) AS total_twd
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.total_value IS NOT NULL
          AND acs.user_id = %s
          AND p.name IN ('yuanta')
          AND acs.currency = 'TWD'
          AND acs.id = (
              SELECT id FROM account_snapshots
              WHERE account_id = acs.account_id
                AND snapshot_date = acs.snapshot_date
                AND total_value IS NOT NULL
              ORDER BY created_at DESC LIMIT 1
          )
        GROUP BY p.name, acs.snapshot_date
        ORDER BY acs.snapshot_date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["total_twd"] = pd.to_numeric(df["total_twd"], errors="coerce")

    rates = get_fx_rates_series()
    df["value_usd"] = df.apply(
        lambda r: r["total_twd"] / lookup_rate(r["snapshot_date"], rates), axis=1
    )
    return df


def get_platform_latest_account_snapshot(user_id: str) -> dict[str, dict]:
    """
    Return the latest account_snapshot per platform (by snapshot_date, then created_at).
    Used to detect platforms that have been zeroed out more recently than their last holdings.
    Returns {platform_name: {snapshot_date, total_value, currency}}.
    """
    sql = """
        SELECT p.name AS platform, acs.snapshot_date, acs.total_value, acs.currency
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.user_id = %s
          AND acs.id = (
            SELECT id FROM account_snapshots
            WHERE account_id = acs.account_id
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
        )
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        platform = row["platform"]
        existing = result.get(platform)
        if existing is None or row["snapshot_date"] > existing["snapshot_date"]:
            result[platform] = {
                "snapshot_date": row["snapshot_date"],
                "total_value": row["total_value"],
                "currency": row["currency"],
            }
    return result


def get_latest_category_totals(user_id: str) -> pd.DataFrame:
    """
    Return the latest total value per category from category_snapshots.
    Used for the pie chart so all categories (crypto/tw_stock/us_stock) appear
    even if they don't have normalized_holdings (no connector yet).
    """
    sql = """
        SELECT DISTINCT ON (category) category, total_value, currency
        FROM category_snapshots
        WHERE user_id = %s AND total_value > 0
        ORDER BY category, snapshot_date DESC
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn.raw, params=(user_id,))
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")
    latest_rate = get_latest_fx_rate()
    df["value_usd"] = df.apply(
        lambda r: r["total_value"] / latest_rate if r["currency"] == "TWD" else r["total_value"],
        axis=1,
    )
    return df


def get_yuanta_holdings_detail() -> dict:
    """
    Return latest detailed holdings for yuanta from JSON files.
    Combines parsed.json (owned/pledged classification) with
    daily_net_asset.json (latest trading day values).
    Returns empty dict if no data available.
    """
    months = sorted(
        [p.parent.name for p in _YUANTA_DERIVED.glob("*/daily_net_asset.json")],
        reverse=True,
    )
    if not months:
        return {}

    latest_month = months[0]

    with open(_YUANTA_DERIVED / latest_month / "daily_net_asset.json", encoding="utf-8") as f:
        na_data = json.load(f)
    latest_entry = next(
        (e for e in reversed(na_data["daily"]) if e.get("net_asset") is not None),
        None,
    )
    if not latest_entry:
        return {}

    holdings_value = {k: float(v) for k, v in (latest_entry.get("holdings_value") or {}).items()}

    cache_path = _YUANTA_DERIVED / "name_to_symbol_cache.json"
    name_to_sym: dict[str, str] = {}
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            name_to_sym = json.load(f)

    owned: list[dict] = []
    pledged: list[dict] = []
    parsed_path = _YUANTA_RAW / latest_month / "parsed.json"
    parsed: dict = {}
    if parsed_path.exists():
        with open(parsed_path, encoding="utf-8") as f:
            parsed = json.load(f)

        for h in parsed.get("holdings_owned", []):
            sym = h.get("symbol")
            owned.append({
                "symbol": sym or "—",
                "name": h.get("name", ""),
                "shares": int(h.get("shares_collateral_free") or 0),
                "value_twd": holdings_value.get(sym) if sym else None,
            })

        for h in parsed.get("holdings_pledged", []):
            name = h.get("name", "")
            sym = h.get("symbol") or name_to_sym.get(name)
            pledged.append({
                "symbol": sym or "—",
                "name": name,
                "shares_balance": int(h.get("shares_balance") or 0),
                "shares_used": int(h.get("shares_used") or 0),
                "shares_remaining": int(h.get("shares_remaining") or 0),
                "value_twd": holdings_value.get(sym) if sym else None,
            })

    owned.sort(key=lambda x: x["value_twd"] or 0, reverse=True)
    pledged.sort(key=lambda x: x["value_twd"] or 0, reverse=True)

    # other_assets: futures equity etc. from latest_entry (already extracted by net_asset script)
    other_assets_raw = latest_entry.get("other_assets") or {}
    other_assets: list[dict] = []
    for label, value in other_assets_raw.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if v == 0:
            continue
        other_assets.append({"label": label, "value_twd": v})

    summary = parsed.get("summary", {})
    return {
        "date": latest_entry["date"],
        "month": latest_month,
        "market_value": float(latest_entry.get("market_value") or 0),
        "margin_balance": float(latest_entry.get("margin_balance") or 0),
        "net_asset": float(latest_entry.get("net_asset") or 0),
        "margin_maintenance_pct": summary.get("margin_maintenance_pct"),
        "owned": owned,
        "pledged": pledged,
        "other_assets": other_assets,
    }


def get_yuanta_latest(user_id: str) -> dict:
    """Return the latest daily net_asset snapshot for yuanta from account_snapshots."""
    sql = """
        SELECT acs.snapshot_date, acs.total_value, acs.currency
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE p.name = 'yuanta'
          AND acs.user_id = %s
          AND acs.total_value IS NOT NULL
        ORDER BY acs.snapshot_date DESC, acs.created_at DESC
        LIMIT 1
    """
    with get_conn() as conn:
        row = conn.execute(sql, (user_id,)).fetchone()
    if not row:
        return {}
    return {
        "snapshot_date": row["snapshot_date"],
        "total_value": row["total_value"],
        "currency": row["currency"],
    }


def get_batch_info(batch_id: str) -> dict:
    """Return metadata for a batch."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE id = %s", (batch_id,)
        ).fetchone()
    if not row:
        return {}
    return dict(row)
