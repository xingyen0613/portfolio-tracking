"""
Financial metrics: return rate, Sharpe ratio, MDD.
"""

import math

import pandas as pd


def compute_metrics(daily_values: pd.Series) -> dict:
    """
    Given a Series of daily total values (indexed by date, sorted ascending),
    return a dict with:
      - total_return: % return over the period
      - sharpe: annualised Sharpe ratio (risk-free = 0)
      - mdd: maximum drawdown (negative %, e.g. -0.15 = -15%)
    Returns None values if insufficient data (<2 points).
    """
    if daily_values is None or len(daily_values) < 2:
        return {"total_return": None, "sharpe": None, "mdd": None}

    vals = daily_values.dropna()
    if len(vals) < 2:
        return {"total_return": None, "sharpe": None, "mdd": None}

    # Total return
    total_return = (vals.iloc[-1] - vals.iloc[0]) / vals.iloc[0]

    # Daily returns
    daily_ret = vals.pct_change().dropna()

    # Sharpe (annualised, risk-free = 0)
    if daily_ret.std() > 0:
        sharpe = (daily_ret.mean() / daily_ret.std()) * math.sqrt(252)
    else:
        sharpe = None

    # MDD
    cummax = vals.cummax()
    drawdown = (vals - cummax) / cummax
    mdd = drawdown.min()

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "mdd": mdd,
    }


def filter_window(df: pd.DataFrame, date_col: str, window: str) -> pd.DataFrame:
    """Filter DataFrame to the selected time window."""
    end = df[date_col].max()
    deltas = {"1W": 7, "1M": 30, "1Q": 90, "1Y": 365}
    days = deltas.get(window, 30)
    start = end - pd.Timedelta(days=days)
    return df[df[date_col] >= start]
