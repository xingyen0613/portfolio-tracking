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
            "apiKey": self._credentials.get("api_key") or os.environ["BINANCE_API_KEY"],
            "secret": self._credentials.get("secret") or os.environ["BINANCE_API_SECRET"],
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

        # Cross margin account (槓桿)
        try:
            margin = self._exchange.sapiGetMarginAccount({})
            items.append({
                "resource_type": "margin_cross",
                "payload": margin,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "margin_cross",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # USD-M futures (U本位永續)
        try:
            f = self._exchange.fapiPrivateV2GetAccount({})
            items.append({
                "resource_type": "futures_um",
                "payload": f,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "futures_um",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Coin-M futures (幣本位永續)
        try:
            f = self._exchange.dapiPrivateGetAccount({})
            items.append({
                "resource_type": "futures_cm",
                "payload": f,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "futures_cm",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Options margin account (期權)
        try:
            o = self._exchange.eapiPrivateGetMarginAccount({})
            items.append({
                "resource_type": "options",
                "payload": o,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "options",
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
                    # Use suffixed key so earn doesn't collide with spot's same
                    # symbol (matching the convention used by earn_locked /
                    # funding below). Without this, e.g. earn USDC 3160 gets
                    # silently dropped if spot also has USDC 0.027.
                    key = f"{symbol}_flexible"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Flexible)",
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

            elif resource_type == "margin_cross":
                # Cross margin: net asset per coin (positive = collateral, negative = borrow)
                for row in payload.get("userAssets", []):
                    symbol = row.get("asset", "")
                    net = float(row.get("netAsset", 0))
                    if net == 0:
                        continue
                    key = f"{symbol}_margin"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Margin)",
                            "asset_type": _classify(symbol),
                            "quantity": net,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

            elif resource_type == "futures_um":
                # USD-M futures wallet balance per asset (mostly USDT)
                for row in payload.get("assets", []):
                    symbol = row.get("asset", "")
                    # walletBalance + unrealizedProfit gives total equity
                    bal = float(row.get("walletBalance", 0)) + float(row.get("unrealizedProfit", 0))
                    if bal == 0:
                        continue
                    key = f"{symbol}_futures_um"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (USD-M Futures)",
                            "asset_type": _classify(symbol),
                            "quantity": bal,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

            elif resource_type == "futures_cm":
                # Coin-M futures wallet balance per coin (BTC, ETH etc.)
                for row in payload.get("assets", []):
                    symbol = row.get("asset", "")
                    bal = float(row.get("walletBalance", 0)) + float(row.get("unrealizedProfit", 0))
                    if bal == 0:
                        continue
                    key = f"{symbol}_futures_cm"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Coin-M Futures)",
                            "asset_type": _classify(symbol),
                            "quantity": bal,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

            elif resource_type == "options":
                # Options margin account: equity per coin
                for row in payload.get("asset", []):
                    symbol = row.get("asset", "")
                    eq = float(row.get("equity", 0))
                    if eq == 0:
                        continue
                    key = f"{symbol}_options"
                    if key not in seen:
                        seen.add(key)
                        holdings.append({
                            "platform_symbol": symbol,
                            "platform_asset_name": f"{symbol} (Options)",
                            "asset_type": _classify(symbol),
                            "quantity": eq,
                            "price": None,
                            "value": None,
                            "original_currency": "USD",
                            "price_source": None,
                        })

        return holdings
