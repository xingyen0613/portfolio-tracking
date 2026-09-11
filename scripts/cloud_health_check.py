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

Usage (crontab, after the 23:30 Taipei Cloud Scheduler run):
    55 23 * * * cd <repo> && uv run python scripts/cloud_health_check.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.notifier import send_telegram
from config.db import get_conn
from config.settings import SYSTEM_OWNER_ID


def main() -> int:
    today = date.today().isoformat()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS cloud_users
              FROM category_snapshots
             WHERE snapshot_date = %s
               AND user_id <> %s
            """,
            (today, SYSTEM_OWNER_ID),
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
            "🔴 雲端 batch 今天沒有跑\n"
            f"{today} 的 category_snapshots 沒有任何非 system 用戶資料"
            f"（預期 {expected_users} 位）。\n"
            "Cloud Run 或 Cloud Scheduler 可能已停擺 — 請檢查 GCP billing 與服務狀態。"
        )
        print(f"[health] ALERT sent — 0/{expected_users} cloud users on {today}")
        return 1

    print(f"[health] OK — {cloud_users}/{expected_users} cloud users on {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
