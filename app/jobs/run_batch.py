"""
CLI entry point for running a data ingestion batch.

Usage:
    uv run python -m app.jobs.run_batch
    uv run python -m app.jobs.run_batch --platform binance
    uv run python -m app.jobs.run_batch --platform sui_wallet
"""

import argparse
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

from app.storage.sqlite import get_conn, init_db
from config.settings import ENABLED_PLATFORMS, ENV_PATH

load_dotenv(ENV_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_connectors(platform: str) -> list:
    """Return list of connector instances for a platform (SUI = one per address)."""
    if platform == "binance":
        from app.connectors.binance_connector import BinanceConnector
        return [BinanceConnector()]
    if platform == "okx":
        from app.connectors.okx_connector import OKXConnector
        return [OKXConnector()]
    if platform == "mexc":
        from app.connectors.mexc_connector import MexcConnector
        return [MexcConnector()]
    if platform == "bybit":
        from app.connectors.bybit_connector import BybitConnector
        return [BybitConnector()]
    if platform == "sui_wallet":
        from app.connectors.sui_wallet_connector import SuiWalletConnector
        addresses_raw = os.environ.get("SUI_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if not addresses:
            raise ValueError("SUI_WALLET_ADDRESSES not set in .env")
        return [SuiWalletConnector(addr) for addr in addresses]
    raise ValueError(f"Unknown platform: {platform}")


def _ensure_sui_accounts(addresses: list[str]) -> None:
    """Ensure each SUI wallet address has an account record in DB."""
    from app.storage.sqlite import get_conn
    for addr in addresses:
        account_key = addr[:10] if len(addr) >= 10 else addr
        with get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO accounts (platform_id, account_key, label)
                   SELECT id, ?, ? FROM platforms WHERE name = 'sui_wallet'""",
                (account_key, addr),
            )


def run_batch(platforms: list[str]) -> None:
    init_db()

    # Ensure SUI wallet accounts exist if needed
    if "sui_wallet" in platforms:
        addresses_raw = os.environ.get("SUI_WALLET_ADDRESSES", "")
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]
        if addresses:
            _ensure_sui_accounts(addresses)

    batch_id = str(uuid.uuid4())
    started_at = _now()
    print(f"\n[Batch {batch_id[:8]}] Starting — {started_at}")
    print(f"Platforms: {', '.join(platforms)}\n")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO batches (id, started_at, status) VALUES (?,?,?)",
            (batch_id, started_at, "running"),
        )

    results = []
    for platform in platforms:
        try:
            connectors = _get_connectors(platform)
        except Exception as e:
            print(f"  ✗ [{platform}] Setup error: {e}")
            continue

        for connector in connectors:
            label = f"{platform}/{connector.account_key}"
            print(f"  → [{label}] Fetching...")
            try:
                result = connector.run(batch_id)
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

    finished_at = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE batches SET status=?, finished_at=? WHERE id=?",
            (batch_status, finished_at, batch_id),
        )

    print(f"\n[Batch {batch_id[:8]}] Done — status: {batch_status}")
    success = sum(1 for r in results if r.status == "success")
    print(f"  {success}/{len(results)} source runs succeeded\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run portfolio data ingestion batch")
    parser.add_argument("--platform", help="Run only a specific platform")
    args = parser.parse_args()

    platforms = [args.platform] if args.platform else ENABLED_PLATFORMS
    implemented = {"binance", "okx", "mexc", "bybit", "sui_wallet"}
    platforms = [p for p in platforms if p in implemented]

    if not platforms:
        print("No implemented platforms to run.")
    else:
        run_batch(platforms)
