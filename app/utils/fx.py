"""USD/TWD exchange rate utilities.

Fetches historical rates from Yahoo Finance (USDTWD=X) and caches them
in the fx_rates table. Provides per-date lookups for historical
conversions and a latest-rate getter for current holdings.
"""

from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from config.db import get_conn
from config.settings import TWD_PER_USD

_TICKER = "USDTWD=X"
_DEFAULT_START = "2021-01-01"


def ensure_fx_table() -> None:
    pass  # DDL managed by Alembic


def refresh_fx_rates(start: str = _DEFAULT_START, end: str | None = None) -> int:
    """Fetch USDTWD rates from Yahoo Finance and upsert into fx_rates table.

    Returns the number of rows inserted/updated.
    """
    if end is None:
        end = date.today().isoformat()

    data = yf.download(_TICKER, start=start, end=end, progress=False, auto_adjust=True)
    if data.empty:
        return 0

    close = data["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    rows = [(ts.strftime("%Y-%m-%d"), float(val)) for ts, val in close.items()]

    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO fx_rates (date, usdtwd) VALUES (%s, %s) ON CONFLICT (date) DO UPDATE SET usdtwd=EXCLUDED.usdtwd",
            rows,
        )

    return len(rows)


def ensure_updated() -> None:
    """Refresh FX rates if today's (or yesterday's) rate is not yet in DB."""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(date) FROM fx_rates").fetchone()

    latest = row["max"] if row and row["max"] else None
    threshold = (date.today() - timedelta(days=1)).isoformat()

    if latest is None or latest < threshold:
        start = latest if latest else _DEFAULT_START
        refresh_fx_rates(start=start)


def get_fx_rates_series() -> pd.Series:
    """Return a date-indexed Series of USD/TWD rates, forward-filled across all days.

    Weekends and public holidays take the most recent preceding trading day's rate.
    Returns an empty Series if the DB table has no data.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, usdtwd FROM fx_rates ORDER BY date"
        ).fetchall()

    if not rows:
        return pd.Series(dtype=float)

    dates = pd.to_datetime([r["date"] for r in rows])
    rates = [float(r["usdtwd"]) for r in rows]
    series = pd.Series(rates, index=dates)

    full_range = pd.date_range(series.index.min(), date.today().isoformat(), freq="D")
    return series.reindex(full_range).ffill()


def get_latest_fx_rate() -> float:
    """Return the most recent USD/TWD rate from DB, falling back to settings constant."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT usdtwd FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
    return float(row["usdtwd"]) if row else TWD_PER_USD


def lookup_rate(dt: "pd.Timestamp | str", rates: pd.Series) -> float:
    """Return the USD/TWD rate for a given date using nearest-previous semantics.

    Falls back to TWD_PER_USD if rates is empty or no prior date exists.
    """
    if rates.empty:
        return TWD_PER_USD
    ts = pd.Timestamp(dt)
    val = rates.asof(ts)
    return float(val) if not pd.isna(val) else TWD_PER_USD
