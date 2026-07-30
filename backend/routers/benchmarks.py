from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth.deps import get_current_user
from config.db import get_conn

router = APIRouter()

AVAILABLE_TICKERS = {"^GSPC", "^NDX", "^SOX", "0050.TW", "BTC-USD"}

TICKER_LABELS = {
    "^GSPC": "S&P 500",
    "^NDX": "NASDAQ100",
    "^SOX": "費半",
    "0050.TW": "0050",
    "BTC-USD": "BTC",
}

TICKER_COLORS = {
    "^GSPC": "#a371f7",
    "^NDX": "#58a6ff",
    "^SOX": "#e3b341",
    "0050.TW": "#39d353",
    "BTC-USD": "#f0883e",
}


@router.get("")
def get_benchmarks(
    tickers: str = Query("^GSPC,^NDX,^SOX,0050.TW,BTC-USD"),
    start: str = Query(""),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Return daily close prices for requested benchmark tickers.
    Frontend computes % return normalization.
    """
    requested = [t.strip() for t in tickers.split(",") if t.strip() in AVAILABLE_TICKERS]
    if not requested:
        return {"benchmarks": []}

    results = []
    with get_conn() as conn:
        for ticker in requested:
            sql = "SELECT date, close FROM benchmark_prices WHERE ticker = %s"
            params: list = [ticker]
            if start:
                sql += " AND date >= %s"
                params.append(start)
            sql += " ORDER BY date"
            rows = conn.execute(sql, tuple(params)).fetchall()
            if rows:
                results.append({
                    "ticker": ticker,
                    "label": TICKER_LABELS.get(ticker, ticker),
                    "color": TICKER_COLORS.get(ticker, "#888"),
                    "dates": [r["date"] for r in rows],
                    "closes": [r["close"] for r in rows],
                })

    return {"benchmarks": results}
