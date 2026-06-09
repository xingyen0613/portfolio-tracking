import hashlib
import hmac
import time
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

STABLECOINS = {"USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDE"}
FIAT = {"USD", "EUR", "GBP", "TWD"}
BASE_URL = "https://api.pionex.com"


def _classify(symbol: str) -> str:
    s = symbol.upper()
    if s in FIAT:
        return "cash"
    if s in STABLECOINS:
        return "stablecoin"
    return "crypto"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sign(method: str, path: str, params: dict, secret: str) -> tuple[str, str]:
    """Return (signature_hex, timestamp_ms_str)."""
    ts = str(int(time.time() * 1000))
    all_params = {**params, "timestamp": ts}
    query_string = "&".join(f"{k}={v}" for k, v in sorted(all_params.items()))
    message = f"{method}{path}?{query_string}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return sig, ts


class PionexConnector(BaseConnector):
    platform_name = "pionex"

    def authenticate(self) -> None:
        self._api_key = self._credentials["api_key"].strip()
        self._secret = self._credentials["secret"].strip()

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        sig, ts = _sign("GET", path, params, self._secret)
        all_params = {**params, "timestamp": ts}
        query_string = "&".join(f"{k}={v}" for k, v in sorted(all_params.items()))
        url = f"{BASE_URL}{path}?{query_string}"
        resp = requests.get(
            url,
            headers={
                "PIONEX-KEY": self._api_key,
                "PIONEX-SIGNATURE": sig,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _fetch_bot_orders(self) -> list[dict]:
        """Fetch all active bot orders (paginated)."""
        results = []
        page_token: str | None = None
        while True:
            params: dict = {"state": "ACTIVE"}
            if page_token:
                params["pageToken"] = page_token
            data = self._get("/api/v1/bot/orders", params)
            if not data.get("result"):
                break
            batch = data.get("data", {}).get("results") or []
            results.extend(batch)
            page_token = data.get("data", {}).get("nextPageToken")
            if not page_token or not batch:
                break
        return results

    def fetch_raw(self) -> list[dict]:
        items = []

        # Spot / trading account balance
        try:
            data = self._get("/api/v1/account/balances")
            items.append({
                "resource_type": "spot",
                "payload": data,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "spot",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Active bot positions (spot_grid, futures_grid, smart_copy)
        try:
            bot_orders = self._fetch_bot_orders()
            items.append({
                "resource_type": "bot",
                "payload": {"orders": bot_orders},
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "bot",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # Full wallet: trading_bot (smart_rebalance), staking, lending, pionex_card
        try:
            data = self._get("/api/v1/wallet/balancesFull")
            items.append({
                "resource_type": "wallet_full",
                "payload": data,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "wallet_full",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings = []
        seen: set[str] = set()

        def _add(symbol: str, qty: float, label: str, resource_type: str) -> None:
            if qty <= 0 or not symbol:
                return
            key = f"{symbol}_{label}"
            if key not in seen:
                seen.add(key)
                holdings.append({
                    "platform_symbol": symbol,
                    "platform_asset_name": f"{symbol} ({label})" if label != symbol else symbol,
                    "asset_type": _classify(symbol),
                    "quantity": qty,
                    "price": None,
                    "value": None,
                    "original_currency": "USD",
                    "price_source": None,
                    "resource_type": resource_type,
                })

        for item in raw_items:
            if item.get("fetch_error"):
                continue

            resource_type = item["resource_type"]
            payload = item["payload"]

            if resource_type == "spot" and payload.get("result"):
                for row in payload.get("data", {}).get("balances", []):
                    symbol = row.get("coin", "")
                    qty = float(row.get("free", 0)) + float(row.get("frozen", 0))
                    _add(symbol, qty, symbol, resource_type)

            elif resource_type == "bot":
                for order in payload.get("orders", []):
                    base = order.get("base", "")
                    quote = order.get("quote", "")
                    order_type = order.get("buOrderType", "")
                    data = order.get("buOrderData") or {}

                    if order_type == "spot_grid":
                        base_amt = float(data.get("baseAmount", 0))
                        quote_amt = float(data.get("quoteAmount", 0))
                        _add(base, base_amt, f"Bot {base}/{quote}", resource_type)
                        _add(quote, quote_amt, f"Bot {base}/{quote} quote", resource_type)

                    elif order_type == "futures_grid":
                        margin = float(data.get("marginBalance", 0))
                        extra = float(data.get("extraBalance", 0))
                        _add(quote, margin + extra, f"Bot Futures {base}/{quote}", resource_type)

                    elif order_type == "smart_copy":
                        quote_amt = float(data.get("currentQuoteAmount", 0))
                        _add(quote, quote_amt, f"Bot SmartCopy {base}/{quote}", resource_type)

                    else:
                        # Unknown bot type — try common amount fields
                        for field in ("baseAmount", "quoteAmount", "currentQuoteAmount"):
                            val = float(data.get(field, 0))
                            coin = base if "base" in field.lower() else quote
                            _add(coin, val, f"Bot {order_type}", resource_type)

            elif resource_type == "wallet_full" and payload.get("result"):
                for section in payload.get("data", {}).get("botAccount", {}).get("detail", []):
                    sec_type = section.get("type", "")
                    sec_list = section.get("list") or []

                    if sec_type == "trading_bot":
                        for bot in sec_list:
                            if bot.get("buOrderType") != "smart_rebalance":
                                continue
                            symbol = bot.get("investmentToken", "")
                            invested = float(bot.get("investmentAmount") or 0)
                            profit = float(bot.get("profit") or 0)
                            qty = invested + profit
                            title = bot.get("title", f"Bot {symbol}")
                            _add(symbol, qty, title, resource_type)

                    elif sec_type in ("staking", "lending"):
                        for pos in sec_list:
                            symbol = pos.get("investmentToken", "")
                            invested = float(pos.get("investmentAmount") or 0)
                            profit = float(pos.get("profit") or 0)
                            qty = invested + profit
                            title = pos.get("title", symbol)
                            _add(symbol, qty, title, resource_type)

                    elif sec_type == "pionex_card":
                        for pos in sec_list:
                            symbol = pos.get("investmentToken", "")
                            qty = float(pos.get("investmentAmount") or 0)
                            _add(symbol, qty, "Pionex Card", resource_type)

        return holdings
