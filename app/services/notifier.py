"""Telegram notification service for batch execution summaries."""

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

from config.db import get_conn

log = logging.getLogger(__name__)

_AUTH_KEYWORDS = {"401", "403", "invalid api key", "authentication", "unauthorized", "invalid signature"}
_CONN_KEYWORDS = {"timeout", "connection refused", "connectionerror", "readtimeout", "timed out"}


def _classify_error(msg: str | None) -> str:
    if not msg:
        return "執行失敗"
    lower = msg.lower()
    if any(k in lower for k in _AUTH_KEYWORDS):
        return "認證失效"
    if any(k in lower for k in _CONN_KEYWORDS):
        return "連線失敗"
    return "執行失敗"


def _query_platform_summary(batch_ids: list[str]) -> dict:
    """Return {platform: {success: int, failed: int, sample_error: str|None}}."""
    if not batch_ids:
        return {}
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.name AS platform,
                    sr.status,
                    COUNT(DISTINCT sr.user_id) AS user_count,
                    MIN(sr.error_message) FILTER (WHERE sr.error_message IS NOT NULL) AS sample_error
                FROM source_runs sr
                JOIN accounts a ON sr.account_id = a.id
                JOIN platforms p ON a.platform_id = p.id
                WHERE sr.batch_id = ANY(%s)
                GROUP BY p.name, sr.status
                ORDER BY p.name
                """,
                (batch_ids,),
            ).fetchall()
    except Exception as e:
        log.warning("notifier: DB query failed: %s", e)
        return {}

    stats: dict[str, dict] = defaultdict(lambda: {"success": 0, "failed": 0, "sample_error": None})
    for row in rows:
        p = row["platform"]
        if row["status"] == "success":
            stats[p]["success"] += row["user_count"]
        else:
            stats[p]["failed"] += row["user_count"]
            if row["sample_error"] and not stats[p]["sample_error"]:
                stats[p]["sample_error"] = row["sample_error"]
    return dict(stats)


def _query_user_stats() -> dict | None:
    """Headcount for the daily report. Excludes the system owner."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM users WHERE NOT is_system) AS total,
                  (SELECT COUNT(DISTINCT uc.user_id)
                     FROM user_connectors uc JOIN users u ON u.id = uc.user_id
                    WHERE uc.status = 'active' AND NOT u.is_system) AS with_source,
                  (SELECT COUNT(*)
                     FROM subscriptions s JOIN users u ON u.id = s.user_id
                    WHERE s.status IN ('active', 'trialing') AND NOT u.is_system) AS subscribed
                """
            ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        log.warning("notifier: user stats query failed: %s", e)
        return None


def send_telegram(message: str) -> None:
    """Send a text message via Telegram Bot API. No-op if env vars not set."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("notifier: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        if not resp.ok:
            log.warning("notifier: Telegram API %s — %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.warning("notifier: failed to send Telegram message: %s", e)


def send_batch_summary(job_type: str, batch_ids: list[str]) -> None:
    """Query batch results from DB and push a Telegram summary to the admin."""
    if not batch_ids:
        return

    stats = _query_platform_summary(batch_ids)
    total = len(stats)
    failed_entries = [(p, s) for p, s in stats.items() if s["failed"] > 0]

    job_labels = {
        "daily": "Daily Batch",
        "monthly_yuanta": "Monthly Yuanta Batch",
        "admin": "Admin Batch",
        "smoke": "Smoke Test",
    }
    job_label = job_labels.get(job_type, job_type)
    ts = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%m/%d %H:%M") + " UTC+8"

    if total == 0:
        lines = [f"⚠️ {job_label} — 無可用資料（no source_runs）"]
    elif not failed_entries:
        lines = [f"✅ {job_label} 完成", f"平台：{total}/{total} 正常"]
    elif len(failed_entries) < total:
        success_count = total - len(failed_entries)
        lines = [f"⚠️ {job_label} 部分失敗", f"成功：{success_count}/{total} 平台", "失敗："]
        for platform, s in failed_entries:
            error_type = _classify_error(s["sample_error"])
            suffix = f"（{s['failed']} 位用戶）" if s["failed"] > 1 else ""
            lines.append(f"• {platform} — {error_type}{suffix}")
    else:
        lines = [f"🔴 {job_label} 全部失敗"]
        for platform, s in failed_entries:
            error_type = _classify_error(s["sample_error"])
            lines.append(f"• {platform} — {error_type}")

    # The daily run is the one report the admin actually reads every day, so it
    # carries the standing numbers too. Admin/smoke runs stay terse.
    if job_type == "daily":
        lines.extend(_daily_report_lines())

    lines.append(ts)
    send_telegram("\n".join(lines))


def _daily_report_lines() -> list[str]:
    """Headcount + GCP free-tier usage. Each part is skipped if unavailable."""
    lines: list[str] = []

    stats = _query_user_stats()
    if stats:
        lines.append(
            f"用戶：{stats['total']} 位"
            f"（{stats['with_source']} 位有來源 · {stats['subscribed']} 位訂閱中）"
        )

    try:
        from app.services import gcp_usage
        usage = gcp_usage.collect()
        if usage:
            lines.extend(gcp_usage.format_lines(usage))
    except Exception as e:
        log.warning("notifier: gcp usage unavailable: %s", e)

    return lines
