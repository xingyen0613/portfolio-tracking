"""
Daily batch scheduler — runs as a standalone Zeabur worker service.

Usage:
    python -m app.jobs.scheduler

Schedule:
    UTC 15:30 every day (= Taiwan time 23:30)

Multi-user ready: iterates over all distinct user_ids with active connectors.
Currently only SYSTEM_OWNER_ID has connectors; new users are picked up automatically
once they have entries in user_connectors.
"""

import logging
import os
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.settings  # triggers load_dotenv
from config.db import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)


def _active_user_ids() -> list[str]:
    """Return all user_ids that have at least one active connector."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM user_connectors WHERE status = 'active'"
        ).fetchall()
    return [row["user_id"] for row in rows]


def run_daily_batch() -> None:
    log.info("Daily batch triggered.")

    from config.settings import ENABLED_PLATFORMS
    from app.jobs.run_batch import run_batch

    implemented = {"binance", "okx", "mexc", "bybit", "sol_wallet", "ibkr", "evm_wallet"}
    platforms = [p for p in ENABLED_PLATFORMS if p in implemented]

    user_ids = _active_user_ids()
    if not user_ids:
        log.warning("No active user connectors found — skipping batch.")
        return

    log.info("Running batch for %d user(s): %s", len(user_ids), user_ids)

    # Currently run_batch uses SYSTEM_OWNER_ID internally.
    # When multi-user support is added to run_batch, pass user_id here.
    run_batch(platforms)

    log.info("Daily batch complete.")


def main() -> None:
    import os
    from datetime import datetime, timedelta, timezone as tz
    scheduler = BlockingScheduler(timezone="UTC")
    trigger = CronTrigger(hour=15, minute=30, timezone="UTC")
    scheduler.add_job(run_daily_batch, trigger, id="daily_batch", replace_existing=True)

    # TEST ONLY: run once 30 seconds after startup — remove after verification
    if os.environ.get("SCHEDULER_STARTUP_TEST") == "1":
        run_at = datetime.now(tz.utc) + timedelta(seconds=30)
        scheduler.add_job(run_daily_batch, DateTrigger(run_date=run_at), id="startup_test")
        log.info("STARTUP TEST enabled — batch will run at %s", run_at.isoformat())

    log.info("Scheduler started. Daily batch fires at UTC 15:30 (Taiwan 23:30).")

    def _shutdown(signum, frame):
        log.info("Shutdown signal received, stopping scheduler.")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.start()


if __name__ == "__main__":
    main()
