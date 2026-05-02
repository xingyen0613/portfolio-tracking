"""
EVM multi-chain wallet connector using Etherscan API v2.
One API key covers all supported chains (change chainid param only).
Rate limit: 5 calls/sec, 100k calls/day (free tier).

Supported chains: ethereum, bsc, arbitrum, optimism, base, avalanche, polygon, linea

Price source: CoinGecko simple/price (free, no key, batch query)
Stablecoins: fixed $1
"""

import time
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"

USD_THRESHOLD = 1.0
_CALL_DELAY = 0.25  # 4 calls/sec, safely under the 5/sec free limit

STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "USDE", "FDUSD"}

# ── Per-chain config ───────────────────────────────────────────────────────────
# contract keys are lowercase; tokens list can be extended freely
CHAIN_CONFIG: dict[str, dict] = {
    "ethereum": {
        "chain_id": 1,
        "short": "eth",
        "native": {"symbol": "ETH", "name": "Ethereum", "decimals": 18, "coingecko_id": "ethereum"},
        "tokens": {
            "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x6b175474e89094c44da98b954eedeac495271d0f": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
            "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"symbol": "UNI",  "decimals": 18, "is_stable": False, "coingecko_id": "uniswap"},
            "0x514910771af9ca656af840dff83e8264ecf986ca": {"symbol": "LINK", "decimals": 18, "is_stable": False, "coingecko_id": "chainlink"},
            "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": {"symbol": "AAVE", "decimals": 18, "is_stable": False, "coingecko_id": "aave"},
            "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72": {"symbol": "ENS",  "decimals": 18, "is_stable": False, "coingecko_id": "ethereum-name-service"},
        },
    },
    "bsc": {
        "chain_id": 56,
        "short": "bsc",
        "native": {"symbol": "BNB", "name": "BNB", "decimals": 18, "coingecko_id": "binancecoin"},
        "tokens": {
            "0x55d398326f99059ff775485246999027b3197955": {"symbol": "USDT", "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": {"symbol": "USDC", "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": {"symbol": "BTCB", "decimals": 18, "is_stable": False, "coingecko_id": "bitcoin-bep2"},
            "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82": {"symbol": "CAKE", "decimals": 18, "is_stable": False, "coingecko_id": "pancakeswap-token"},
        },
    },
    "arbitrum": {
        "chain_id": 42161,
        "short": "arb",
        "native": {"symbol": "ETH", "name": "Ethereum", "decimals": 18, "coingecko_id": "ethereum"},
        "tokens": {
            "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
            "0x912ce59144191c1204e64559fe8253a0e49e6548": {"symbol": "ARB",  "decimals": 18, "is_stable": False, "coingecko_id": "arbitrum"},
            "0xf97f4df75117a78c1a5a0dbb814af92458539fb4": {"symbol": "LINK", "decimals": 18, "is_stable": False, "coingecko_id": "chainlink"},
        },
    },
    "optimism": {
        "chain_id": 10,
        "short": "op",
        "native": {"symbol": "ETH", "name": "Ethereum", "decimals": 18, "coingecko_id": "ethereum"},
        "tokens": {
            "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x0b2c639c533813f4aa9d7837caf62653d097ff85": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x68f180fcce6836688e9084f035309e29bf0a2095": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
            "0x4200000000000000000000000000000000000042": {"symbol": "OP",   "decimals": 18, "is_stable": False, "coingecko_id": "optimism"},
        },
    },
    "base": {
        "chain_id": 8453,
        "short": "base",
        "native": {"symbol": "ETH", "name": "Ethereum", "decimals": 18, "coingecko_id": "ethereum"},
        "tokens": {
            "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x0555e30da8f98308edb960aa94c0db47230d2b9c": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
            "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22": {"symbol": "cbETH","decimals": 18, "is_stable": False, "coingecko_id": "coinbase-wrapped-staked-eth"},
        },
    },
    "avalanche": {
        "chain_id": 43114,
        "short": "avax",
        "native": {"symbol": "AVAX", "name": "Avalanche", "decimals": 18, "coingecko_id": "avalanche-2"},
        "tokens": {
            "0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x50b7545627a5162f82a992c33b87adc75187b218": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
            "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7": {"symbol": "WAVAX","decimals": 18, "is_stable": False, "coingecko_id": "avalanche-2"},
        },
    },
    "polygon": {
        "chain_id": 137,
        "short": "matic",
        "native": {"symbol": "POL", "name": "Polygon", "decimals": 18, "coingecko_id": "matic-network"},
        "tokens": {
            "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": {"symbol": "DAI",  "decimals": 18, "is_stable": True,  "coingecko_id": None},
            "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
        },
    },
    "linea": {
        "chain_id": 59144,
        "short": "linea",
        "native": {"symbol": "ETH", "name": "Ethereum", "decimals": 18, "is_stable": False, "coingecko_id": "ethereum"},
        "tokens": {
            "0xa219439258ca9da29e9cc4ce5596924745e12b93": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x176211869ca2b568f2a7d4ee941e073a821ee1ff": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0x3aab2285ddcddad8edf438c1bab47e1a9d05a9b4": {"symbol": "WBTC", "decimals": 8,  "is_stable": False, "coingecko_id": "wrapped-bitcoin"},
        },
    },
    "stable": {
        "chain_id": 988,
        "short": "stbl",
        # Stability Protocol: native gas token is a stablecoin (~$1), coingecko_id=None
        "native": {"symbol": "STBL", "name": "Stability", "decimals": 18, "is_stable": True, "coingecko_id": None},
        "tokens": {
            "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "decimals": 6,  "is_stable": True,  "coingecko_id": None},
        },
    },
}


# ── Module-level price cache (shared across all connector instances in one batch) ─
# All coingecko_ids needed by any chain are collected here; first call fetches all,
# subsequent calls reuse. Cache is invalidated after 10 minutes.
_cg_cache: dict[str, float] = {}
_cg_cache_ts: float = 0.0
_CG_CACHE_TTL = 600  # seconds

# Pre-collect ALL coingecko_ids across every chain so we can batch-fetch once
_ALL_CG_IDS: set[str] = set()
for _cfg in CHAIN_CONFIG.values():
    if _cfg["native"].get("coingecko_id"):
        _ALL_CG_IDS.add(_cfg["native"]["coingecko_id"])
    for _t in _cfg["tokens"].values():
        if not _t["is_stable"] and _t.get("coingecko_id"):
            _ALL_CG_IDS.add(_t["coingecko_id"])

# Etherscan ETH price cache (separate — fetched via Etherscan, not CoinGecko)
_eth_price_cache: float | None = None
_eth_price_cache_ts: float = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(symbol: str) -> str:
    return "stablecoin" if symbol.upper() in STABLECOINS else "crypto"


def _etherscan_get(chain_id: int, params: dict, api_key: str) -> dict | None:
    time.sleep(_CALL_DELAY)
    try:
        resp = requests.get(
            ETHERSCAN_BASE,
            params={"chainid": chain_id, "apikey": api_key, **params},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            return None
        return data
    except Exception:
        return None


def _fetch_native_balance(address: str, chain_id: int, api_key: str) -> int | None:
    data = _etherscan_get(chain_id, {"module": "account", "action": "balance", "address": address, "tag": "latest"}, api_key)
    if not data:
        return None
    try:
        return int(data["result"])
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_token_balance(address: str, contract: str, chain_id: int, api_key: str) -> int | None:
    data = _etherscan_get(chain_id, {
        "module": "account", "action": "tokenbalance",
        "contractaddress": contract, "address": address, "tag": "latest",
    }, api_key)
    if not data:
        return None
    try:
        return int(data["result"])
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_eth_price_from_etherscan(api_key: str) -> float | None:
    """Use Etherscan stats/ethprice — reliable, not rate-limited by CoinGecko.
    Cached for _CG_CACHE_TTL seconds so all connectors in a batch share one call."""
    global _eth_price_cache, _eth_price_cache_ts
    if _eth_price_cache is not None and time.time() - _eth_price_cache_ts < _CG_CACHE_TTL:
        return _eth_price_cache
    data = _etherscan_get(1, {"module": "stats", "action": "ethprice"}, api_key)
    if not data:
        return _eth_price_cache  # return stale value on failure rather than None
    try:
        price = float(data["result"]["ethusd"])
        _eth_price_cache = price
        _eth_price_cache_ts = time.time()
        return price
    except (KeyError, TypeError, ValueError):
        return _eth_price_cache


def _ensure_cg_cache() -> None:
    """Fetch ALL coingecko prices once for the entire batch; subsequent calls are no-ops."""
    global _cg_cache, _cg_cache_ts
    if _cg_cache and time.time() - _cg_cache_ts < _CG_CACHE_TTL:
        return  # cache still warm
    ids = list(_ALL_CG_IDS)
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            resp = requests.get(
                COINGECKO_PRICE_URL,
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            _cg_cache = {cg_id: data[cg_id]["usd"] for cg_id in ids if cg_id in data}
            _cg_cache_ts = time.time()
            return
        except Exception:
            continue
    # On total failure keep existing cache (stale but better than empty)


def _get_cg_price(coingecko_id: str) -> float | None:
    return _cg_cache.get(coingecko_id)


class EVMWalletConnector(BaseConnector):
    platform_name = "evm_wallet"
    use_pricer = False

    def __init__(self, wallet_address: str, chain_name: str, api_key: str):
        if chain_name not in CHAIN_CONFIG:
            raise ValueError(f"Unsupported chain: {chain_name}. Choose from: {list(CHAIN_CONFIG)}")
        self.wallet_address = wallet_address.lower()
        self.chain_name = chain_name
        self.api_key = api_key
        cfg = CHAIN_CONFIG[chain_name]
        self.chain_id = cfg["chain_id"]
        self.chain_short = cfg["short"]
        self.account_key = f"{self.wallet_address[:10]}_{self.chain_short}"

    def authenticate(self) -> None:
        if not self.api_key:
            raise ValueError("ETHERSCAN_API_KEY is not set")

    def fetch_raw(self) -> list[dict]:
        cfg = CHAIN_CONFIG[self.chain_name]
        chain_id = self.chain_id
        address = self.wallet_address
        items = []

        # 1. Native balance
        native_wei = _fetch_native_balance(address, chain_id, self.api_key)
        items.append({
            "resource_type": "native_balance",
            "payload": {"wei": native_wei},
            "fetched_at": _now(),
        })

        # 2. ERC-20 token balances
        token_balances: dict[str, int | None] = {}
        for contract in cfg["tokens"]:
            token_balances[contract] = _fetch_token_balance(address, contract, chain_id, self.api_key)
        items.append({
            "resource_type": "token_balances",
            "payload": token_balances,
            "fetched_at": _now(),
        })

        # 3. Ensure CoinGecko price cache is warm (one call for ALL chains/tokens)
        _ensure_cg_cache()

        # 4. Native price — ETH via Etherscan, stablecoin fixed $1, others from CoinGecko cache
        native_cfg = cfg["native"]
        if native_cfg.get("is_stable"):
            native_price = 1.0
            native_price_source = "stable"
        elif native_cfg["symbol"] == "ETH":
            native_price = _fetch_eth_price_from_etherscan(self.api_key)
            native_price_source = "etherscan"
        else:
            native_cg_id = native_cfg.get("coingecko_id")
            native_price = _get_cg_price(native_cg_id) if native_cg_id else None
            native_price_source = "coingecko"
        items.append({
            "resource_type": "native_price",
            "payload": {"price_usd": native_price, "source": native_price_source},
            "fetched_at": _now(),
        })

        # 5. ERC-20 prices from CoinGecko cache (no extra HTTP call)
        erc20_prices = {
            meta["coingecko_id"]: _get_cg_price(meta["coingecko_id"])
            for meta in cfg["tokens"].values()
            if not meta["is_stable"] and meta.get("coingecko_id")
        }
        items.append({
            "resource_type": "coingecko_prices",
            "payload": {k: v for k, v in erc20_prices.items() if v is not None},
            "fetched_at": _now(),
        })

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        cfg = CHAIN_CONFIG[self.chain_name]
        native_wei: int | None = None
        native_price: float | None = None
        native_price_source: str = "unknown"
        token_balances: dict[str, int | None] = {}
        cg_prices: dict[str, float] = {}

        for item in raw_items:
            if item.get("fetch_error"):
                continue
            rt = item["resource_type"]
            payload = item["payload"]
            if rt == "native_balance":
                native_wei = payload.get("wei")
            elif rt == "native_price":
                native_price = payload.get("price_usd")
                native_price_source = payload.get("source", "unknown")
            elif rt == "token_balances":
                token_balances = payload
            elif rt == "coingecko_prices":
                cg_prices = payload

        holdings = []
        native_cfg = cfg["native"]

        # Native token
        if native_wei is not None and native_price is not None:
            quantity = native_wei / (10 ** native_cfg["decimals"])
            value = quantity * native_price
            if value > USD_THRESHOLD:
                holdings.append({
                    "platform_symbol":     native_cfg["symbol"],
                    "platform_asset_name": native_cfg["name"],
                    "asset_type":          _classify(native_cfg["symbol"]),
                    "quantity":            quantity,
                    "price":               native_price,
                    "value":               value,
                    "original_currency":   "USD",
                    "price_source":        native_price_source,
                    "chain":               self.chain_name,
                })

        # ERC-20 tokens
        for contract, raw_balance in token_balances.items():
            if not raw_balance:
                continue
            meta = cfg["tokens"].get(contract)
            if not meta:
                continue

            quantity = raw_balance / (10 ** meta["decimals"])
            if quantity <= 0:
                continue

            if meta["is_stable"]:
                price = 1.0
                price_source = "stable"
            else:
                cg_id = meta.get("coingecko_id")
                price = cg_prices.get(cg_id) if cg_id else None
                price_source = "coingecko"

            if price is None:
                continue

            value = quantity * price
            if value <= USD_THRESHOLD:
                continue

            symbol = meta["symbol"]
            holdings.append({
                "platform_symbol":     symbol,
                "platform_asset_name": symbol,
                "asset_type":          _classify(symbol),
                "quantity":            quantity,
                "price":               price,
                "value":               value,
                "original_currency":   "USD",
                "price_source":        price_source,
                "chain":               self.chain_name,
            })

        return holdings
