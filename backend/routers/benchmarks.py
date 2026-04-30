import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sqlite" / "portfolio.db"

AVAILABLE_TICKERS = {"^GSPC", "0050.TW", "BTC-USD"}

TICKER_LABELS = {
    "^GSPC": "S&P 500",
    "0050.TW": "0050",
    "BTC-USD": "BTC",
}

TICKER_COLORS = {
    "^GSPC": "#a371f7",
    "0050.TW": "#39d353",
    "BTC-USD": "#f0883e",
}


@router.get("")
def get_benchmarks(
    tickers: str = Query("^GSPC,0050.TW,BTC-USD"),
    start: str = Query(""),
) -> dict[str, Any]:
    """
    Return daily close prices for requested benchmark tickers.
    Frontend computes % return normalization.
    """
    requested = [t.strip() for t in tickers.split(",") if t.strip() in AVAILABLE_TICKERS]
    if not requested:
        return {"benchmarks": []}

    results = []
    with sqlite3.connect(DB_PATH) as conn:
        for ticker in requested:
            sql = "SELECT date, close FROM benchmark_prices WHERE ticker = ?"
            params: list = [ticker]
            if start:
                sql += " AND date >= ?"
                params.append(start)
            sql += " ORDER BY date"
            rows = conn.execute(sql, params).fetchall()
            if rows:
                results.append({
                    "ticker": ticker,
                    "label": TICKER_LABELS.get(ticker, ticker),
                    "color": TICKER_COLORS.get(ticker, "#888"),
                    "dates": [r[0] for r in rows],
                    "closes": [r[1] for r in rows],
                })

    return {"benchmarks": results}
