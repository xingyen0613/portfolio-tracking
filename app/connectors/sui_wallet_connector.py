"""
SUI on-chain wallet connector using Sui public RPC + Pyth oracle.
No API key required — 完全免費，無速率限制。

Price source  : Pyth Hermes（讀取鏈上 Pyth price feed objects）
Token filter  : coin_type 必須在 COIN_FEED_MAP 內，且 USD value > USD_THRESHOLD
DeFi positions: 尚未支援（待後續版本）
"""

from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

# ── 端點 ──────────────────────────────────────────────────────────
SUI_RPC  = "https://fullnode.mainnet.sui.io:443"
PYTH_URL = "https://hermes.pyth.network/v2/updates/price/latest"

USD_THRESHOLD = 1.0   # USD value 低於此值過濾掉

# ── Coin type → Pyth feed ID（或 __STABLE__）─────────────────────
# Key 使用完整 coin_type address，避免 symbol 偽造
# Pyth feed IDs: https://pyth.network/developers/price-feed-ids
COIN_FEED_MAP: dict[str, str] = {
    # Native SUI
    "0x2::sui::SUI":
        "0x23d7315113f5b1d3ba7a83604c44b94d79f4fd69af77f804fc7f920a6dc65744",
    # ETH (Wormhole bridged)
    "0xd0e89b2af5e4910726fbcd8b8dd37bb79b29e5f83f7491bca830e94f7f226d29::eth::ETH":
        "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    # WBTC (Wormhole bridged)
    "0x027792d9fed7f9844eb4839566001bb6f6cb4804f66aa2da6fe1ee242d896881::coin::COIN":
        "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    # USDC — 多個 bridged 版本共用同一 Pyth feed
    "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC":
        "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "0x5d4b302506645c37ff133b98c4b50a5ae14841659738d6d733d59d0d217a93bf::coin::COIN":
        "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "0xdd6908843a65fb676886ca154461ededd1925a70bed664e1f417bb97d6735b2::usdc::USDC":
        "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    # USDT (Wormhole bridged)
    "0xa90e10bc38ff7e234e22fdd24692a1d8a3c9564113b13fc9961724fe37e91cba::usdt::USDT":
        "0x2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b",
    # ── Stablecoins (fixed $1, no Pyth query needed) ──────────────
    "0xce7ff77a83ea0cb6fd39bd8748e2ec89a3f41e8efdc3f4eb123e0ca37b184db2::buck::BUCK":
        "__STABLE__",
    "0xe44df51c0b21a27ab915fa1fe2ca610cd3eaa6d9666fe5e62b988bf7f0bd8722::musd::MUSD":
        "__STABLE__",
    "0x2053d08c1e2bd02791056171aab0fd12bd7cd7efad2ab8f6b9c8902f14df2ff2::ausd::AUSD":
        "__STABLE__",
    "0xb231fcda8bbddb31f2ef02e6161444aec64a514e2c89279584ac9806ce9cf037::coin::COIN":
        "__STABLE__",  # USDC via Celer bridge
}

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "BUCK", "USDE", "FDUSD", "MUSD", "AUSD", "SUSD"}

# Module-level metadata cache（跨 connector 實例共用，減少重複 RPC 呼叫）
_metadata_cache: dict[str, dict | None] = {}
_rpc_id = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(symbol: str) -> str:
    return "stablecoin" if symbol.upper() in STABLECOINS else "crypto"


