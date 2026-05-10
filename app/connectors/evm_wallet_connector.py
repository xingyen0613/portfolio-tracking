"""
EVM multi-chain wallet connector using Alchemy API.
Single API key covers all supported chains via per-chain subdomain.
Auto-discovers all ERC-20 token balances — no whitelist needed.

Price sources:
  Native tokens : CoinGecko simple/price (module-level cache, TTL=10min)
  ERC-20        : CoinGecko simple/token_price/{platform}?contract_addresses=...
  Stablecoins   : Fixed $1
"""

import time
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

USD_THRESHOLD = 1.0
_CALL_DELAY = 0.1  # Alchemy free tier: ~330 CU/sec, well above our usage

STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "USDE", "FDUSD", "USDS", "PYUSD", "CRVUSD"}

# ── Per-chain config ───────────────────────────────────────────────────────────
CHAIN_CONFIG: dict[str, dict] = {
    "ethereum": {
        "subdomain":   "eth-mainnet",
        "cg_platform": "ethereum",
        "short":       "eth",
        "native": {"symbol": "ETH",  "name": "Ethereum",  "decimals": 18, "coingecko_id": "ethereum",    "is_stable": False},
    },
    "bsc": {
        "subdomain":   "bnb-mainnet",
        "cg_platform": "binance-smart-chain",
        "short":       "bsc",
        "native": {"symbol": "BNB",  "name": "BNB",       "decimals": 18, "coingecko_id": "binancecoin", "is_stable": False},
    },
    "arbitrum": {
        "subdomain":   "arb-mainnet",
        "cg_platform": "arbitrum-one",
        "short":       "arb",
        "native": {"symbol": "ETH",  "name": "Ethereum",  "decimals": 18, "coingecko_id": "ethereum",    "is_stable": False},
    },
    "optimism": {
        "subdomain":   "opt-mainnet",
        "cg_platform": "optimistic-ethereum",
        "short":       "op",
        "native": {"symbol": "ETH",  "name": "Ethereum",  "decimals": 18, "coingecko_id": "ethereum",    "is_stable": False},
    },
    "base": {
        "subdomain":   "base-mainnet",
        "cg_platform": "base",
        "short":       "base",
        "native": {"symbol": "ETH",  "name": "Ethereum",  "decimals": 18, "coingecko_id": "ethereum",    "is_stable": False},
    },
    "avalanche": {
        "subdomain":   "avax-mainnet",
        "cg_platform": "avalanche",
        "short":       "avax",
        "native": {"symbol": "AVAX", "name": "Avalanche", "decimals": 18, "coingecko_id": "avalanche-2", "is_stable": False},
    },
    "polygon": {
        "subdomain":   "polygon-mainnet",
        "cg_platform": "polygon-pos",
        "short":       "matic",
        "native": {"symbol": "POL",  "name": "Polygon",   "decimals": 18, "coingecko_id": "matic-network","is_stable": False},
    },
    "linea": {
        "subdomain":   "linea-mainnet",
        "cg_platform": "linea",
        "short":       "linea",
        "native": {"symbol": "ETH",  "name": "Ethereum",  "decimals": 18, "coingecko_id": "ethereum",    "is_stable": False},
    },
}

DEFAULT_EVM_CHAINS: list[str] = list(CHAIN_CONFIG.keys())

# ── Module-level native price cache (shared across all connectors in one batch) ─
_NATIVE_CG_IDS: set[str] = {
    cfg["native"]["coingecko_id"]
    for cfg in CHAIN_CONFIG.values()
    if cfg["native"].get("coingecko_id")
}
_native_price_cache: dict[str, float] = {}
_native_cache_ts: float = 0.0
_CG_CACHE_TTL = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(symbol: str) -> str:
    return "stablecoin" if symbol.upper() in STABLECOINS else "crypto"


def _ensure_native_price_cache() -> None:
    """Batch-fetch all native token prices once; shared across all connectors."""
    global _native_price_cache, _native_cache_ts
    if _native_price_cache and time.time() - _native_cache_ts < _CG_CACHE_TTL:
        return
    ids = list(_NATIVE_CG_IDS)
    for attempt in range(3):
        try:
            if attempt:
                time.sleep(2 ** attempt)
            resp = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            _native_price_cache = {cg_id: data[cg_id]["usd"] for cg_id in ids if cg_id in data}
            _native_cache_ts = time.time()
            return
        except Exception:
            continue


def _alchemy_rpc(subdomain: str, api_key: str, method: str, params: list):
    time.sleep(_CALL_DELAY)
    url = f"https://{subdomain}.g.alchemy.com/v2/{api_key}"
    try:
        resp = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15,
        )
        if resp.status_code == 403:
            return None  # chain not enabled in Alchemy dashboard
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return None
        return data.get("result")
    except Exception:
        return None


