import os
from datetime import datetime, timezone

import ccxt
from dotenv import load_dotenv

from app.connectors.base import BaseConnector

load_dotenv()

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


class BinanceConnector(BaseConnector):
    platform_name = "binance"

    def authenticate(self) -> None:
        self._exchange = ccxt.binance({
            "apiKey": os.environ["BINANCE_API_KEY"],
            "secret": os.environ["BINANCE_API_SECRET"],
            "options": {"defaultType": "spot"},
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

        # Simple Earn Flexible positions
        try:
            flexible = self._exchange.sapiGetSimpleEarnFlexiblePosition({})
            items.append({
                "resource_type": "earn_flexible",
                "payload": flexible,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "earn_flexible",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Simple Earn Locked positions
        try:
            locked = self._exchange.sapiGetSimpleEarnLockedPosition({})
            items.append({
                "resource_type": "earn_locked",
                "payload": locked,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "earn_locked",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings = []
        seen = set()  # deduplicate by symbol

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
                    # Skip LD* tokens — they are Flexible Earn assets,
                    # we'll use the richer earn_flexible data instead
                    if symbol.startswith("LD"):
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
                        })

            elif resource_type == "earn_flexible":
                for row in payload.get("rows", []):
                    symbol = row["asset"]
                    qty = float(row.get("totalAmount", 0))
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
                        })

            elif resource_type == "earn_locked":
                for row in payload.get("rows", []):
                    symbol = row.get("asset", "")
                    qty = float(row.get("amount", 0))
                    if qty <= 0:
                        continue
                    key = f"{symbol}_locked"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Locked)",
                            "asset_type": _classify(symbol),
                            "quantity": qty,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

        return holdings
