"""
CLI entry point for running a data ingestion batch.

Usage:
    uv run python -m app.jobs.run_batch
    uv run python -m app.jobs.run_batch --platform binance
    uv run python -m app.jobs.run_batch --platform sui_wallet
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"

from config.db import get_conn
from app.storage.sqlite import init_db
from config.settings import ENABLED_PLATFORMS, ENV_PATH, PLATFORM_CATEGORY, WALLETS_ENV_PATH

load_dotenv(ENV_PATH)
load_dotenv(WALLETS_ENV_PATH, override=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_credentials(user_id: str, platform_name: str) -> dict:
    """Fetch decrypted credentials from user_connectors. Returns {} if not found."""
    try:
        from app.auth.encryption import decrypt
        with get_conn() as conn:
            cur = conn.execute(
                "SELECT credentials_json FROM user_connectors WHERE user_id=%s AND platform_name=%s AND status='active'",
                (user_id, platform_name),
            )
            row = cur.fetchone()
        if row and row["credentials_json"]:
            return json.loads(decrypt(row["credentials_json"]))
    except Exception:
        pass
    return {}


def _get_connectors(platform: str, credentials: dict) -> list:
    """Return list of connector instances for a platform (SUI = one per address)."""
    if platform == "binance":
        from app.connectors.binance_connector import BinanceConnector
        return [BinanceConnector(credentials)]
    if platform == "okx":
        from app.connectors.okx_connector import OKXConnector
        return [OKXConnector(credentials)]
    if platform == "mexc":
        from app.connectors.mexc_connector import MexcConnector
        return [MexcConnector(credentials)]
    if platform == "bybit":
        from app.connectors.bybit_connector import BybitConnector
        return [BybitConnector(credentials)]
    if platform == "sui_wallet":
        from app.connectors.sui_wallet_connector import SuiWalletConnector
        addresses_raw = os.environ.get("SUI_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if not addresses:
            raise ValueError("SUI_WALLET_ADDRESSES not set in .env")
        return [SuiWalletConnector(addr) for addr in addresses]
    if platform == "sol_wallet":
        from app.connectors.sol_wallet_connector import SolWalletConnector
        api_key = credentials.get("api_key") or os.environ.get("ALCHEMY_API_KEY", "")
        if not api_key:
            raise ValueError("ALCHEMY_API_KEY not set")
        addresses_raw = os.environ.get("SOL_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if not addresses:
            raise ValueError("SOL_WALLET_ADDRESSES not set in .env.wallets")
        return [SolWalletConnector(addr, api_key) for addr in addresses]
    if platform == "ibkr":
        from app.connectors.ibkr_connector import IBKRConnector
        return [IBKRConnector(credentials)]
    if platform == "evm_wallet":
        from app.connectors.evm_wallet_connector import EVMWalletConnector
        api_key = credentials.get("api_key") or os.environ.get("ALCHEMY_API_KEY", "")
        if not api_key:
            raise ValueError("ALCHEMY_API_KEY not set")
        addresses_raw = os.environ.get("EVM_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if not addresses:
            raise ValueError("EVM_WALLET_ADDRESSES not set in .env")
        chains_raw = os.environ.get("EVM_CHAINS", "ethereum")
        chains = [c.strip() for c in chains_raw.split(",") if c.strip()]
        return [EVMWalletConnector(addr, chain, api_key) for addr in addresses for chain in chains]
    raise ValueError(f"Unknown platform: {platform}")


def _ensure_sui_accounts(addresses: list[str], user_id: str) -> None:
    """Ensure each SUI wallet address has an account record in DB."""
    for addr in addresses:
        account_key = addr[:10] if len(addr) >= 10 else addr
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   SELECT id, %s, %s, %s FROM platforms WHERE name = 'sui_wallet'
                   ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                (account_key, addr, user_id),
            )


def _ensure_sol_accounts(addresses: list[str], user_id: str) -> None:
    """Ensure each Solana wallet address has an account record in DB."""
    for addr in addresses:
        account_key = addr[:10] if len(addr) >= 10 else addr
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   SELECT id, %s, %s, %s FROM platforms WHERE name = 'sol_wallet'
                   ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                (account_key, addr, user_id),
            )


def _ensure_evm_accounts(addresses: list[str], chains: list[str], user_id: str) -> None:
    """Ensure one account record per (address, chain) exists under evm_wallet platform."""
    from app.connectors.evm_wallet_connector import CHAIN_CONFIG
    for addr in addresses:
        addr_lower = addr.lower()
        for chain in chains:
            cfg = CHAIN_CONFIG.get(chain, {})
            short = cfg.get("short", chain)
            account_key = f"{addr_lower[:10]}_{short}"
            label = f"{addr} ({chain})"
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO accounts (platform_id, account_key, label, user_id)
                       SELECT id, %s, %s, %s FROM platforms WHERE name = 'evm_wallet'
                       ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                    (account_key, label, user_id),
                )


def _aggregate_categories(batch_id: str, user_id: str) -> None:
    """After all source runs finish, write category totals to category_snapshots.

    For each date touched by this batch, computes the category total using each
    platform's LATEST known value on or before that date — not just what this batch
    captured.  This preserves the "carry-forward" behaviour when not all platforms
    run on the same day (e.g. OKX monthly vs Binance daily).

    Skips any (date, category) that already has source='manual'.
    """
    from collections import defaultdict

    with get_conn() as conn:
        dates_rows = conn.execute("""
            SELECT DISTINCT acs.snapshot_date
            FROM account_snapshots acs
            WHERE acs.batch_id = %s
              AND acs.total_value IS NOT NULL
        """, (batch_id,)).fetchall()

    dates = [row["snapshot_date"] for row in dates_rows]
    if not dates:
        return

    now = _now()
    written = 0
    with get_conn() as conn:
        for snapshot_date in dates:
            # For each platform, get its latest total value on or before snapshot_date.
            # Dedup: per account, take only the latest record on the resolved date
            # to avoid double-counting when multiple batches ran on the same day.
            platform_values = conn.execute("""
                SELECT p.name, SUM(acs.total_value) AS total_value
                FROM account_snapshots acs
                JOIN accounts a ON acs.account_id = a.id
                JOIN platforms p ON a.platform_id = p.id
                WHERE acs.total_value IS NOT NULL
                  AND acs.currency = 'USD'
                  AND acs.snapshot_date = (
                      SELECT MAX(acs2.snapshot_date)
                      FROM account_snapshots acs2
                      JOIN accounts a2 ON acs2.account_id = a2.id
                      WHERE a2.platform_id = a.platform_id
                        AND acs2.snapshot_date <= %s
                        AND acs2.total_value IS NOT NULL
                        AND acs2.currency = 'USD'
                  )
                  AND acs.id = (
                      SELECT id FROM account_snapshots
                      WHERE account_id = acs.account_id
                        AND snapshot_date = acs.snapshot_date
                        AND total_value IS NOT NULL
                      ORDER BY created_at DESC LIMIT 1
                  )
                GROUP BY p.name
            """, (snapshot_date,)).fetchall()

            grouped: dict[str, float] = defaultdict(float)
            for row in platform_values:
                cat = PLATFORM_CATEGORY.get(row["name"])
                if cat:
                    grouped[cat] += row["total_value"] or 0.0

            for category, total_value in grouped.items():
                conn.execute(
                    """INSERT INTO category_snapshots
                       (id, snapshot_date, category, total_value, currency, source, batch_id, created_at, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (snapshot_date, category, user_id) DO UPDATE SET
                         total_value=EXCLUDED.total_value,
                         source=EXCLUDED.source,
                         batch_id=EXCLUDED.batch_id,
                         created_at=EXCLUDED.created_at
                       WHERE category_snapshots.source <> 'manual'""",
                    (str(uuid.uuid4()), snapshot_date, category, total_value, "USD", "auto", batch_id, now, user_id),
                )
                written += 1

    print(f"  [category_snapshots] Wrote {written} entries for batch {batch_id[:8]}")


def run_batch(platforms: list[str]) -> None:
    from config.settings import SYSTEM_OWNER_ID
    user_id = SYSTEM_OWNER_ID

    init_db()

    # Ensure wallet accounts exist in DB if needed
    if "sol_wallet" in platforms:
        addresses_raw = os.environ.get("SOL_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if addresses:
            _ensure_sol_accounts(addresses, user_id)
    if "sui_wallet" in platforms:
        addresses_raw = os.environ.get("SUI_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if addresses:
            _ensure_sui_accounts(addresses, user_id)
    if "evm_wallet" in platforms:
        addresses_raw = os.environ.get("EVM_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        chains_raw = os.environ.get("EVM_CHAINS", "ethereum")
        chains = [c.strip() for c in chains_raw.split(",") if c.strip()]
        if addresses:
            _ensure_evm_accounts(addresses, chains, user_id)

    batch_id = str(uuid.uuid4())
    started_at = _now()
    print(f"\n[Batch {batch_id[:8]}] Starting — {started_at}")
    print(f"Platforms: {', '.join(platforms)}\n")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s,%s,%s,%s)",
            (batch_id, started_at, "running", user_id),
        )

    results = []
    for platform in platforms:
        try:
            credentials = _get_credentials(user_id, platform)
            connectors = _get_connectors(platform, credentials)
        except Exception as e:
            print(f"  ✗ [{platform}] Setup error: {e}")
            continue

        for connector in connectors:
            label = f"{platform}/{connector.account_key}"
            print(f"  → [{label}] Fetching...")
            try:
                result = connector.run(batch_id, user_id)
                results.append(result)
                if result.status == "success":
                    print(f"  ✓ [{label}] Success")
                else:
                    print(f"  ✗ [{label}] Failed: {result.error_message}")
            except Exception as e:
                print(f"  ✗ [{label}] Connector error: {e}")

    # Determine batch final status
    statuses = [r.status for r in results]
    if not statuses:
        batch_status = "failed"
    elif all(s == "success" for s in statuses):
        batch_status = "success"
    elif any(s == "success" for s in statuses):
        batch_status = "partial"
    else:
        batch_status = "failed"

    # Aggregate account_snapshots → category_snapshots
    if batch_status in ("success", "partial"):
        _aggregate_categories(batch_id, user_id)

    finished_at = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE batches SET status=%s, finished_at=%s WHERE id=%s",
            (batch_status, finished_at, batch_id),
        )

    print(f"\n[Batch {batch_id[:8]}] Done — status: {batch_status}")
    success = sum(1 for r in results if r.status == "success")
    print(f"  {success}/{len(results)} source runs succeeded\n")

    _fetch_benchmarks()


def _fetch_benchmarks() -> None:
    """Incremental benchmark price update — only fetches dates missing from DB."""
    import subprocess
    print("[benchmarks] Updating benchmark prices...")
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "fetch_benchmarks.py")],
        cwd=str(_SCRIPTS_DIR.parent),
    )
    if result.returncode != 0:
        print("[benchmarks] Warning: fetch failed (non-critical)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run portfolio data ingestion batch")
    parser.add_argument("--platform", help="Run only a specific platform")
    args = parser.parse_args()

    platforms = [args.platform] if args.platform else ENABLED_PLATFORMS
    implemented = {"binance", "okx", "mexc", "bybit", "sui_wallet", "sol_wallet", "ibkr", "evm_wallet"}
    platforms = [p for p in platforms if p in implemented]

    if not platforms:
        print("No implemented platforms to run.")
    else:
        run_batch(platforms)
