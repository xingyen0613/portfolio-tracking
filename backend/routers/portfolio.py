from typing import Any

import pandas as pd
from fastapi import APIRouter, Query

from app.dashboard.data import get_snapshot_history
from app.dashboard.metrics import compute_metrics

router = APIRouter()

CATEGORIES = ["crypto", "us_stock", "tw_stock"]

WINDOW_DAYS: dict[str, int | None] = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "2Y": 730,
    "all": None,
}


def _build_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot category_snapshots to date-indexed wide DataFrame with forward fill."""
    pivot = df.pivot_table(
        index="snapshot_date", columns="category", values="value_usd", aggfunc="sum"
    )
    for cat in CATEGORIES:
        if cat not in pivot.columns:
            pivot[cat] = 0.0
    date_range = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    pivot = pivot.reindex(date_range).ffill().fillna(0)
    pivot["total"] = pivot[CATEGORIES].sum(axis=1)
    return pivot


@router.get("/history")
def portfolio_history(window: str = Query("3M")) -> dict[str, Any]:
    df = get_snapshot_history()
    pivot = _build_pivot(df)

    days = WINDOW_DAYS.get(window)
    if days is not None:
        start = pivot.index.max() - pd.Timedelta(days=days)
        pivot = pivot[pivot.index >= start]

    keys = ["total"] + CATEGORIES
    dates = pivot.index.strftime("%Y-%m-%d").tolist()
    series = {k: pivot[k].round(2).tolist() for k in keys}
    latest = {k: round(float(pivot[k].iloc[-1]), 2) if not pivot.empty else 0.0 for k in keys}
    metrics = {k: compute_metrics(pivot[k]) for k in keys}

    return {"dates": dates, "series": series, "latest": latest, "metrics": metrics}
