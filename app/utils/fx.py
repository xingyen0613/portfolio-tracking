"""USD/TWD exchange rate utilities.

Fetches historical rates from Yahoo Finance (USDTWD=X) and caches them
in the SQLite fx_rates table. Provides per-date lookups for historical
conversions and a latest-rate getter for current holdings.
"""

import sqlite3
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from config.settings import DB_PATH, TWD_PER_USD

_TICKER = "USDTWD=X"
_DEFAULT_START = "2021-01-01"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_fx_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fx_rates (
                date    TEXT PRIMARY KEY,
                usdtwd  REAL NOT NULL
            )
        """)
        conn.commit()


def refresh_fx_rates(start: str = _DEFAULT_START, end: str | None = None) -> int:
    """Fetch USDTWD rates from Yahoo Finance and upsert into fx_rates table.

    Returns the number of rows inserted/updated.
    """
    ensure_fx_table()
    if end is None:
        end = date.today().isoformat()

    data = yf.download(_TICKER, start=start, end=end, progress=False, auto_adjust=True)
    if data.empty:
        return 0

    close = data["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    rows = [(ts.strftime("%Y-%m-%d"), float(val)) for ts, val in close.items()]

    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO fx_rates (date, usdtwd) VALUES (?, ?)",
            rows,
        )
        conn.commit()

    return len(rows)


def ensure_updated() -> None:
    """Refresh FX rates if today's (or yesterday's) rate is not yet in DB."""
    ensure_fx_table()
    with _conn() as conn:
        row = conn.execute("SELECT MAX(date) FROM fx_rates").fetchone()

    latest = row[0] if row and row[0] else None
    threshold = (date.today() - timedelta(days=1)).isoformat()

    if latest is None or latest < threshold:
        start = latest if latest else _DEFAULT_START
        refresh_fx_rates(start=start)


def get_fx_rates_series() -> pd.Series:
    """Return a date-indexed Series of USD/TWD rates, forward-filled across all days.

    Weekends and public holidays take the most recent preceding trading day's rate.
    Returns an empty Series if the DB table has no data.
    """
    ensure_fx_table()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, usdtwd FROM fx_rates ORDER BY date"
        ).fetchall()

    if not rows:
        return pd.Series(dtype=float)

    dates = pd.to_datetime([r[0] for r in rows])
    rates = [float(r[1]) for r in rows]
    series = pd.Series(rates, index=dates)

    full_range = pd.date_range(series.index.min(), date.today().isoformat(), freq="D")
    return series.reindex(full_range).ffill()


def get_latest_fx_rate() -> float:
    """Return the most recent USD/TWD rate from DB, falling back to settings constant."""
    ensure_fx_table()
    with _conn() as conn:
        row = conn.execute(
            "SELECT usdtwd FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
    return float(row[0]) if row else TWD_PER_USD


def lookup_rate(dt: "pd.Timestamp | str", rates: pd.Series) -> float:
    """Return the USD/TWD rate for a given date using nearest-previous semantics.

    Falls back to TWD_PER_USD if rates is empty or no prior date exists.
    """
    if rates.empty:
        return TWD_PER_USD
    ts = pd.Timestamp(dt)
    val = rates.asof(ts)
    return float(val) if not pd.isna(val) else TWD_PER_USD
