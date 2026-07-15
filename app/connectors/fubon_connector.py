"""Fubon (富邦證券) connector via official fubon-neo SDK.

範圍：證券帳戶現股（order_type=Stock，整股 + 零股 odd 相加）+ 銀行存款餘額。
融資融券（Margin/Short）、期貨帳戶留待後續——見 docs/fubon-api-poc.md。

認證走 apikey_login（唯讀 API Key + 電子交易憑證 .pfx），電子平台密碼不進系統。
憑證以 base64 存在 credentials（cert_pfx_b64），登入時落地暫存檔、用畢即刪。

定價：unrealized_gains_and_loses 反推市值（cost×qty + 未實現損益），不需外部查價；
反推不到的 symbol 查共用 price_cache（永豐 batch 先跑會回存 TWD 價格）。
"""

import base64
import os
import tempfile
from datetime import date, datetime, timezone

from app.connectors.base import BaseConnector


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(obj, depth: int = 0) -> dict:
    """fubon_neo 回傳 pyo3 原生物件（無 __dict__/model_dump），用 dir()+getattr 取值。"""
    out = {}
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except Exception:
            continue
        if callable(v):
            continue
        out[k] = _plain(v, depth)
    return out if out else {"value": str(obj)}


def _plain(v, depth: int = 0):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x, depth + 1) for x in v]
    # pyo3 enum（如 OrderType.Stock）：str 以型別名開頭，存字串避免 dir() 展開變體造成遞迴
    if str(v).startswith(type(v).__name__ + "."):
        return str(v)
    if depth < 3:
        return _to_dict(v, depth + 1)
    return str(v)


def _is_stock_type(order_type) -> bool:
    """order_type enum: Stock / Margin / Short / DayTrade / SBL（序列化後可能是
    'Stock' 或 'OrderType.Stock'），只收現股。"""
    return str(order_type).split(".")[-1].lower() == "stock"


