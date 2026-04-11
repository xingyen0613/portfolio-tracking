"""
Price fetcher: resolves current USD prices for a list of crypto symbols.
Uses Binance via ccxt as price source.
"""

import os

import ccxt
from dotenv import load_dotenv

from config.settings import ENV_PATH

load_dotenv(ENV_PATH)

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDE"}
FIAT_USD = {"USD"}
QUOTE_CURRENCIES = ["USDT", "USDC", "BTC"]  # fallback order for price lookup


def _get_binance():
    return ccxt.binance({
        "apiKey": os.environ.get("BINANCE_API_KEY", ""),
        "secret": os.environ.get("BINANCE_API_SECRET", ""),
    })


def _get_okx():
    return ccxt.okx({
        "apiKey": os.environ.get("OKX_API_KEY", ""),
        "secret": os.environ.get("OKX_API_SECRET", ""),
        "password": os.environ.get("OKX_PASSPHRASE", ""),
    })


def fetch_prices(symbols: list[str]) -> dict[str, float | None]:
    """
    Fetch USD prices for a list of platform symbols.
    Returns {symbol: price_in_usd} — None if price unavailable.
    """
    prices: dict[str, float | None] = {}

    # Fixed prices
    for s in symbols:
        if s.upper() in STABLECOINS or s.upper() in FIAT_USD:
            prices[s] = 1.0

    # Symbols that need market lookup
    to_fetch = [s for s in symbols if s not in prices]
    if not to_fetch:
        return prices

    def _fetch_from(exchange, syms: list[str]) -> dict[str, float | None]:
        """Try to fetch prices for syms from a given exchange. Returns found prices."""
        found: dict[str, float | None] = {}
        ticker_map = {f"{s}/USDT": s for s in syms}
        try:
            tickers = exchange.fetch_tickers(list(ticker_map.keys()))
            for ccxt_sym, orig_sym in ticker_map.items():
                ticker = tickers.get(ccxt_sym)
                if ticker and ticker.get("last"):
                    found[orig_sym] = float(ticker["last"])
        except Exception:
            for ccxt_sym, orig_sym in ticker_map.items():
                try:
                    ticker = exchange.fetch_ticker(ccxt_sym)
                    if ticker.get("last"):
                        found[orig_sym] = float(ticker["last"])
                except Exception:
                    pass
        return found

    # Round 1: Binance
    binance_prices = _fetch_from(_get_binance(), to_fetch)
    prices.update(binance_prices)

    # Round 2: OKX fallback for symbols not found on Binance
    still_missing = [s for s in to_fetch if s not in prices]
    if still_missing:
        okx_prices = _fetch_from(_get_okx(), still_missing)
        prices.update(okx_prices)

    # Fill any remaining symbols as None
    for s in symbols:
        if s not in prices:
            prices[s] = None

    return prices
