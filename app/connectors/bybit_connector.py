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


class BybitConnector(BaseConnector):
    platform_name = "bybit"

    def authenticate(self) -> None:
        self._exchange = ccxt.bybit({
            "apiKey": os.environ["BYBIT_API_KEY"],
            "secret": os.environ["BYBIT_API_SECRET"],
        })

    def fetch_raw(self) -> list[dict]:
        items = []

        # Unified account balance (covers spot + derivatives in Bybit UTA)
        try:
            balance = self._exchange.fetch_balance({"accountType": "UNIFIED"})
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

        # Funding account — requires dedicated endpoint (fetch_balance doesn't support FUND on UTA)
        try:
            resp = self._exchange.privateGetV5AssetTransferQueryAccountCoinsBalance({
                "accountType": "FUND",
                "coin": "",
            })
            items.append({
                "resource_type": "funding",
                "payload": resp.get("result", {}),
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "funding",
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

            elif resource_type == "funding":
                for row in payload.get("balance", []):
                    symbol = row.get("coin", "")
                    qty = float(row.get("walletBalance", 0))
                    if qty <= 0:
                        continue
                    key = f"{symbol}_funding"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Funding)",
                            "asset_type": _classify(symbol),
                            "quantity": qty,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

        return holdings
