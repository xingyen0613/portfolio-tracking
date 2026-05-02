"""
Solana wallet connector using Alchemy RPC.
Queries native SOL balance and all SPL token balances automatically.

Price sources:
  SOL native   : CoinGecko simple/price (module-level cache)
  SPL tokens   : CoinGecko simple/token_price/solana?contract_addresses=...
  Stablecoins  : Fixed $1 (checked by mint address + symbol)

Token metadata : Jupiter token list (module-level cache, fetched once per process)
"""

import time
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

ALCHEMY_SOLANA_RPC = "https://solana-mainnet.g.alchemy.com/v2/{api_key}"
SPL_TOKEN_PROGRAM  = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
JUPITER_TOKEN_LIST = "https://token.jup.ag/all"

USD_THRESHOLD = 1.0
_CALL_DELAY   = 0.1

STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "USDE", "FDUSD", "USDS", "PYUSD"}

# Known stablecoin mints
SOL_STABLECOIN_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

# Hardcoded fallback metadata for common tokens — used when Jupiter is unavailable
KNOWN_MINTS: dict[str, dict] = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"symbol": "USDC",  "name": "USD Coin",   "decimals": 6},
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": {"symbol": "USDT",  "name": "Tether USD",  "decimals": 6},
    "So11111111111111111111111111111111111111112":    {"symbol": "SOL",   "name": "Wrapped SOL", "decimals": 9},
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": {"symbol": "ETH",   "name": "Wrapped ETH (Wormhole)", "decimals": 8},
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": {"symbol": "WBTC",  "name": "Wrapped BTC (Wormhole)", "decimals": 8},
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So":  {"symbol": "mSOL",  "name": "Marinade staked SOL",    "decimals": 9},
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1":  {"symbol": "bSOL",  "name": "BlazeStake Staked SOL",  "decimals": 9},
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": {"symbol": "JitoSOL","name": "Jito Staked SOL",       "decimals": 9},
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v":  {"symbol": "JupSOL","name": "Jupiter Staked SOL",      "decimals": 9},
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN":  {"symbol": "JUP",   "name": "Jupiter",                "decimals": 6},
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": {"symbol": "BONK",  "name": "Bonk",                   "decimals": 5},
    "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk":  {"symbol": "WEN",   "name": "WEN",                    "decimals": 5},
    "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4": {"symbol": "JLP",   "name": "Jupiter Liquidity Provider Token", "decimals": 6},
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": {"symbol": "PYTH",  "name": "Pyth Network",           "decimals": 6},
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE":  {"symbol": "ORCA",  "name": "Orca",                   "decimals": 6},
    "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof":  {"symbol": "RENDER","name": "Render Token",            "decimals": 8},
}

# ── Module-level caches ────────────────────────────────────────────────────────
_jupiter_cache: dict[str, dict] = {}   # mint → {symbol, name, decimals}
_jupiter_loaded = False

_sol_price_cache: float | None = None
_sol_price_ts: float = 0.0
_CG_CACHE_TTL = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(symbol: str) -> str:
    return "stablecoin" if symbol.upper() in STABLECOINS else "crypto"


def _ensure_jupiter_cache() -> None:
    """Populate token cache: start with KNOWN_MINTS, then enrich from Jupiter if reachable."""
    global _jupiter_cache, _jupiter_loaded
    if _jupiter_loaded:
        return
    # Always seed with hardcoded fallbacks first
    _jupiter_cache.update(KNOWN_MINTS)
    try:
        resp = requests.get(JUPITER_TOKEN_LIST, timeout=15)
        resp.raise_for_status()
        for token in resp.json():
            mint = token.get("address", "")
            if mint:
                _jupiter_cache[mint] = {
                    "symbol":   token.get("symbol", "?"),
                    "name":     token.get("name", ""),
                    "decimals": int(token.get("decimals", 9)),
                }
        print(f"  [sol_wallet] Jupiter token list loaded ({len(_jupiter_cache)} tokens)")
    except Exception as e:
        print(f"  [sol_wallet] Jupiter unavailable ({e}), using {len(_jupiter_cache)} hardcoded tokens")
    _jupiter_loaded = True


def _ensure_sol_price() -> float | None:
    global _sol_price_cache, _sol_price_ts
    if _sol_price_cache is not None and time.time() - _sol_price_ts < _CG_CACHE_TTL:
        return _sol_price_cache
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "solana", "vs_currencies": "usd"},
            timeout=15,
        )
        resp.raise_for_status()
        price = resp.json()["solana"]["usd"]
        _sol_price_cache = price
        _sol_price_ts = time.time()
        return price
    except Exception:
        return _sol_price_cache


