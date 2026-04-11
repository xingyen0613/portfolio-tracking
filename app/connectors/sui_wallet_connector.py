"""
SUI on-chain wallet connector using BlockVision API.
One instance per wallet address.
"""

import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from app.connectors.base import BaseConnector
from config.settings import ENV_PATH, SUI_DEFI_PROTOCOLS

load_dotenv(ENV_PATH)

BASE_URL = "https://api.blockvision.org/v2/sui"

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "BUCK", "USDE", "FDUSD"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(symbol: str) -> str:
    s = symbol.upper()
    if s in STABLECOINS:
        return "stablecoin"
    return "crypto"


class SuiWalletConnector(BaseConnector):
    platform_name = "sui_wallet"

    def __init__(self, wallet_address: str):
        self.wallet_address = wallet_address
        # account_key = first 10 chars of address (0x + 8 chars)
        self.account_key = wallet_address[:10] if len(wallet_address) >= 10 else wallet_address

    def authenticate(self) -> None:
        api_key = os.environ["BLOCKVISION_API_KEY"]
        self._headers = {
            "x-api-key": api_key,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict) -> dict:
        resp = requests.get(
            f"{BASE_URL}{path}",
            headers=self._headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (200, None) and data.get("code") != 0:
            raise ValueError(f"BlockVision error {data.get('code')}: {data.get('message')}")
        return data

    def fetch_raw(self) -> list[dict]:
        items = []

        # Token balances
        try:
            data = self._get("/account/coins", {"account": self.wallet_address})
            items.append({
                "resource_type": "tokens",
                "payload": data,
                "fetched_at": _now(),
            })
        except Exception as e:
            items.append({
                "resource_type": "tokens",
                "payload": {"error": str(e)},
                "fetched_at": _now(),
                "fetch_error": str(e),
            })

        # DeFi positions — one call per protocol
        for protocol in SUI_DEFI_PROTOCOLS:
            try:
                data = self._get("/account/defiPortfolio", {
                    "address": self.wallet_address,
                    "protocol": protocol,
                })
                items.append({
                    "resource_type": f"defi_{protocol}",
                    "payload": data,
                    "fetched_at": _now(),
                })
            except Exception as e:
                items.append({
                    "resource_type": f"defi_{protocol}",
                    "payload": {"error": str(e)},
                    "fetched_at": _now(),
                    "fetch_error": str(e),
                })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings = []

        for item in raw_items:
            if item.get("fetch_error"):
                continue

            resource_type = item["resource_type"]
            payload = item["payload"]
            result = payload.get("result", {})

            if resource_type == "tokens":
                coins = result.get("coins", [])
                for coin in coins:
                    symbol = coin.get("symbol", "UNKNOWN")
                    decimals = int(coin.get("decimals", 9))
                    raw_balance = int(coin.get("balance", "0"))
                    quantity = raw_balance / (10 ** decimals)
                    if quantity <= 0:
                        continue

                    usd_value_str = coin.get("usdValue", "")
                    usd_value = float(usd_value_str) if usd_value_str else None
                    price = (usd_value / quantity) if (usd_value and quantity > 0) else None

                    holdings.append({
                        "platform_symbol": symbol,
                        "platform_asset_name": coin.get("name", symbol),
                        "asset_type": _classify(symbol),
                        "quantity": quantity,
                        "price": price,
                        "value": usd_value,
                        "original_currency": "USD",
                        "price_source": "blockvision" if usd_value else None,
                    })

            elif resource_type.startswith("defi_"):
                protocol = resource_type[5:]  # strip "defi_"
                # BlockVision DeFi response structure varies by protocol
                # Result is a dict keyed by protocol name, containing a list of positions
                positions = []
                if isinstance(result, dict):
                    for key, val in result.items():
                        if isinstance(val, list):
                            positions.extend(val)
                        elif isinstance(val, dict):
                            positions.append(val)
                elif isinstance(result, list):
                    positions = result

                for pos in positions:
                    symbol = pos.get("symbol") or pos.get("coinType", "").split("::")[-1]
                    if not symbol:
                        continue
                    decimals = int(pos.get("decimals", 9))
                    raw_balance = pos.get("balance", "0")
                    try:
                        quantity = int(raw_balance) / (10 ** decimals)
                    except (ValueError, TypeError):
                        try:
                            quantity = float(raw_balance)
                        except (ValueError, TypeError):
                            continue

                    if quantity <= 0:
                        continue

                    pos_type = pos.get("type", "")  # Supply, Borrow, Staked, etc.
                    holdings.append({
                        "platform_symbol": symbol,
                        "platform_asset_name": f"{symbol} ({protocol} {pos_type})".strip(),
                        "asset_type": _classify(symbol),
                        "quantity": quantity,
                        "price": None,
                        "value": None,
                        "original_currency": "USD",
                        "price_source": None,
                    })

        return holdings
