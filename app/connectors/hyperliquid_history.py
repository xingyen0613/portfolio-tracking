"""
Hyperliquid 歷史資產回補 — 只在初次連接某地址時觸發一次。

資料來源：info endpoint 的 `portfolio` type，回傳 8 組曲線：
    day / week / month / allTime          → 帳戶總值（現貨＋永續）
    perpDay / perpWeek / perpMonth / perpAllTime → 僅永續部分

回補採用 `allTime`，因為只有它能涵蓋一年範圍。實測其尾值與
clearinghouseState + 現貨市值算出的總資產一致，故可直接當帳戶總值寫入。

取樣密度的先天限制（官方行為，非本模組可控）：
    Hyperliquid 的 allTime 大約固定回傳 ~100 個點，帳戶越老間隔越稀。
    帳戶年齡 ~75 天  → 約每日一點
    帳戶年齡 ~3 年   → 約每 14 天一點
本模組按日聚合（同日取最後一點），因此實際寫入天數受此限制。
官方另註明 portfolio 曲線在出入金與每 15 分鐘取樣，適合畫圖，
不適合當精算帳本。

之後的每日數值由日常 batch 累積，不再重複回補。
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests

from config.db import get_conn

log = logging.getLogger(__name__)

API_URL = "https://api.hyperliquid.xyz/info"
BACKFILL_DAYS = 365


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_portfolio(address: str) -> list | None:
    try:
        resp = requests.post(
            API_URL, json={"type": "portfolio", "user": address}, timeout=25
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("hyperliquid portfolio fetch failed for %s: %s", address[:10], e)
        return None


def _daily_series(portfolio: list, days: int) -> dict[str, float]:
    """從 allTime 曲線取最近 N 天，按日聚合（同日取最後一點）。"""
    if not isinstance(portfolio, list):
        return {}

    history = None
    for entry in portfolio:
        if isinstance(entry, list) and len(entry) == 2 and entry[0] == "allTime":
            data = entry[1]
            if isinstance(data, dict):
                history = data.get("accountValueHistory")
            break
    if not history:
        return {}

    cutoff_ms = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    by_date: dict[str, tuple[int, float]] = {}
    for point in history:
        if not (isinstance(point, list) and len(point) == 2):
            continue
        try:
            ts = int(point[0])
            value = float(point[1])
        except (TypeError, ValueError):
            continue
        if ts < cutoff_ms:
            continue
        date_str = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d")
        # 同一天多個點取時間最晚的那個
        if date_str not in by_date or ts > by_date[date_str][0]:
            by_date[date_str] = (ts, value)

    return {d: v for d, (_, v) in by_date.items()}


def backfill_history(addresses: list[str], user_id: str, days: int = BACKFILL_DAYS) -> dict:
    """為初次連接的地址回補歷史 account_snapshots。

    已存在的日期一律跳過 —— 既有資料是不可變的歷史紀錄，且當日快照
    由 batch 寫入，較歷史曲線精確。
    """
    written_dates: list[str] = []
    skipped = 0

    for address in addresses:
        account_key = address[:10] if len(address) >= 10 else address

        portfolio = _fetch_portfolio(address)
        if portfolio is None:
            continue

        series = _daily_series(portfolio, days)
        if not series:
            log.info("hyperliquid backfill: no history points for %s", account_key)
            continue

        with get_conn() as conn:
            acct = conn.execute(
                """SELECT a.id FROM accounts a
                   JOIN platforms p ON a.platform_id = p.id
                   WHERE p.name='hyperliquid' AND a.account_key=%s AND a.user_id=%s""",
                (account_key, user_id),
            ).fetchone()
            if not acct:
                log.warning("hyperliquid backfill: account row missing for %s", account_key)
                continue
            account_id = acct["id"]

            batch_id = str(uuid.uuid4())
            started_at = _now()
            conn.execute(
                "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s, %s, %s, %s)",
                (batch_id, started_at, "running", user_id),
            )

            for date_str, value in sorted(series.items()):
                existing = conn.execute(
                    "SELECT 1 FROM account_snapshots WHERE account_id=%s AND snapshot_date=%s LIMIT 1",
                    (account_id, date_str),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue

                conn.execute(
                    """INSERT INTO account_snapshots
                         (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (str(uuid.uuid4()), batch_id, account_id, date_str,
                     round(value, 6), "USD", started_at, user_id),
                )
                written_dates.append(date_str)

            conn.execute(
                "UPDATE batches SET status='success', finished_at=%s WHERE id=%s",
                (_now(), batch_id),
            )

    # 重建受影響日期的 category_snapshots（歷史折線圖用）
    if written_dates:
        try:
            from app.jobs.rebuild_category_snapshots import rebuild_for_dates
            with get_conn() as conn:
                rebuild_for_dates(conn, user_id, written_dates)
        except Exception:
            log.exception("rebuild_for_dates failed after hyperliquid backfill — chart may be stale")

    return {
        "written_count": len(written_dates),
        "skipped_count": skipped,
        "date_from": min(written_dates) if written_dates else None,
        "date_to": max(written_dates) if written_dates else None,
    }