class FubonConnector(BaseConnector):
    platform_name = "fubon"
    account_key = "stock_main"
    use_pricer = False  # 價格由 unrealized 反推 / price_cache，pipeline 會把 platform 價格回存 cache

    def authenticate(self) -> None:
        fubon_id = self._credentials.get("fubon_id") or os.getenv("FUBON_ID")
        api_key = self._credentials.get("api_key") or os.getenv("FUBON_API_KEY")
        cert_b64 = self._credentials.get("cert_pfx_b64")
        cert_pwd = self._credentials.get("cert_password") or fubon_id  # 憑證預設密碼 = 身分證號

        if not fubon_id or not api_key:
            raise RuntimeError("fubon credentials require fubon_id and api_key")

        # 憑證來源：credentials base64（正式路徑）或本機檔案路徑（開發用 FUBON_CERT_PATH）
        cert_path = None
        tmp_path = None
        if cert_b64:
            fd, tmp_path = tempfile.mkstemp(suffix=".pfx")
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(cert_b64))
            cert_path = tmp_path
        else:
            cert_path = os.getenv("FUBON_CERT_PATH")
        if not cert_path or not os.path.exists(cert_path):
            raise RuntimeError("fubon certificate missing (cert_pfx_b64 or FUBON_CERT_PATH)")

        from fubon_neo.sdk import FubonSDK

        sdk = FubonSDK()
        try:
            print("  [fubon] apikey_login start")
            res = sdk.apikey_login(fubon_id, api_key, cert_path, cert_pwd)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if not getattr(res, "is_success", False):
            raise RuntimeError(f"fubon login failed: {getattr(res, 'message', 'unknown error')}")
        accounts = res.data or []
        print(f"  [fubon] login ok, {len(accounts)} account(s)")
        if not accounts:
            raise RuntimeError("fubon login returned no accounts")
        self._sdk = sdk
        self._accounts = accounts

    def fetch_raw(self) -> list[dict]:
        sdk = self._sdk
        items: list[dict] = []
        try:
            for acc in self._accounts:
                acc_no = getattr(acc, "account", "?")
                inv = sdk.accounting.inventories(acc)
                if not getattr(inv, "is_success", False):
                    raise RuntimeError(f"inventories failed ({acc_no}): {getattr(inv, 'message', '?')}")
                unreal = sdk.accounting.unrealized_gains_and_loses(acc)
                if not getattr(unreal, "is_success", False):
                    raise RuntimeError(f"unrealized failed ({acc_no}): {getattr(unreal, 'message', '?')}")
                cash = sdk.accounting.bank_remain(acc)
                if not getattr(cash, "is_success", False):
                    raise RuntimeError(f"bank_remain failed ({acc_no}): {getattr(cash, 'message', '?')}")

                items.append({
                    "resource_type": "fubon_account",
                    "payload": {
                        "account": _to_dict(acc),
                        "inventories": [_to_dict(x) for x in (inv.data or [])],
                        "unrealized": [_to_dict(x) for x in (unreal.data or [])],
                        "bank_remain": _to_dict(cash.data) if cash.data is not None else {},
                    },
                    "fetched_at": _now(),
                })
        finally:
            try:
                sdk.logout()
            except Exception:
                pass
        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        holdings: list[dict] = []
        missing_price: list[str] = []

        for item in raw_items:
            payload = item["payload"]

            # 未實現損益 → 每檔市值反推價格：market_value = cost×qty + (profit − loss)
            price_by_symbol: dict[str, float] = {}
            for u in payload.get("unrealized", []):
                sym = u.get("stock_no")
                qty = float(u.get("today_qty") or 0)
                cost = float(u.get("cost_price") or 0)
                profit = float(u.get("unrealized_profit") or 0)
                loss = float(u.get("unrealized_loss") or 0)
                if sym and qty > 0:
                    price_by_symbol[sym] = (cost * qty + profit - loss) / qty

            for pos in payload.get("inventories", []):
                if not _is_stock_type(pos.get("order_type")):
                    print(f"  ⚠ [fubon] skip non-stock inventory {pos.get('stock_no')} "
                          f"(order_type={pos.get('order_type')})")
                    continue
                odd = pos.get("odd") or {}
                qty = float(pos.get("today_qty") or 0) + float(odd.get("today_qty") or 0)
                if qty == 0:
                    continue
                sym = pos.get("stock_no")
                price = price_by_symbol.get(sym)
                if price is None:
                    missing_price.append(sym)
                holdings.append({
                    "platform_symbol": sym,
                    "platform_asset_name": sym,
                    "asset_type": "stock",
                    "quantity": qty,
                    "price": price,
                    "value": round(qty * price, 8) if price is not None else None,
                    "original_currency": "TWD",
                    "price_source": "platform" if price is not None else None,
                    "resource_type": "stock",
                })

            bank = payload.get("bank_remain") or {}
            balance = float(bank.get("balance") or 0)
            currency = str(bank.get("currency") or "TWD").upper()
            if balance and currency != "TWD":
                # account_snapshots 幣別取第一筆 holding 且直接加總，混入非 TWD 會算錯
                print(f"  ⚠ [fubon] skip non-TWD bank balance: {balance} {currency}")
            elif balance:
                holdings.append({
                    "platform_symbol": "TWD",
                    "platform_asset_name": "銀行存款 (TWD)",
                    "asset_type": "cash",
                    "quantity": balance,
                    "price": 1.0,
                    "value": balance,
                    "original_currency": "TWD",
                    "price_source": "platform",
                    "resource_type": "cash",
                })

        # unrealized 反推不到的 symbol → 查共用 price_cache（永豐先跑會回存 TWD 價格）
        if missing_price:
            from app.valuation.price_cache import get_cached_prices
            cached = get_cached_prices(missing_price, date.today().isoformat())
            for h in holdings:
                if h["price"] is None:
                    p = cached.get(h["platform_symbol"])
                    if p is not None:
                        h["price"] = p
                        h["value"] = round(h["quantity"] * p, 8)
                        h["price_source"] = "market"
                    else:
                        print(f"  ⚠ [fubon] no price for {h['platform_symbol']} "
                              f"(not in unrealized nor price_cache)")

        return holdings
