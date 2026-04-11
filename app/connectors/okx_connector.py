import os
from datetime import datetime, timezone

import ccxt
from dotenv import load_dotenv

from app.connectors.base import BaseConnector
from config.settings import ENV_PATH

load_dotenv(ENV_PATH)

STABLECOINS = {"USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDE"}
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


class OKXConnector(BaseConnector):
    platform_name = "okx"

    def authenticate(self) -> None:
        self._exchange = ccxt.okx({
            "apiKey": os.environ["OKX_API_KEY"],
            "secret": os.environ["OKX_API_SECRET"],
            "password": os.environ["OKX_PASSPHRASE"],
        })

    def fetch_raw(self) -> list[dict]:
        items = []

        # Spot/Trading balance
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

        # Savings balance
        try:
            savings = self._exchange.privateGetFinanceSavingsBalance({})
            items.append({
                "resource_type": "savings",
                "payload": savings,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "savings",
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
                        })

            elif resource_type == "savings":
                for row in payload.get("data", []):
                    symbol = row["ccy"]
                    qty = float(row.get("amt", 0))
                    if qty <= 0:
                        continue
                    # Savings assets are separate from spot; add them in
                    key = f"{symbol}_savings"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Savings)",
                            "asset_type": _classify(symbol),
                            "quantity": qty,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

        return holdings
