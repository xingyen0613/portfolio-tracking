"""
CLI entry point for running a data ingestion batch.

Usage:
    uv run python -m app.jobs.run_batch
    uv run python -m app.jobs.run_batch --platform binance
"""

import argparse
import uuid
from datetime import datetime, timezone

from app.storage.sqlite import get_conn, init_db
from config.settings import ENABLED_PLATFORMS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_connector(platform: str):
    if platform == "binance":
        from app.connectors.binance_connector import BinanceConnector
        return BinanceConnector()
    if platform == "okx":
        from app.connectors.okx_connector import OKXConnector
        return OKXConnector()
    raise ValueError(f"Unknown platform: {platform}")


def run_batch(platforms: list[str]) -> None:
    init_db()

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
        print(f"  → [{platform}] Fetching...")
        try:
            connector = _get_connector(platform)
            result = connector.run(batch_id)
            results.append(result)
            if result.status == "success":
                print(f"  ✓ [{platform}] Success")
            else:
                print(f"  ✗ [{platform}] Failed: {result.error_message}")
        except Exception as e:
            print(f"  ✗ [{platform}] Connector error: {e}")

    # Determine batch final status
    statuses = [r.status for r in results]
    if all(s == "success" for s in statuses):
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
    print(f"  {success}/{len(results)} platforms succeeded\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run portfolio data ingestion batch")
    parser.add_argument("--platform", help="Run only a specific platform")
    args = parser.parse_args()

    platforms = [args.platform] if args.platform else ENABLED_PLATFORMS
    # Filter to only implemented connectors for now
    implemented = {"binance", "okx"}
    platforms = [p for p in platforms if p in implemented]

    if not platforms:
        print("No implemented platforms to run.")
    else:
        run_batch(platforms)
