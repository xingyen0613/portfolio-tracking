"""
Shared price cache backed by the price_cache DB table.

Schema: (symbol, price_date) PRIMARY KEY — one price per symbol per calendar date.
This avoids duplicate API calls across users and batch runs for the same symbol+date.

Usage:
  cached = get_cached_prices(["BTC", "ETH"], "2026-06-14")
  missing = [s for s in symbols if cached.get(s) is None]
  if missing:
      fetched = fetch_prices(missing)
      save_prices(fetched, "2026-06-14", source="market")
"""

import logging
from datetime import datetime, timezone

from config.db import get_conn

logger = logging.getLogger(__name__)


def get_cached_prices(symbols: list[str], price_date: str) -> dict[str, float | None]:
    """
    Read prices from the DB cache for given symbols on price_date (YYYY-MM-DD).
    Returns {symbol: price} — None for symbols not in cache.
    """
    if not symbols:
        return {}

    result: dict[str, float | None] = {s: None for s in symbols}

    with get_conn() as conn:
        placeholders = ",".join(["%s"] * len(symbols))
        rows = conn.execute(
            f"SELECT symbol, price FROM price_cache WHERE symbol IN ({placeholders}) AND price_date = %s",
            (*symbols, price_date),
        ).fetchall()

    hits = 0
    for row in rows:
        result[row["symbol"]] = float(row["price"])
        hits += 1

    logger.info("[price_cache] %d/%d cache hits for %s", hits, len(symbols), price_date)
    return result


def save_prices(
    prices: dict[str, float],
    price_date: str,
    source: str,
    currency: str = "USD",
) -> None:
    """
    Upsert prices into the cache. Existing entries for (symbol, price_date) are updated.
    prices: {symbol: price_in_native_currency}
    """
    if not prices:
        return

    with get_conn() as conn:
        for symbol, price in prices.items():
            conn.execute(
                """INSERT INTO price_cache (symbol, price_date, price, currency, source, fetched_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (symbol, price_date) DO UPDATE SET
                     price      = EXCLUDED.price,
                     source     = EXCLUDED.source,
                     fetched_at = NOW()""",
                (symbol, price_date, price, currency, source),
            )

    logger.info("[price_cache] saved %d prices for %s (source=%s, currency=%s)",
                len(prices), price_date, source, currency)


def get_month_prices(month: str, symbols: list[str]) -> dict[str, dict[str, float]]:
    """
    Read all cached prices for given symbols within a month (YYYY-MM).
    Returns {date_str: {symbol: price}}.
    Useful for yuanta / Yahoo Finance path — avoid re-fetching a full month already in cache.
    """
    if not symbols:
        return {}

    year, mon = int(month[:4]), int(month[5:7])
    first_day = f"{year:04d}-{mon:02d}-01"
    if mon == 12:
        last_day = f"{year + 1:04d}-01-01"
    else:
        last_day = f"{year:04d}-{mon + 1:02d}-01"

    placeholders = ",".join(["%s"] * len(symbols))
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT symbol, price_date::text AS price_date, price
                FROM price_cache
                WHERE symbol IN ({placeholders})
                  AND price_date >= %s
                  AND price_date < %s""",
            (*symbols, first_day, last_day),
        ).fetchall()

    result: dict[str, dict[str, float]] = {}
    for row in rows:
        date_str = str(row["price_date"])
        if date_str not in result:
            result[date_str] = {}
        result[date_str][row["symbol"]] = float(row["price"])

    return result


# ---------------------------------------------------------------------------
# Historical price lookup (for test / backfill scenarios)
# ---------------------------------------------------------------------------

def _yfinance_ticker_for(symbol: str) -> str | None:
    """Map internal symbol to a Yahoo Finance ticker string."""
    # Crypto: ETH → ETH-USD
    CRYPTO = {
        "BTC", "ETH", "SOL", "BNB", "AVAX", "MATIC", "DOT", "ADA", "LINK",
        "UNI", "ATOM", "NEAR", "FTM", "OP", "ARB", "SUI", "APT", "INJ",
        "TIA", "DYDX", "SEI", "PEPE", "WLD", "PYTH", "JTO", "JUP", "W",
    }
    if symbol.upper() in CRYPTO:
        return f"{symbol.upper()}-USD"

    # Taiwan stocks: 0050 → 0050.TW (try .TW first, then .TWO handled by caller)
    if symbol.isdigit() or (len(symbol) == 4 and symbol[:-1].isdigit()):
        return f"{symbol}.TW"

    # US stocks / ETFs: TSLA, QQQ, SPY, etc.
    return symbol.upper()


def fetch_historical_price(
    symbol: str,
    price_date: str,
    currency: str = "USD",
) -> float | None:
    """
    Fetch a historical price for symbol on price_date (YYYY-MM-DD) using yfinance.
    Checks the DB cache first; fetches from API on miss and saves to cache.
    Returns price or None if unavailable.
    """
    cached = get_cached_prices([symbol], price_date)
    if cached.get(symbol) is not None:
        logger.info("[price_cache] historical hit: %s on %s = %s", symbol, price_date, cached[symbol])
        return cached[symbol]

    ticker_str = _yfinance_ticker_for(symbol)
    if not ticker_str:
        logger.warning("[price_cache] no Yahoo Finance ticker for symbol: %s", symbol)
        return None

    # Try .TW, then .TWO for Taiwan stocks
    tickers_to_try = [ticker_str]
    if ticker_str.endswith(".TW"):
        tickers_to_try.append(ticker_str[:-3] + ".TWO")

    import yfinance as yf
    from datetime import timedelta

    dt = datetime.strptime(price_date, "%Y-%m-%d")
    start = price_date
    # End = next trading day (yfinance end is exclusive)
    end = (dt + timedelta(days=5)).strftime("%Y-%m-%d")

    for ticker_id in tickers_to_try:
        try:
            data = yf.download(ticker_id, start=start, end=end, auto_adjust=True, progress=False)
            if data.empty:
                continue
            # Normalize MultiIndex columns (yfinance >= 0.2.38 may return (Price, Ticker) columns)
            if hasattr(data.columns, "levels"):
                data.columns = data.columns.get_level_values(0)
            if "Close" not in data.columns:
                continue
            # Strip timezone from DatetimeIndex
            if hasattr(data.index, "tz") and data.index.tz is not None:
                data.index = data.index.tz_localize(None)
            # Find the row for the target date or nearest next trading day
            relevant = data[data.index.strftime("%Y-%m-%d") == price_date]
            if relevant.empty:
                relevant = data.iloc[[0]]  # first available trading day in range
            raw_val = relevant["Close"].iloc[0]
            # Handle numpy scalar, pandas Series, or plain float
            price = float(raw_val) if not hasattr(raw_val, "__len__") else float(raw_val.iloc[0])
            actual_date = relevant.index[0].strftime("%Y-%m-%d")
            source = f"yfinance:{ticker_id}"
            save_prices({symbol: price}, actual_date, source, currency=currency)
            # For non-trading days (weekends/holidays), also cache under the requested date
            if actual_date != price_date:
                save_prices({symbol: price}, price_date, source=f"alias:{ticker_id}", currency=currency)
                logger.info("[price_cache] non-trading day alias: %s → %s", price_date, actual_date)
            logger.info("[price_cache] fetched %s on %s = %.4f (%s)", symbol, actual_date, price, ticker_id)
            return price
        except Exception as e:
            logger.warning("[price_cache] yfinance fetch failed for %s: %s", ticker_id, e)
            continue

    logger.warning("[price_cache] could not fetch price for %s on %s", symbol, price_date)
    return None
