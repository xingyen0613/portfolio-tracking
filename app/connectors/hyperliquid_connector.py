"""
Hyperliquid connector — 公開 info API，只需錢包地址，不需 API key。

Endpoint     : https://api.hyperliquid.xyz/info（POST，type 欄位分流）
Rate limit   : 1200 weight/min per IP；本 connector 用到的 type 皆為 weight 2
Price source : Hyperliquid 自身的 spot midPx（不打外部查價）

淨值公式（PoC 實測驗證，差額 0.00000000）：
    accountValue = totalRawUsd + Σ sign(szi) × positionValue

positionValue 以 markPx 計價，本身已含未實現損益。為了讓「未實現損益」
能成為獨立可見的子分類、又不重複計算，部位與損益拆成兩段記錄：

    perp_position.value = sign(szi) × positionValue − unrealizedPnl
    perp_upnl.value     = Σ unrealizedPnl

兩者相加還原成 Σ sign(szi) × positionValue，因此 holdings 總和精確等於
accountValue，與 Hyperliquid 官網顯示一致。

詳細驗證過程見 scripts/hyperliquid_poc.py 與 docs/hyperliquid-api-poc.md。
"""

from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

API_URL = "https://api.hyperliquid.xyz/info"

USD_THRESHOLD = 1.0   # 現貨 USD 價值低於此值視為粉塵/空投，過濾掉

