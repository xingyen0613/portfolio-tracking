from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query

from app.dashboard.data import (
    get_snapshot_history,
    get_latest_category_totals,
    get_latest_snapshot_date,
    get_crypto_symbol_breakdown,
    get_us_stock_symbol_breakdown,
    get_tw_stock_symbol_breakdown,
)
from app.dashboard.metrics import compute_metrics
from config.settings import CATEGORY_LABEL, TWD_PER_USD

router = APIRouter()

CATEGORIES = ["crypto", "us_stock", "tw_stock"]

WINDOW_DAYS: dict[str, int | None] = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730, "all": None,
}


def _build_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot category_snapshots → date-indexed wide DataFrame with forward fill."""
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


# ── /api/portfolio/history ────────────────────────────────────────────────────

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
    series  = {k: pivot[k].round(2).tolist() for k in keys}
    latest  = {k: round(float(pivot[k].iloc[-1]), 2) if not pivot.empty else 0.0 for k in keys}
    metrics = {k: compute_metrics(pivot[k]) for k in keys}

    return {"dates": dates, "series": series, "latest": latest, "metrics": metrics}


# ── /api/portfolio/allocation ─────────────────────────────────────────────────

@router.get("/allocation")
def portfolio_allocation() -> dict[str, Any]:
    cat_df = get_latest_category_totals()
    total = float(cat_df["value_usd"].sum())

    categories = [
        {
            "key": row["category"],
            "label": CATEGORY_LABEL.get(row["category"], row["category"]),
            "value_usd": round(float(row["value_usd"]), 2),
            "pct": round(float(row["value_usd"]) / total * 100, 1) if total > 0 else 0.0,
        }
        for _, row in cat_df.iterrows()
    ]
    categories.sort(key=lambda x: -x["value_usd"])
    return {"total": round(total, 2), "categories": categories}


@router.get("/allocation/{category}")
def portfolio_allocation_drilldown(category: str) -> dict[str, Any]:
    fetchers = {
        "crypto":   get_crypto_symbol_breakdown,
        "us_stock": get_us_stock_symbol_breakdown,
        "tw_stock": get_tw_stock_symbol_breakdown,
    }
    label = CATEGORY_LABEL.get(category, category)

    fetch = fetchers.get(category)
    if fetch is None:
        return {"category": category, "label": label, "items": []}

    df = fetch()
    if df.empty:
        return {"category": category, "label": label, "items": []}

    latest = df["snapshot_date"].max()
    df = df[df["snapshot_date"] == latest]
    df = df.groupby("symbol")["value_usd"].sum().reset_index().sort_values("value_usd", ascending=False)

    total = float(df["value_usd"].sum())
    items = [
        {
            "symbol": row["symbol"],
            "value_usd": round(float(row["value_usd"]), 2),
            "pct": round(float(row["value_usd"]) / total * 100, 1) if total > 0 else 0.0,
        }
        for _, row in df.iterrows()
    ]
    return {"category": category, "label": label, "items": items}


# ── /api/portfolio/metrics ────────────────────────────────────────────────────

@router.get("/metrics")
def portfolio_metrics(window: str = Query("YTD")) -> dict[str, Any]:
    df = get_snapshot_history()
    pivot = _build_pivot(df)

    if window == "YTD":
        start = pd.Timestamp(f"{date.today().year}-01-01")
        pivot = pivot[pivot.index >= start]
    else:
        days = WINDOW_DAYS.get(window)
        if days is not None:
            start = pivot.index.max() - pd.Timedelta(days=days)
            pivot = pivot[pivot.index >= start]

    return {
        k: compute_metrics(pivot[k]) if k in pivot.columns else {}
        for k in ["total"] + CATEGORIES
    }


# ── /api/portfolio/meta ───────────────────────────────────────────────────────

@router.get("/meta")
def portfolio_meta() -> dict[str, Any]:
    last_updated = get_latest_snapshot_date()
    return {
        "last_updated": last_updated,
        "usd_twd_rate": TWD_PER_USD,
    }
