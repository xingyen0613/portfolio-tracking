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

from app.utils.fx import ensure_updated
from config.db import get_conn
from config.settings import ENABLED_PLATFORMS, ENV_PATH, PLATFORM_CATEGORY, WALLETS_ENV_PATH

load_dotenv(ENV_PATH)
load_dotenv(WALLETS_ENV_PATH, override=True)


class SystemConfigError(RuntimeError):
    """Server-side misconfiguration (e.g. missing system-wide API key).

    These are admin/ops problems, not user problems — they must not be
    written into `user_connectors.last_error` or shown in the UI.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def active_batch_user_ids() -> list[str]:
    """user_ids eligible for an automated batch run.

    Single source of truth shared by the scheduler and every trigger endpoint:
    a user must have an active connector AND an active subscription entitlement.
    Users without entitlement keep their history but are skipped (no further
    updates) — see app.services.entitlements. Callers wanting to force a specific
    user (e.g. admin manual trigger) should bypass this and pass the user_id directly.
    """
    import logging
    from app.services.entitlements import is_active

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM user_connectors WHERE status = 'active'"
        ).fetchall()
    candidates = [row["user_id"] for row in rows]

    entitled = [uid for uid in candidates if is_active(uid)]
    skipped = [uid for uid in candidates if uid not in entitled]
    if skipped:
        logging.getLogger(__name__).info(
            "Skipping %d user(s) without active subscription: %s", len(skipped), skipped
        )
    return entitled


def _get_user_connectors(user_id: str, platform_name: str) -> list[dict]:
    """
    Return all active user_connectors rows for (user_id, platform_name).

    Each row: {id, account_key, label, credentials} (credentials decrypted dict).
    """
    from app.auth.encryption import decrypt
    rows = []
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """SELECT id, account_key, label, credentials_json
                   FROM user_connectors
                   WHERE user_id=%s AND platform_name=%s AND status='active'
                   ORDER BY created_at""",
                (user_id, platform_name),
            )
            for row in cur.fetchall():
                creds = {}
                if row["credentials_json"]:
                    try:
                        creds = json.loads(decrypt(row["credentials_json"]))
                    except Exception:
                        pass
                rows.append({
                    "id": row["id"],
                    "account_key": row["account_key"],
                    "label": row["label"],
                    "credentials": creds,
                })
    except Exception:
        pass
    return rows


def _instantiate_connectors(platform: str, credentials: dict, account_key: str) -> list:
    """Return list of connector instances for a single user_connectors row.

    Wallet platforms expand into multiple instances (one per address × chain).
    Exchange/IBKR return a single instance carrying the user's account_key.
    """
    if platform == "binance":
        from app.connectors.binance_connector import BinanceConnector
        return [BinanceConnector(credentials, account_key=account_key)]
    if platform == "okx":
        from app.connectors.okx_connector import OKXConnector
        return [OKXConnector(credentials, account_key=account_key)]
    if platform == "mexc":
        from app.connectors.mexc_connector import MexcConnector
        return [MexcConnector(credentials, account_key=account_key)]
    if platform == "bybit":
        from app.connectors.bybit_connector import BybitConnector
        return [BybitConnector(credentials, account_key=account_key)]
    if platform == "pionex":
        from app.connectors.pionex_connector import PionexConnector
        return [PionexConnector(credentials, account_key=account_key)]
    if platform == "ibkr":
        from app.connectors.ibkr_connector import IBKRConnector
        return [IBKRConnector(credentials, account_key=account_key)]
    if platform == "sinopac":
        from app.connectors.sinopac_connector import SinopacStockConnector
        return [SinopacStockConnector(credentials, account_key=account_key)]
    if platform == "fubon":
        from app.connectors.fubon_connector import FubonConnector
        return [FubonConnector(credentials, account_key=account_key)]
    if platform == "yuanta":
        from app.connectors.yuanta_connector import YuantaConnector
        return [YuantaConnector(credentials, account_key=account_key)]
    if platform == "sui_wallet":
        from app.connectors.sui_wallet_connector import SuiWalletConnector
        addresses = credentials.get("addresses") or []
        if not addresses:
            raise ValueError("sui_wallet credentials.addresses is required")
        return [SuiWalletConnector(addr) for addr in addresses]
    if platform == "hyperliquid":
        from app.connectors.hyperliquid_connector import HyperliquidConnector
        addresses = credentials.get("addresses") or []
        if not addresses:
            raise ValueError("hyperliquid credentials.addresses is required")
        return [HyperliquidConnector(addr) for addr in addresses]
    if platform == "sol_wallet":
        from app.connectors.sol_wallet_connector import SolWalletConnector
        # Alchemy is a system-level read-only query tool shared by all users
        api_key = os.environ.get("ALCHEMY_API_KEY", "")
        if not api_key:
            raise SystemConfigError("ALCHEMY_API_KEY not set on server")
        addresses = credentials.get("addresses") or [
            a.strip() for a in os.environ.get("SOL_WALLET_ADDRESSES", "").split(",") if a.strip()
        ]
        if not addresses:
            raise ValueError("SOL_WALLET_ADDRESSES not configured in user_connectors or env")
        return [SolWalletConnector(addr, api_key) for addr in addresses]
    if platform == "evm_wallet":
        from app.connectors.evm_wallet_connector import EVMWalletConnector, DEFAULT_EVM_CHAINS
        # Alchemy is a system-level read-only query tool shared by all users
        api_key = os.environ.get("ALCHEMY_API_KEY", "")
        if not api_key:
            raise SystemConfigError("ALCHEMY_API_KEY not set on server")
        addresses = credentials.get("addresses") or [
            a.strip() for a in os.environ.get("EVM_WALLET_ADDRESSES", "").split(",") if a.strip()
        ]
        if not addresses:
            raise ValueError("EVM_WALLET_ADDRESSES not configured in user_connectors or env")
        chains = credentials.get("chains") or [
            c.strip() for c in os.environ.get("EVM_CHAINS", "").split(",") if c.strip()
        ] or DEFAULT_EVM_CHAINS
        return [EVMWalletConnector(addr, chain, api_key) for addr in addresses for chain in chains]
    raise ValueError(f"Unknown platform: {platform}")


def _ensure_sui_accounts(addresses: list[str], user_id: str) -> None:
    for addr in addresses:
        account_key = addr[:10] if len(addr) >= 10 else addr
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   SELECT id, %s, %s, %s FROM platforms WHERE name = 'sui_wallet'
                   ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                (account_key, addr, user_id),
            )


def _ensure_hyperliquid_accounts(addresses: list[str], user_id: str) -> None:
    for addr in addresses:
        account_key = addr[:10] if len(addr) >= 10 else addr
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   SELECT id, %s, %s, %s FROM platforms WHERE name = 'hyperliquid'
                   ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                (account_key, addr, user_id),
            )


def _ensure_sol_accounts(addresses: list[str], user_id: str) -> None:
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


def _ensure_exchange_or_ibkr_account(platform: str, account_key: str, label: str | None, user_id: str) -> None:
    """For exchanges and IBKR, ensure the account row exists with the user-given key."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO accounts (platform_id, account_key, label, user_id)
               SELECT id, %s, %s, %s FROM platforms WHERE name = %s
               ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
            (account_key, label, user_id, platform),
        )


