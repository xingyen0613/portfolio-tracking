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

        # Simple Earn Flexible positions (paginated)
        try:
            all_rows = []
            page = 1
            while True:
                resp = self._exchange.sapiGetSimpleEarnFlexiblePosition({"current": page, "size": 100})
                rows = resp.get("rows", [])
                all_rows.extend(rows)
                if len(all_rows) >= int(resp.get("total", 0)) or not rows:
                    break
                page += 1
            items.append({
                "resource_type": "earn_flexible",
                "payload": {"rows": all_rows, "total": len(all_rows)},
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "earn_flexible",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Simple Earn Locked positions (paginated)
        try:
            all_rows = []
            page = 1
            while True:
                resp = self._exchange.sapiGetSimpleEarnLockedPosition({"current": page, "size": 100})
                rows = resp.get("rows", [])
                all_rows.extend(rows)
                if len(all_rows) >= int(resp.get("total", 0)) or not rows:
                    break
                page += 1
            items.append({
                "resource_type": "earn_locked",
                "payload": {"rows": all_rows, "total": len(all_rows)},
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "earn_locked",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Funding account (資金帳戶) — separate from spot wallet
        try:
            funding = self._exchange.sapiPostAssetGetFundingAsset({})
            items.append({
                "resource_type": "funding",
                "payload": {"assets": funding},
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

            elif resource_type == "funding":
                for row in payload.get("assets", []):
                    symbol = row.get("asset", "")
                    qty = float(row.get("free", 0)) + float(row.get("locked", 0)) + float(row.get("freeze", 0))
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
