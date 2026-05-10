import os
from datetime import datetime, timezone

import ccxt
from dotenv import load_dotenv

from app.connectors.base import BaseConnector
from config.settings import ENV_PATH

load_dotenv(ENV_PATH)

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"}
FIAT = {"USD", "EUR", "GBP", "TWD"}


def _classify(symbol: str) -> str:
    s = symbol.upper()
    if s in FIAT:
        return "cash"
    if s in STABLECOINS:
        return "stablecoin"
    return "crypto"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MexcConnector(BaseConnector):
    platform_name = "mexc"

    def authenticate(self) -> None:
        self._exchange = ccxt.mexc({
            "apiKey": self._credentials.get("api_key") or os.environ["MEXC_API_KEY"],
            "secret": self._credentials.get("secret") or os.environ["MEXC_API_SECRET"],
        })

    def fetch_raw(self) -> list[dict]:
        items = []

        # Spot balance
        try:
            balance = self._exchange.fetch_balance()
            items.append({
                "resource_type": "spot",
                "payload": balance,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "spot",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Futures/Swap contract account
        try:
            swap_balance = self._exchange.fetch_balance({"type": "swap"})
            items.append({
                "resource_type": "futures",
                "payload": swap_balance,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "futures",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings = []
        seen = set()

        for item in raw_items:
            if item.get("fetch_error"):
                continue

            resource_type = item["resource_type"]
            payload = item["payload"]

            if resource_type == "spot":
                for symbol, qty in payload.get("total", {}).items():
                    qty = float(qty) if qty else 0.0
                    if qty <= 0:
                        continue
                    if symbol not in seen:
                        seen.add(symbol)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": symbol,
                            "asset_type": _classify(symbol),
                            "quantity": qty,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                            "resource_type": resource_type,
                        })

            elif resource_type == "futures":
                for symbol, qty in payload.get("total", {}).items():
                    qty = float(qty) if qty else 0.0
                    if qty <= 0:
                        continue
                    key = f"{symbol}_futures"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Futures)",
                            "asset_type": _classify(symbol),
                            "quantity": qty,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                            "resource_type": resource_type,
                        })

        return holdings
