"""
Data access layer for the Streamlit dashboard.
Reads from SQLite and returns aggregated DataFrames.
"""

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
              SELECT id FROM source_runs
              WHERE account_id = a.id AND status = 'success'
              ORDER BY started_at DESC LIMIT 1
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
    Return daily account snapshots aggregated by category.
    For each account+date, only the latest batch's snapshot is used.
    Used for the time series chart.
    """
    sql = """
        SELECT
            p.name          AS platform,
            acs.snapshot_date,
            acs.total_value AS value_usd,
            acs.currency
        FROM account_snapshots acs
        JOIN accounts a  ON acs.account_id = a.id
        JOIN platforms p ON a.platform_id = p.id
        WHERE acs.total_value IS NOT NULL
          AND acs.id = (
              SELECT id FROM account_snapshots
              WHERE account_id = acs.account_id
                AND snapshot_date = acs.snapshot_date
                AND total_value IS NOT NULL
              ORDER BY created_at DESC LIMIT 1
          )
        ORDER BY acs.snapshot_date
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn)

    df["category"] = df["platform"].map(PLATFORM_CATEGORY).fillna("unknown")
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
    return df


def get_batch_info(batch_id: str) -> dict:
    """Return metadata for a batch."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
    if not row:
        return {}
    return dict(row)
