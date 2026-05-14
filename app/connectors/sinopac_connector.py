"""SinoPac (永豐證券) connector via official Shioaji SDK.

Slice 1 範圍：股票帳戶現股部位 (cond=Cash/Netting) + 交割款現金。
融資融券、期貨選擇權留待後續 slice。

Login session 以 api_key 為 key 在 module-level cache，避免同一 batch 內
stock + futopt 兩個 connector instance 重複 login（每日 1000 次 quota）。
"""

import os
import time
from datetime import datetime, timezone

from app.connectors.base import BaseConnector


_SESSION_TTL = 300  # 5 分鐘
_sessions: dict[str, tuple[object, float]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_shioaji_api(api_key: str, secret_key: str, simulation: bool = False):
    """Return a logged-in Shioaji API, cached by api_key for the session TTL.

    Keying by api_key (+ simulation flag) prevents cross-user session
    contamination when daily batch iterates over multiple users.
    """
    cache_key = f"{api_key}:{'sim' if simulation else 'prod'}"
    cached = _sessions.get(cache_key)
    if cached and time.time() - cached[1] < _SESSION_TTL:
        return cached[0]

    import shioaji as sj
    api = sj.Shioaji(simulation=simulation)
    api.login(api_key=api_key, secret_key=secret_key)
    _sessions[cache_key] = (api, time.time())
    return api


def _serialize_position(pos) -> dict:
    """StockPosition / FuturePosition → plain dict for raw_payloads JSON."""
    if hasattr(pos, "model_dump"):
        return pos.model_dump()
    if hasattr(pos, "dict"):
        return pos.dict()
    return {k: getattr(pos, k) for k in dir(pos) if not k.startswith("_")}


class SinopacStockConnector(BaseConnector):
    platform_name = "sinopac"
    account_key = "stock_main"
    use_pricer = False  # shioaji returns last_price directly

    def authenticate(self) -> None:
        api_key = self._credentials.get("api_key") or os.getenv("SINOPAC_API_KEY")
        secret_key = self._credentials.get("secret_key") or os.getenv("SINOPAC_SECRET_KEY")
        if not api_key or not secret_key:
            raise RuntimeError("SINOPAC_API_KEY and SINOPAC_SECRET_KEY must be set")
        simulation = os.getenv("SINOPAC_SIMULATION", "").lower() in ("1", "true")
        self._api = _get_shioaji_api(api_key, secret_key, simulation=simulation)
        if not getattr(self._api, "stock_account", None):
            raise RuntimeError("No stock_account on this Shioaji session — account may not be opened")

    def fetch_raw(self) -> list[dict]:
        import shioaji as sj
        api = self._api
        stock_account = api.stock_account

        # 整股
        positions_common = api.list_positions(stock_account, unit=sj.constant.Unit.Common)
        # 零股
        positions_share = api.list_positions(stock_account, unit=sj.constant.Unit.Share)
        # 交割款餘額
        balance = api.account_balance()

        return [
            {
                "resource_type": "stock_position",
                "payload": {"positions": [_serialize_position(p) for p in positions_common]},
                "fetched_at": _now(),
            },
            {
                "resource_type": "stock_position_odd",
                "payload": {"positions": [_serialize_position(p) for p in positions_share]},
                "fetched_at": _now(),
            },
            {
                "resource_type": "cash_balance",
                "payload": _serialize_position(balance) if balance else {},
                "fetched_at": _now(),
            },
        ]

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings: list[dict] = []

        for item in raw_items:
            rt = item["resource_type"]
            payload = item["payload"]

            if rt in ("stock_position", "stock_position_odd"):
                for pos in payload.get("positions", []):
                    cond = str(pos.get("cond", "")).lower()
                    # Slice 1 只處理現股；融資融券 cond 待 Slice 2
                    if cond and "cash" not in cond and "netting" not in cond:
                        continue

                    qty = float(pos.get("quantity") or 0)
                    last_price = float(pos.get("last_price") or 0)
                    direction = str(pos.get("direction", "")).lower()
                    # 整股 quantity 單位是「張」(1000 股)，零股是「股」
                    multiplier = 1000 if rt == "stock_position" else 1
                    actual_qty = qty * multiplier
                    value = actual_qty * last_price
                    if direction.endswith("sell"):
                        actual_qty = -actual_qty
                        value = -value

                    holdings.append({
                        "platform_symbol": pos.get("code"),
                        "platform_asset_name": pos.get("code"),
                        "asset_type": "stock",
                        "quantity": actual_qty,
                        "price": last_price,
                        "value": value,
                        "original_currency": "TWD",
                        "price_source": "platform",
                        "resource_type": "stock",
                    })

            elif rt == "cash_balance":
                acc_balance = float(payload.get("acc_balance") or 0)
                if acc_balance:
                    holdings.append({
                        "platform_symbol": "TWD",
                        "platform_asset_name": "交割款 (TWD)",
                        "asset_type": "cash",
                        "quantity": acc_balance,
                        "price": 1.0,
                        "value": acc_balance,
                        "original_currency": "TWD",
                        "price_source": "platform",
                        "resource_type": "cash",
                    })

        return holdings
