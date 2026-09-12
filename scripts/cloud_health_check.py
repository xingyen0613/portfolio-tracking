"""Dead-man's switch for the GCP daily batch — runs on the local Mac.

The Telegram batch summary is sent from Cloud Run itself, so when Cloud Run is
down (billing suspended, bad deploy, Scheduler misconfigured) nothing is sent at
all and "no bad news" silently means "nothing ran". That is exactly what happened
2026-08-30 → 2026-09-10: twelve days with no data and no alert.

This script runs from the local crontab — an independent failure domain — and
alerts only when the cloud batch did not write today. Silent when healthy.

The local cron batch (`python -m app.jobs.run_batch`) only ever runs for
SYSTEM_OWNER_ID, so "a non-system user has a category_snapshot dated today" is a
clean signal that the cloud track specifically did its job.

It checks *yesterday*, not today: the cloud batch runs 23:30-23:42 Taipei, which
leaves only ~13 minutes before the date rolls over. Checking the previous day
from a morning cron removes that coupling entirely — an outage that started last
night is still an outage this morning, and a 9-hour-late alert is irrelevant next
to the 12-day blind spot this exists to close.

Usage (crontab):
    0 9 * * * cd <repo> && uv run python scripts/cloud_health_check.py
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.notifier import send_telegram
from config.db import get_conn
from config.settings import SYSTEM_OWNER_ID


def main() -> int:
    parser = argparse.ArgumentParser(description="Alert if the GCP batch did not run.")
    parser.add_argument("--days-ago", type=int, default=1,
                        help="which day to check (default: 1 = yesterday)")
    args = parser.parse_args()
    target = (date.today() - timedelta(days=args.days_ago)).isoformat()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS cloud_users
              FROM category_snapshots
             WHERE snapshot_date = %s
               AND user_id <> %s
            """,
            (target, SYSTEM_OWNER_ID),
        ).fetchone()
        expected = conn.execute(
            """
            SELECT COUNT(DISTINCT uc.user_id) AS n
              FROM user_connectors uc
             WHERE uc.status = 'active'
               AND uc.user_id <> %s
            """,
            (SYSTEM_OWNER_ID,),
        ).fetchone()

    cloud_users = row["cloud_users"] if row else 0
    expected_users = expected["n"] if expected else 0

    if cloud_users == 0 and expected_users > 0:
        send_telegram(
            "🔴 雲端 batch 沒有跑\n"
            f"{target} 的 category_snapshots 沒有任何非 system 用戶資料"
            f"（預期 {expected_users} 位）。\n"
            "Cloud Run 或 Cloud Scheduler 可能已停擺 — 請檢查 GCP billing 與服務狀態。"
        )
        print(f"[health] ALERT sent — 0/{expected_users} cloud users on {target}")
        return 1

    print(f"[health] OK — {cloud_users}/{expected_users} cloud users on {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
