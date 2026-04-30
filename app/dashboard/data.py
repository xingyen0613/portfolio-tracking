"""
Data access layer for the Streamlit dashboard.
Reads from SQLite and returns aggregated DataFrames.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config.settings import DB_PATH, PLATFORM_CATEGORY, TWD_PER_USD


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_snapshot_date() -> str | None:
    """Return the most recent snapshot date that has holdings."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) AS d FROM normalized_holdings"
        ).fetchone()
    return row["d"] if row else None


def get_holdings() -> pd.DataFrame:
    """
    Return the latest holdings per account.
    For each account, picks the most recent successful source_run
    regardless of date or batch, so all platforms are always shown
    even if they were last fetched on different days.
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
            sr.id         AS source_run_id,
            sr.started_at AS fetched_at
        FROM normalized_holdings nh
        JOIN source_runs sr ON nh.source_run_id = sr.id
        JOIN accounts a     ON sr.account_id = a.id
        JOIN platforms p    ON a.platform_id = p.id
        WHERE sr.status = 'success'
          AND sr.id IN (
              SELECT sr2.id FROM source_runs sr2
              WHERE sr2.account_id = a.id AND sr2.status = 'success'
                AND EXISTS (
                    SELECT 1 FROM normalized_holdings WHERE source_run_id = sr2.id
                )
              ORDER BY sr2.started_at DESC LIMIT 1
          )
        ORDER BY p.name, a.account_key, nh.value DESC NULLS LAST
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)

    df["category"] = df["platform"].map(PLATFORM_CATEGORY).fillna("unknown")
    df["value_usd"] = pd.to_numeric(df["value"], errors="coerce")
    df["value_twd"] = df["value_usd"] * TWD_PER_USD
    return df


def get_snapshot_history() -> pd.DataFrame:
    """
    Return category-level daily totals from category_snapshots (materialized layer).
    Used for the time series chart.
    """
    sql = """
        SELECT snapshot_date, category, total_value, currency, source
        FROM category_snapshots
        ORDER BY snapshot_date, category
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")
    df["value_usd"] = df.apply(
        lambda r: r["total_value"] / TWD_PER_USD if r["currency"] == "TWD" else r["total_value"],
        axis=1,
    )
    return df


def get_crypto_platform_daily() -> pd.DataFrame:
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
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_crypto_symbol_breakdown() -> pd.DataFrame:
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
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_us_stock_platform_daily() -> pd.DataFrame:
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
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_us_stock_symbol_breakdown() -> pd.DataFrame:
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
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_tw_stock_symbol_breakdown() -> pd.DataFrame:
    """
    Return per-date per-stock breakdown for tw_stock (yuanta).
    Source: daily_net_asset.json holdings_value (TWD per symbol).
    Only includes trading days where holdings_value is non-empty.
    """
    project_root = Path(DB_PATH).parent.parent.parent
    derived_dir = project_root / "data" / "derived" / "yuanta_poc"

    rows = []
    for na_file in sorted(derived_dir.glob("*/daily_net_asset.json")):
        with open(na_file, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("daily", []):
            hv = entry.get("holdings_value")
            if not hv:
                continue
            date_str = entry["date"]
            for symbol, value_str in hv.items():
                rows.append({
                    "snapshot_date": date_str,
                    "symbol": symbol,
                    "value_usd": float(value_str) / TWD_PER_USD,
                })

    if not rows:
        return pd.DataFrame(columns=["snapshot_date", "symbol", "value_usd"])

    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df.sort_values(["snapshot_date", "value_usd"], ascending=[True, False])


def get_tw_stock_platform_daily() -> pd.DataFrame:
    """Per-date per-platform totals for tw_stock (yuanta, extensible). Used for hover breakdown."""
    sql = """
        SELECT
            p.name          AS platform,
            acs.snapshot_date,
            SUM(acs.total_value) / :rate AS value_usd
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.total_value IS NOT NULL
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
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params={"rate": TWD_PER_USD})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_platform_latest_account_snapshot() -> dict[str, dict]:
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
        WHERE acs.id = (
            SELECT id FROM account_snapshots
            WHERE account_id = acs.account_id
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
        )
    """
    with _conn() as conn:
        rows = conn.execute(sql).fetchall()
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


def get_latest_category_totals() -> pd.DataFrame:
    """
    Return the latest total value per category from category_snapshots.
    Used for the pie chart so all categories (crypto/tw_stock/us_stock) appear
    even if they don't have normalized_holdings (no connector yet).
    """
    sql = """
        SELECT category, total_value, currency
        FROM category_snapshots
        WHERE (category, snapshot_date) IN (
            SELECT category, MAX(snapshot_date)
            FROM category_snapshots
            GROUP BY category
        )
          AND total_value > 0
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")
    df["value_usd"] = df.apply(
        lambda r: r["total_value"] / TWD_PER_USD if r["currency"] == "TWD" else r["total_value"],
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
    project_root = Path(DB_PATH).parent.parent.parent
    derived_dir = project_root / "data" / "derived" / "yuanta_poc"
    raw_dir = project_root / "data" / "raw" / "yuanta_poc"

    # Find latest month with daily_net_asset.json
    months = sorted(
        [p.parent.name for p in derived_dir.glob("*/daily_net_asset.json")],
        reverse=True,
    )
    if not months:
        return {}

    latest_month = months[0]

    # Latest non-null entry from daily_net_asset.json
    with open(derived_dir / latest_month / "daily_net_asset.json", encoding="utf-8") as f:
        na_data = json.load(f)
    latest_entry = next(
        (e for e in reversed(na_data["daily"]) if e.get("net_asset") is not None),
        None,
    )
    if not latest_entry:
        return {}

    holdings_value = {k: float(v) for k, v in (latest_entry.get("holdings_value") or {}).items()}

    # Name→symbol cache (for pledged holdings that have no symbol in PDF)
    cache_path = derived_dir / "name_to_symbol_cache.json"
    name_to_sym: dict[str, str] = {}
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            name_to_sym = json.load(f)

    # parsed.json — owned vs pledged distinction (end-of-month snapshot)
    owned: list[dict] = []
    pledged: list[dict] = []
    parsed_path = raw_dir / latest_month / "parsed.json"
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

    summary = parsed.get("summary", {}) if parsed_path.exists() else {}
    return {
        "date": latest_entry["date"],
        "month": latest_month,
        "market_value": float(latest_entry.get("market_value") or 0),
        "margin_balance": float(latest_entry.get("margin_balance") or 0),
        "net_asset": float(latest_entry.get("net_asset") or 0),
        "margin_maintenance_pct": summary.get("margin_maintenance_pct"),
        "owned": owned,
        "pledged": pledged,
    }


def get_yuanta_latest() -> dict:
    """Return the latest daily net_asset snapshot for yuanta from account_snapshots."""
    sql = """
        SELECT acs.snapshot_date, acs.total_value, acs.currency
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE p.name = 'yuanta'
          AND acs.total_value IS NOT NULL
        ORDER BY acs.snapshot_date DESC, acs.created_at DESC
        LIMIT 1
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    if not row:
        return {}
    return {"snapshot_date": row[0], "total_value": row[1], "currency": row[2]}


def get_batch_info(batch_id: str) -> dict:
    """Return metadata for a batch."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
    if not row:
        return {}
    return dict(row)