def _fetch_spl_prices(mints: list[str]) -> dict[str, float]:
    """CoinGecko batch price by mint address on Solana."""
    if not mints:
        return {}
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/token_price/solana",
            params={"contract_addresses": ",".join(mints), "vs_currencies": "usd"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {mint: info["usd"] for mint, info in data.items() if "usd" in info}
    except Exception:
        return {}


class SolWalletConnector(BaseConnector):
    platform_name = "sol_wallet"
    use_pricer = False

    def __init__(self, wallet_address: str, api_key: str):
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.account_key = wallet_address[:10]
        self._rpc_url = ALCHEMY_SOLANA_RPC.format(api_key=api_key)

    def authenticate(self) -> None:
        if not self.api_key:
            raise ValueError("ALCHEMY_API_KEY is not set")

    def _rpc(self, method: str, params: list):
        time.sleep(_CALL_DELAY)
        try:
            resp = requests.post(
                self._rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=15,
            )
            if resp.status_code == 403:
                return None
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                return None
            return data.get("result")
        except Exception:
            return None

    def fetch_raw(self) -> list[dict]:
        items = []

        # 1. Native SOL balance (lamports)
        result = self._rpc("getBalance", [self.wallet_address])
        lamports = result["value"] if result and "value" in result else None
        items.append({"resource_type": "native_balance", "payload": {"lamports": lamports}, "fetched_at": _now()})

        # 2. SPL token accounts
        result = self._rpc("getTokenAccountsByOwner", [
            self.wallet_address,
            {"programId": SPL_TOKEN_PROGRAM},
            {"encoding": "jsonParsed"},
        ])
        spl_tokens: list[dict] = []  # [{mint, ui_amount, decimals}]
        if result and "value" in result:
            for acct in result["value"]:
                try:
                    info = acct["account"]["data"]["parsed"]["info"]
                    mint = info["mint"]
                    ta = info["tokenAmount"]
                    ui_amount = float(ta.get("uiAmount") or 0)
                    if ui_amount > 0:
                        spl_tokens.append({
                            "mint":      mint,
                            "ui_amount": ui_amount,
                            "decimals":  int(ta.get("decimals", 9)),
                        })
                except (KeyError, TypeError, ValueError):
                    continue
        items.append({"resource_type": "spl_balances", "payload": spl_tokens, "fetched_at": _now()})

        # 3. Token metadata from Jupiter
        _ensure_jupiter_cache()

        # 4. Native SOL price
        sol_price = _ensure_sol_price()
        items.append({"resource_type": "sol_price", "payload": {"price_usd": sol_price}, "fetched_at": _now()})

        # 5. SPL token prices (skip stablecoins)
        non_stable_mints = [
            t["mint"] for t in spl_tokens
            if t["mint"] not in SOL_STABLECOIN_MINTS
            and _jupiter_cache.get(t["mint"], {}).get("symbol", "?").upper() not in STABLECOINS
        ]
        spl_prices = _fetch_spl_prices(non_stable_mints) if non_stable_mints else {}
        items.append({"resource_type": "spl_prices", "payload": spl_prices, "fetched_at": _now()})

        return items

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        lamports: int | None = None
        sol_price: float | None = None
        spl_tokens: list[dict] = []
        spl_prices: dict[str, float] = {}

        for item in raw_items:
            if item.get("fetch_error"):
                continue
            rt, payload = item["resource_type"], item["payload"]
            if rt == "native_balance":
                lamports = payload.get("lamports")
            elif rt == "sol_price":
                sol_price = payload.get("price_usd")
            elif rt == "spl_balances":
                spl_tokens = payload
            elif rt == "spl_prices":
                spl_prices = payload

        holdings = []

        # Native SOL
        if lamports is not None and sol_price is not None:
            qty = lamports / 1e9
            val = qty * sol_price
            if val > USD_THRESHOLD:
                holdings.append({
                    "platform_symbol":     "SOL",
                    "platform_asset_name": "Solana",
                    "asset_type":          "crypto",
                    "quantity":            qty,
                    "price":               sol_price,
                    "value":               val,
                    "original_currency":   "USD",
                    "price_source":        "coingecko",
                    "chain":               None,
                })

        # SPL tokens
        for token in spl_tokens:
            mint      = token["mint"]
            ui_amount = token["ui_amount"]
            meta      = _jupiter_cache.get(mint, {})
            symbol    = meta.get("symbol", mint[:8])
            name      = meta.get("name", "")

            is_stable = mint in SOL_STABLECOIN_MINTS or symbol.upper() in STABLECOINS
            if is_stable:
                price, price_source = 1.0, "stable"
            else:
                price = spl_prices.get(mint)
                price_source = "coingecko"

            if price is None:
                continue

            val = ui_amount * price
            if val <= USD_THRESHOLD:
                continue

            holdings.append({
                "platform_symbol":     symbol,
                "platform_asset_name": name or symbol,
                "asset_type":          "stablecoin" if is_stable else "crypto",
                "quantity":            ui_amount,
                "price":               price,
                "value":               val,
                "original_currency":   "USD",
                "price_source":        price_source,
                "chain":               None,
            })

        return holdings