def _aggregate_categories(batch_id: str, user_id: str) -> None:
    """After all source runs finish, write category totals to category_snapshots."""
    from collections import defaultdict
    from app.utils.fx import get_latest_fx_rate

    with get_conn() as conn:
        dates_rows = conn.execute("""
            SELECT DISTINCT acs.snapshot_date
            FROM account_snapshots acs
            WHERE acs.batch_id = %s
              AND acs.total_value IS NOT NULL
        """, (batch_id,)).fetchall()

    from datetime import date as _date, timedelta
    dates = {str(row["snapshot_date"]) for row in dates_rows}
    today = _date.today().isoformat()
    if dates:
        # If batch contains historical dates, fill the gap from batch's last date
        # to today so carry-forward is continuous and the chart has no sudden jumps.
        last_batch = _date.fromisoformat(max(dates))
        fill = last_batch + timedelta(days=1)
        while fill.isoformat() <= today:
            dates.add(fill.isoformat())
            fill += timedelta(days=1)
    else:
        dates.add(today)
    dates = sorted(dates)

    fx_rate = get_latest_fx_rate()  # TWD per USD
    now = _now()
    written = 0
    with get_conn() as conn:
        for snapshot_date in dates:
            platform_values = conn.execute("""
                SELECT p.name, acs.currency, SUM(acs.total_value) AS total_value
                FROM account_snapshots acs
                JOIN accounts a ON acs.account_id = a.id
                JOIN platforms p ON a.platform_id = p.id
                WHERE acs.total_value IS NOT NULL
                  AND acs.currency IN ('USD', 'TWD')
                  AND acs.user_id = %s
                  AND acs.snapshot_date = (
                      SELECT MAX(acs2.snapshot_date)
                      FROM account_snapshots acs2
                      JOIN accounts a2 ON acs2.account_id = a2.id
                      WHERE a2.platform_id = a.platform_id
                        AND acs2.user_id = %s
                        AND acs2.snapshot_date <= %s
                        AND acs2.total_value IS NOT NULL
                        AND acs2.currency = acs.currency
                  )
                  AND acs.id = (
                      SELECT id FROM account_snapshots
                      WHERE account_id = acs.account_id
                        AND snapshot_date = acs.snapshot_date
                        AND total_value IS NOT NULL
                      ORDER BY created_at DESC LIMIT 1
                  )
                GROUP BY p.name, acs.currency
            """, (user_id, user_id, snapshot_date)).fetchall()

            grouped: dict[str, float] = defaultdict(float)
            for row in platform_values:
                cat = PLATFORM_CATEGORY.get(row["name"])
                if not cat:
                    continue
                value = row["total_value"] or 0.0
                # Convert TWD to USD
                if row["currency"] == "TWD":
                    value = value / fx_rate
                grouped[cat] += value

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


