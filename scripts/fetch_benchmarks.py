"""
Fetch OHLC data for benchmark tickers and store in benchmark_prices table.
Supports incremental updates — only fetches missing dates.

Usage:
    uv run python scripts/fetch_benchmarks.py
    uv run python scripts/fetch_benchmarks.py --start 2020-01-01
"""

import argparse
import sqlite3
from datetime import date, timedelta

from pathlib import Path

import yfinance as yf

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sqlite" / "portfolio.db"

TICKERS = {
    "^GSPC": "S&P 500",
    "0050.TW": "元大台灣50",
    "BTC-USD": "Bitcoin",
}

DEFAULT_START = "2020-01-01"


def fetch_and_store(ticker: str, start: str, end: str) -> int:
    """Fetch OHLC from yfinance and upsert into benchmark_prices. Returns rows inserted."""
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return 0

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, type(df.columns)) and hasattr(df.columns, 'levels'):
        df.columns = df.columns.droplevel(1) if df.columns.nlevels > 1 else df.columns

    rows = []
    for dt, row in df.iterrows():
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10]
        rows.append((
            date_str,
            ticker,
            float(row.get("Open", row.get("open", 0)) or 0),
            float(row.get("High", row.get("high", 0)) or 0),
            float(row.get("Low", row.get("low", 0)) or 0),
            float(row.get("Close", row.get("close", 0)) or 0),
        ))

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO benchmark_prices (date, ticker, open, high, low, close) VALUES (?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def get_latest_date(ticker: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM benchmark_prices WHERE ticker = ?", (ticker,)
        ).fetchone()
    return row[0] if row else None


def main(start: str | None = None):
    end = date.today().strftime("%Y-%m-%d")

    for ticker, name in TICKERS.items():
        latest = get_latest_date(ticker)
        if latest is not None and not start:
            # Incremental: start from day after latest stored date
            fetch_start = (date.fromisoformat(latest) + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            fetch_start = start or DEFAULT_START

        if fetch_start >= end:
            print(f"  {name} ({ticker}): already up to date ({latest})")
            continue

        print(f"  {name} ({ticker}): fetching {fetch_start} → {end} ...", end=" ", flush=True)
        n = fetch_and_store(ticker, fetch_start, end)
        print(f"{n} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None, help="Override start date (YYYY-MM-DD)")
    args = parser.parse_args()
    main(args.start)
