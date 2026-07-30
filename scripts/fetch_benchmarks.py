"""
Fetch OHLC data for benchmark tickers and store in benchmark_prices table.
Supports incremental updates — only fetches missing dates.

Usage:
    uv run python scripts/fetch_benchmarks.py
    uv run python scripts/fetch_benchmarks.py --start 2020-01-01
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.db import get_conn

TICKERS = {
    "^GSPC": "S&P 500",
    "^NDX": "納斯達克100",
    "^SOX": "費城半導體",
    "0050.TW": "元大台灣50",
    "BTC-USD": "Bitcoin",
}

DEFAULT_START = "2020-01-01"


def fetch_and_store(ticker: str, start: str, end: str) -> int:
    """Fetch OHLC from yfinance and upsert into benchmark_prices. Returns rows inserted."""
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return 0

    if hasattr(df.columns, 'levels') and df.columns.nlevels > 1:
        df.columns = df.columns.droplevel(1)

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

    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO benchmark_prices (date, ticker, open, high, low, close)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (date, ticker) DO UPDATE SET
                 open=EXCLUDED.open, high=EXCLUDED.high,
                 low=EXCLUDED.low, close=EXCLUDED.close""",
            rows,
        )
    return len(rows)


def get_latest_date(ticker: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM benchmark_prices WHERE ticker = %s", (ticker,)
        ).fetchone()
    return row["max"] if row else None


def main(start: str | None = None):
    end = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    today = date.today().strftime("%Y-%m-%d")

    for ticker, name in TICKERS.items():
        latest = get_latest_date(ticker)
        if latest is not None and not start:
            fetch_start = (date.fromisoformat(latest) + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            fetch_start = start or DEFAULT_START

        if fetch_start > today:
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