def _rpc(method: str, params: list):
    global _rpc_id
    _rpc_id += 1
    try:
        resp = requests.post(SUI_RPC, json={
            "jsonrpc": "2.0", "id": _rpc_id,
            "method": method, "params": params,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return None if "error" in data else data.get("result")
    except Exception:
        return None


def _pyth_prices(feed_ids: list[str]) -> dict[str, float]:
    """Batch query；若 400 自動降級為逐一查詢。"""
    if not feed_ids:
        return {}

    def _parse(data: dict) -> dict[str, float]:
        out = {}
        for item in data.get("parsed", []):
            p     = item["price"]
            price = int(p["price"]) * (10 ** int(p["expo"]))
            out["0x" + item["id"]] = price
        return out

    try:
        resp = requests.get(PYTH_URL, params=[("ids[]", fid) for fid in feed_ids], timeout=15)
        resp.raise_for_status()
        return _parse(resp.json())
    except requests.HTTPError as e:
        if e.response.status_code != 400:
            return {}
        result = {}
        for fid in feed_ids:
            try:
                r = requests.get(PYTH_URL, params=[("ids[]", fid)], timeout=10)
                r.raise_for_status()
                result.update(_parse(r.json()))
            except Exception:
                pass
        return result
    except Exception:
        return {}


class SuiWalletConnector(BaseConnector):
    platform_name = "sui_wallet"
    use_pricer = False  # 價格由 Pyth 提供，不需 pricer

    def __init__(self, wallet_address: str):
        self.wallet_address = wallet_address
        self.account_key = wallet_address[:10] if len(wallet_address) >= 10 else wallet_address

    def authenticate(self) -> None:
        # 無需 API key，no-op
        pass

    def fetch_raw(self) -> list[dict]:
        items = []

        # 1. Token 餘額
        balances = _rpc("suix_getAllBalances", [self.wallet_address]) or []
        nonzero  = [b for b in balances if int(b.get("totalBalance", "0")) > 0]
        items.append({
            "resource_type": "balances",
            "payload": {"balances": nonzero},
            "fetched_at": _now(),
        })

        # 2. Coin metadata（dedup，使用 module-level cache）
        coin_types = [b["coinType"] for b in nonzero]
        uncached   = [ct for ct in coin_types if ct not in _metadata_cache]
        for ct in uncached:
            _metadata_cache[ct] = _rpc("suix_getCoinMetadata", [ct])

        items.append({
            "resource_type": "coin_metadata",
            "payload": {ct: _metadata_cache.get(ct) for ct in coin_types},
            "fetched_at": _now(),
        })

        # 3. Pyth prices（只查在 COIN_FEED_MAP 且有非零餘額的幣）
        feed_map: dict[str, str] = {}   # coin_type → feed_id
        for ct in coin_types:
            feed = COIN_FEED_MAP.get(ct)
            if feed and feed != "__STABLE__":
                feed_map[ct] = feed

        unique_feeds = list(set(feed_map.values()))
        prices_by_feed = _pyth_prices(unique_feeds)

        # 展開回 coin_type → price
        price_payload: dict[str, float | None] = {}
        for ct in coin_types:
            feed = COIN_FEED_MAP.get(ct)
            if feed == "__STABLE__":
                price_payload[ct] = 1.0
            elif feed:
                price_payload[ct] = prices_by_feed.get(feed)
            else:
                price_payload[ct] = None

        items.append({
            "resource_type": "pyth_prices",
            "payload": price_payload,
            "fetched_at": _now(),
        })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        # 重建 raw_items 的各 resource
        balances: list[dict] = []
        metadata: dict[str, dict | None] = {}
        prices:   dict[str, float | None] = {}

        for item in raw_items:
            if item.get("fetch_error"):
                continue
            rt      = item["resource_type"]
            payload = item["payload"]
            if rt == "balances":
                balances = payload.get("balances", [])
            elif rt == "coin_metadata":
                metadata = payload
            elif rt == "pyth_prices":
                prices = payload

        holdings = []
        for coin in balances:
            ct   = coin["coinType"]
            meta = metadata.get(ct)
            if not meta:
                continue  # 無 metadata → 過濾

            price = prices.get(ct)
            if price is None:
                continue  # 無價格 → 過濾

            decimals = int(meta.get("decimals", 9))
            quantity = int(coin["totalBalance"]) / (10 ** decimals)
            if quantity <= 0:
                continue

            usd_value = quantity * price
            if usd_value <= USD_THRESHOLD:
                continue  # 低於門檻 → 過濾

            symbol = meta.get("symbol", "UNKNOWN")
            holdings.append({
                "platform_symbol":    symbol,
                "platform_asset_name": meta.get("name", symbol),
                "asset_type":         _classify(symbol),
                "quantity":           quantity,
                "price":              price,
                "value":              usd_value,
                "original_currency":  "USD",
                "price_source":       "pyth" if COIN_FEED_MAP.get(ct) != "__STABLE__" else "stable",
            })

        return holdings