def _update_connector_health(user_id: str, platform: str, account_key: str,
                             ok: bool, error_msg: str | None) -> None:
    """Update user_connectors with latest sync result."""
    with get_conn() as conn:
        if ok:
            conn.execute(
                """UPDATE user_connectors
                   SET last_sync_at = NOW(), last_error = NULL, last_error_at = NULL
                   WHERE user_id=%s AND platform_name=%s AND account_key=%s""",
                (user_id, platform, account_key),
            )
        else:
            conn.execute(
                """UPDATE user_connectors
                   SET last_error = %s, last_error_at = NOW()
                   WHERE user_id=%s AND platform_name=%s AND account_key=%s""",
                (error_msg, user_id, platform, account_key),
            )


def run_batch(platforms: list[str], user_id: str,
              connector_ids: list[str] | None = None) -> str:
    """
    Run an ingestion batch for one user.

    platforms: which platforms to run (filtered to whatever connectors the user actually has).
    connector_ids: if specified, only run these specific user_connectors rows
                   (used for single-connector immediate test-fetch after POST).

    Returns batch_id.
    """
    batch_id = str(uuid.uuid4())
    started_at = _now()
    print(f"\n[Batch {batch_id[:8]}] user={user_id[:8]} starting — {started_at}")
    print(f"Platforms: {', '.join(platforms)}\n")

    # Refresh FX rates as part of the daily batch (primary refresh point).
    # ensure_updated() is self-guarding: it only hits the network when the DB
    # rate is stale, so running it per-user is a no-op after the first call.
    # Never let an FX fetch failure abort the batch.
    try:
        ensure_updated()
    except Exception as e:
        print(f"[Batch {batch_id[:8]}] FX refresh skipped: {e}")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s,%s,%s,%s)",
            (batch_id, started_at, "running", user_id),
        )

    results = []

    for platform in platforms:
        connector_rows = _get_user_connectors(user_id, platform)
        if connector_ids:
            connector_rows = [r for r in connector_rows if r["id"] in connector_ids]
        if not connector_rows:
            continue

        for row in connector_rows:
            account_key = row["account_key"]
            label = row["label"]
            creds = row["credentials"]

            # Ensure accounts row exists for this connector
            try:
                if platform in ("binance", "okx", "mexc", "bybit", "pionex", "ibkr", "sinopac", "fubon", "yuanta"):
                    _ensure_exchange_or_ibkr_account(platform, account_key, label, user_id)
                elif platform == "sol_wallet":
                    addresses = creds.get("addresses") or [
                        a.strip() for a in os.environ.get("SOL_WALLET_ADDRESSES", "").split(",") if a.strip()
                    ]
                    if addresses:
                        _ensure_sol_accounts(addresses, user_id)
                elif platform == "evm_wallet":
                    from app.connectors.evm_wallet_connector import DEFAULT_EVM_CHAINS
                    addresses = creds.get("addresses") or [
                        a.strip() for a in os.environ.get("EVM_WALLET_ADDRESSES", "").split(",") if a.strip()
                    ]
                    chains = creds.get("chains") or [
                        c.strip() for c in os.environ.get("EVM_CHAINS", "").split(",") if c.strip()
                    ] or DEFAULT_EVM_CHAINS
                    if addresses:
                        _ensure_evm_accounts(addresses, chains, user_id)
                elif platform == "sui_wallet":
                    addresses = creds.get("addresses") or []
                    if addresses:
                        _ensure_sui_accounts(addresses, user_id)
                elif platform == "hyperliquid":
                    addresses = creds.get("addresses") or []
                    if addresses:
                        _ensure_hyperliquid_accounts(addresses, user_id)
            except Exception as e:
                print(f"  ✗ [{platform}/{account_key}] account setup error: {e}")

            # Instantiate and run connector(s) for this row
            try:
                connectors = _instantiate_connectors(platform, creds, account_key)
            except SystemConfigError as e:
                # Server-side misconfig — log only, do NOT touch user_connectors.last_error
                print(f"  ⚠ [{platform}/{account_key}] system config error (not user-facing): {e}")
                continue
            except Exception as e:
                msg = f"Setup error: {e}"
                print(f"  ✗ [{platform}/{account_key}] {msg}")
                _update_connector_health(user_id, platform, account_key, False, str(e))
                continue

            row_ok = True
            row_err = None
            for connector in connectors:
                tag = f"{platform}/{connector.account_key}"
                print(f"  → [{tag}] Fetching...")
                try:
                    result = connector.run(batch_id, user_id)
                    results.append(result)
                    if result.status == "success":
                        print(f"  ✓ [{tag}] Success")
                    else:
                        print(f"  ✗ [{tag}] Failed: {result.error_message}")
                        row_ok = False
                        row_err = result.error_message
                except Exception as e:
                    print(f"  ✗ [{tag}] Connector error: {e}")
                    row_ok = False
                    row_err = str(e)

            _update_connector_health(user_id, platform, account_key, row_ok, row_err)

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

    return batch_id


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
    from config.settings import SYSTEM_OWNER_ID

    parser = argparse.ArgumentParser(description="Run portfolio data ingestion batch")
    parser.add_argument("--platform", help="Run only a specific platform")
    parser.add_argument("--user-id", default=SYSTEM_OWNER_ID, help="User ID (default: SYSTEM_OWNER_ID)")
    args = parser.parse_args()

    platforms = [args.platform] if args.platform else ENABLED_PLATFORMS
    implemented = {"binance", "okx", "mexc", "bybit", "pionex", "sui_wallet", "sol_wallet", "ibkr", "evm_wallet", "hyperliquid", "sinopac", "fubon", "yuanta"}
    platforms = [p for p in platforms if p in implemented]

    if not platforms:
        print("No implemented platforms to run.")
    else:
        run_batch(platforms, args.user_id)
        _fetch_benchmarks()