def _fetch_token_prices_by_contract(platform: str, contracts: list[str]) -> dict[str, float]:
    """CoinGecko batch price by contract address. Returns {contract_lower: usd_price}."""
    if not contracts or not platform:
        return {}
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/simple/token_price/{platform}",
            params={"contract_addresses": ",".join(contracts), "vs_currencies": "usd"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {addr.lower(): info["usd"] for addr, info in data.items() if "usd" in info}
    except Exception:
        return {}


class EVMWalletConnector(BaseConnector):
    platform_name = "evm_wallet"
    use_pricer = False

    def __init__(self, wallet_address: str, chain_name: str, api_key: str):
        if chain_name not in CHAIN_CONFIG:
            raise ValueError(f"Unsupported chain: {chain_name}. Available: {list(CHAIN_CONFIG)}")
        self.wallet_address = wallet_address.lower()
        self.chain_name = chain_name
        self.api_key = api_key
        cfg = CHAIN_CONFIG[chain_name]
        self.subdomain   = cfg["subdomain"]
        self.chain_short = cfg["short"]
        self.cg_platform = cfg["cg_platform"]
        self.account_key = f"{self.wallet_address[:10]}_{self.chain_short}"

    def authenticate(self) -> None:
        if not self.api_key:
            raise ValueError("ALCHEMY_API_KEY is not set")

    def _rpc(self, method: str, params: list):
        return _alchemy_rpc(self.subdomain, self.api_key, method, params)

    def fetch_raw(self) -> list[dict]:
        address = self.wallet_address
        items = []

        # 1. Native balance
        result = self._rpc("eth_getBalance", [address, "latest"])
        native_wei = int(result, 16) if result else None
        items.append({"resource_type": "native_balance", "payload": {"wei": native_wei}, "fetched_at": _now()})

        # 2. ERC-20 auto-discovery
        token_result = self._rpc("alchemy_getTokenBalances", [address, "DEFAULT_TOKENS"])
        ZERO = {"0x0", "0x", None, "0x" + "0" * 64}
        raw_balances = []
        if token_result and "tokenBalances" in token_result:
            raw_balances = [b for b in token_result["tokenBalances"] if b.get("tokenBalance") not in ZERO]

        # 3. Metadata for each discovered token
        token_meta: dict[str, dict] = {}
        for b in raw_balances:
            contract = b["contractAddress"].lower()
            meta = self._rpc("alchemy_getTokenMetadata", [b["contractAddress"]])
            if meta and meta.get("decimals") is not None:
                token_meta[contract] = {
                    "symbol":   (meta.get("symbol") or "?").upper(),
                    "decimals": int(meta["decimals"]),
                    "name":     meta.get("name") or "",
                }

        # Build token_balances: contract → raw int
        token_balances: dict[str, int] = {}
        for b in raw_balances:
            contract = b["contractAddress"].lower()
            if contract not in token_meta:
                continue
            try:
                token_balances[contract] = int(b["tokenBalance"], 16)
            except (TypeError, ValueError):
                pass

        items.append({"resource_type": "token_balances", "payload": token_balances, "fetched_at": _now()})
        items.append({"resource_type": "token_meta",     "payload": token_meta,     "fetched_at": _now()})

        # 4. Native price (module-level cache)
        _ensure_native_price_cache()
        native_cfg = CHAIN_CONFIG[self.chain_name]["native"]
        if native_cfg.get("is_stable"):
            native_price, native_source = 1.0, "stable"
        else:
            cg_id = native_cfg.get("coingecko_id")
            native_price = _native_price_cache.get(cg_id) if cg_id else None
            native_source = "coingecko"
        items.append({"resource_type": "native_price", "payload": {"price_usd": native_price, "source": native_source}, "fetched_at": _now()})

        # 5. ERC-20 prices via CoinGecko by contract (skip stable chain and known stablecoins)
        non_stable = [c for c, m in token_meta.items() if m["symbol"] not in STABLECOINS and self.cg_platform]
        erc20_prices = _fetch_token_prices_by_contract(self.cg_platform, non_stable) if non_stable else {}
        items.append({"resource_type": "erc20_prices", "payload": erc20_prices, "fetched_at": _now()})

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        native_cfg = CHAIN_CONFIG[self.chain_name]["native"]
        native_wei: int | None = None
        native_price: float | None = None
        native_source = "unknown"
        token_balances: dict[str, int] = {}
        token_meta: dict[str, dict] = {}
        erc20_prices: dict[str, float] = {}

        for item in raw_items:
            if item.get("fetch_error"):
                continue
            rt, payload = item["resource_type"], item["payload"]
            if rt == "native_balance":
                native_wei = payload.get("wei")
            elif rt == "native_price":
                native_price = payload.get("price_usd")
                native_source = payload.get("source", "unknown")
            elif rt == "token_balances":
                token_balances = payload
            elif rt == "token_meta":
                token_meta = payload
            elif rt == "erc20_prices":
                erc20_prices = payload

        holdings = []

        # Native token
        if native_wei is not None and native_price is not None:
            qty = native_wei / (10 ** native_cfg["decimals"])
            val = qty * native_price
            if val > USD_THRESHOLD:
                holdings.append({
                    "platform_symbol":     native_cfg["symbol"],
                    "platform_asset_name": native_cfg["name"],
                    "asset_type":          _classify(native_cfg["symbol"]),
                    "quantity":            qty,
                    "price":               native_price,
                    "value":               val,
                    "original_currency":   "USD",
                    "price_source":        native_source,
                    "chain":               self.chain_name,
                })

        # ERC-20 tokens
        for contract, raw_bal in token_balances.items():
            if not raw_bal:
                continue
            meta = token_meta.get(contract)
            if not meta:
                continue
            qty = raw_bal / (10 ** meta["decimals"])
            if qty <= 0:
                continue

            symbol = meta["symbol"]
            if symbol in STABLECOINS or self.cg_platform is None:
                price, price_source = 1.0, "stable"
            else:
                price = erc20_prices.get(contract)
                price_source = "coingecko"

            if price is None:
                continue

            val = qty * price
            if val <= USD_THRESHOLD:
                continue

            holdings.append({
                "platform_symbol":     symbol,
                "platform_asset_name": meta["name"] or symbol,
                "asset_type":          _classify(symbol),
                "quantity":            qty,
                "price":               price,
                "value":               val,
                "original_currency":   "USD",
                "price_source":        price_source,
                "chain":               self.chain_name,
                "resource_type":       "wallet",
            })

        return holdings