STABLECOINS = {"USDC", "USDT", "USDT0", "USDE", "USDH", "DAI", "FDUSD", "USDD"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(x, default=0.0) -> float:
    """Hyperliquid 所有數值皆以 string 回傳。"""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _classify(symbol: str) -> str:
    return "stablecoin" if symbol.upper() in STABLECOINS else "crypto"


def _info(req_type: str, **kwargs) -> dict | list | None:
    try:
        resp = requests.post(API_URL, json={"type": req_type, **kwargs}, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def build_spot_prices(spot_meta_ctxs) -> dict[str, float]:
    """從 spotMetaAndAssetCtxs 建 token name → USD 價格。

    回傳結構為 [meta, ctxs]：meta.universe[i] 的交易對對應 ctxs[i] 的報價。
    只採用 USDC 計價對；其他計價幣要再換一手，暫不支援。
    """
    if not isinstance(spot_meta_ctxs, list) or len(spot_meta_ctxs) < 2:
        return {}
    meta, ctxs = spot_meta_ctxs[0], spot_meta_ctxs[1]
    tokens = meta.get("tokens", [])
    universe = meta.get("universe", [])

    name_by_idx = {t.get("index"): t.get("name") for t in tokens}
    usdc_idx = next((t.get("index") for t in tokens if t.get("name") == "USDC"), None)

    prices: dict[str, float] = {"USDC": 1.0}
    for pair, ctx in zip(universe, ctxs):
        pair_tokens = pair.get("tokens") or []
        if len(pair_tokens) != 2:
            continue
        base_idx, quote_idx = pair_tokens
        if usdc_idx is not None and quote_idx != usdc_idx:
            continue
        px = ctx.get("midPx") or ctx.get("markPx")
        if px is None:
            continue
        base_name = name_by_idx.get(base_idx)
        if base_name:
            prices[base_name] = _f(px)
    return prices


class HyperliquidConnector(BaseConnector):
    platform_name = "hyperliquid"
    use_pricer = False  # 價格來自 Hyperliquid 自身報價，不需 pricer

    def __init__(self, wallet_address: str):
        self.wallet_address = wallet_address
        self.account_key = wallet_address[:10] if len(wallet_address) >= 10 else wallet_address

    def authenticate(self) -> None:
        # info endpoint 為公開讀取，無需認證
        pass

    def fetch_raw(self) -> list[dict]:
        items = []

        perp = _info("clearinghouseState", user=self.wallet_address)
        items.append({
            "resource_type": "perp_state",
            "payload": perp if isinstance(perp, dict) else {},
            "fetched_at": _now(),
        })

        spot = _info("spotClearinghouseState", user=self.wallet_address)
        items.append({
            "resource_type": "spot_state",
            "payload": spot if isinstance(spot, dict) else {},
            "fetched_at": _now(),
        })

        # 現貨定價：只留用得到的 token → USD，不存整份 meta（481 token 太大）
        meta_ctxs = _info("spotMetaAndAssetCtxs")
        items.append({
            "resource_type": "spot_prices",
            "payload": build_spot_prices(meta_ctxs),
            "fetched_at": _now(),
        })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        perp: dict = {}
        spot: dict = {}
        prices: dict[str, float] = {}

        for item in raw_items:
            if item.get("fetch_error"):
                continue
            rt = item["resource_type"]
            payload = item["payload"]
            if rt == "perp_state":
                perp = payload or {}
            elif rt == "spot_state":
                spot = payload or {}
            elif rt == "spot_prices":
                prices = payload or {}

        holdings: list[dict] = []

        # ── 現貨餘額 ──────────────────────────────────────────────
        for b in spot.get("balances", []):
            coin = b.get("coin")
            qty = _f(b.get("total"))
            if not coin or qty <= 0:
                continue
            price = prices.get(coin)
            if price is None:
                continue  # 無 USDC 計價對 → 無法定價，過濾
            usd = qty * price
            if usd <= USD_THRESHOLD:
                continue  # 粉塵/空投
            holdings.append({
                "platform_symbol": coin,
                "platform_asset_name": coin,
                "asset_type": _classify(coin),
                "quantity": qty,
                "price": price,
                "value": usd,
                "original_currency": "USD",
                "price_source": "platform",
                "resource_type": "spot",
            })

        # ── 永續現金（totalRawUsd 為純現金，不含部位）────────────
        margin = perp.get("marginSummary") or {}
        raw_usd = _f(margin.get("totalRawUsd"))
        if abs(raw_usd) > 0:
            holdings.append({
                "platform_symbol": "USDC",
                "platform_asset_name": "永續保證金現金",
                "asset_type": "stablecoin",
                "quantity": raw_usd,
                "price": 1.0,
                "value": raw_usd,
                "original_currency": "USD",
                "price_source": "platform",
                "resource_type": "perp_cash",
            })

        # ── 永續部位與未實現損益 ─────────────────────────────────
        # 部位記成本基礎（扣掉 uPnL），uPnL 另立一筆；兩者相加還原市值，
        # 使 holdings 總和 == accountValue，同時讓損益成為獨立子分類。
        total_upnl = 0.0
        for ap in perp.get("assetPositions", []):
            p = ap.get("position") or {}
            coin = p.get("coin")
            szi = _f(p.get("szi"))
            if not coin or szi == 0:
                continue
            pos_value = _f(p.get("positionValue"))
            upnl = _f(p.get("unrealizedPnl"))
            total_upnl += upnl

            signed_value = pos_value if szi > 0 else -pos_value
            holdings.append({
                "platform_symbol": coin,
                "platform_asset_name": f"{coin} 永續（{'多' if szi > 0 else '空'}）",
                "asset_type": "crypto",
                "quantity": szi,
                "price": _f(p.get("entryPx")) or None,
                "value": signed_value - upnl,
                "original_currency": "USD",
                # 不用 "platform"：這裡的 price 是進場價非市價，
                # 標成 platform 會被 pipeline 存進 price_cache 污染真實報價
                "price_source": "entry_price",
                "resource_type": "perp_position",
            })

        if abs(total_upnl) > 0:
            holdings.append({
                "platform_symbol": "UPNL",
                "platform_asset_name": "未實現損益",
                "asset_type": "crypto",
                "quantity": total_upnl,
                "price": 1.0,
                "value": total_upnl,
                "original_currency": "USD",
                "price_source": "derived",
                "resource_type": "perp_upnl",
            })

        return holdings
