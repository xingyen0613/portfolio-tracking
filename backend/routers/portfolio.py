from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.auth.deps import get_current_user
from app.dashboard.data import (
    get_snapshot_history,
    get_latest_category_totals,
    get_latest_snapshot_date,
    get_crypto_symbol_breakdown,
    get_us_stock_symbol_breakdown,
    get_tw_stock_symbol_breakdown,
)
from app.dashboard.metrics import compute_metrics
from app.utils.fx import get_latest_fx_rate
from config.settings import CATEGORY_LABEL

router = APIRouter()

CATEGORIES = ["crypto", "us_stock", "tw_stock"]

WINDOW_DAYS: dict[str, int | None] = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730, "all": None,
}


def _build_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot category_snapshots → date-indexed wide DataFrame with forward fill."""
    if df.empty:
        today = pd.Timestamp.utcnow().normalize()
        pivot = pd.DataFrame(index=[today], columns=CATEGORIES + ["total"], data=0.0)
        return pivot
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
def portfolio_history(
    window: str = Query("3M"),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    df = get_snapshot_history(current_user["id"])
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
def portfolio_allocation(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    cat_df = get_latest_category_totals(current_user["id"])
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
def portfolio_allocation_drilldown(
    category: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    fetchers = {
        "crypto":   lambda: get_crypto_symbol_breakdown(user_id),
        "us_stock": lambda: get_us_stock_symbol_breakdown(user_id),
        "tw_stock": lambda: get_tw_stock_symbol_breakdown(user_id),
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


# ── /api/portfolio/snapshot ───────────────────────────────────────────────────

# Cache breakdown DataFrames for the lifetime of the server process.
# These are historical snapshots — they only grow when a new batch run completes,
# which requires a server restart anyway.
_breakdown_cache: dict[str, "pd.DataFrame"] = {}

def _get_breakdown(category: str, user_id: str) -> "pd.DataFrame":
    cache_key = f"{user_id}:{category}"
    if cache_key not in _breakdown_cache:
        fetcher = {
            "crypto":   lambda: get_crypto_symbol_breakdown(user_id),
            "us_stock": lambda: get_us_stock_symbol_breakdown(user_id),
            "tw_stock": lambda: get_tw_stock_symbol_breakdown(user_id),
        }[category]
        _breakdown_cache[cache_key] = fetcher()
    return _breakdown_cache[cache_key]


@router.get("/snapshot")
def portfolio_snapshot(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Symbol-level breakdown for each category on or before `date`."""
    try:
        target = pd.Timestamp(date)
    except Exception:
        return {"date": date, "categories": {}}

    result: dict[str, Any] = {}
    for category in ("crypto", "us_stock", "tw_stock"):
        df = _get_breakdown(category, current_user["id"])
        if df.empty:
            result[category] = {"actual_date": None, "items": []}
            continue

        avail = df[df["snapshot_date"] <= target]["snapshot_date"]
        if avail.empty:
            result[category] = {"actual_date": None, "items": []}
            continue

        actual = avail.max()
        day_df = df[df["snapshot_date"] == actual].sort_values("value_usd", ascending=False)
        total  = float(day_df["value_usd"].sum())
        items  = [
            {
                "symbol": str(row["symbol"]),
                "pct":    round(float(row["value_usd"]) / total * 100, 1) if total > 0 else 0.0,
            }
            for _, row in day_df.iterrows()
        ]
        result[category] = {
            "actual_date": actual.strftime("%Y-%m-%d"),
            "items":       items,
        }

    return {"date": date, "categories": result}


# ── /api/portfolio/metrics ────────────────────────────────────────────────────

@router.get("/metrics")
def portfolio_metrics(
    window: str = Query("YTD"),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    df = get_snapshot_history(current_user["id"])
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
def portfolio_meta(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    last_updated = get_latest_snapshot_date(current_user["id"])
    return {
        "last_updated": last_updated,
        "usd_twd_rate": get_latest_fx_rate(),
    }
