"""Rebuild category_snapshots for specific dates from account_snapshots.

Used after manual CSV imports to ensure the portfolio history chart reflects
newly written account-level data. Unlike _aggregate_categories in run_batch.py,
this function:
  - accepts an explicit list of dates instead of a batch_id
  - does NOT apply the source <> 'manual' guard, so account-level imports
    override any previously entered category-level manual values
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from config.settings import PLATFORM_CATEGORY


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rebuild_for_dates(conn, user_id: str, dates: list[str]) -> int:
    """Recompute category_snapshots for the given dates.

    Uses fill-forward semantics identical to _aggregate_categories:
    for each platform, picks the most recent snapshot_date <= target date.

    Returns the number of category_snapshots rows upserted.
    """
    if not dates:
        return 0

    now = _now()
    written = 0

    for snapshot_date in dates:
        platform_values = conn.execute(
            """
            SELECT p.name, SUM(acs.total_value) AS total_value
            FROM account_snapshots acs
            JOIN accounts a ON acs.account_id = a.id
            JOIN platforms p ON a.platform_id = p.id
            WHERE acs.total_value IS NOT NULL
              AND acs.currency = 'USD'
              AND acs.user_id = %s
              AND acs.snapshot_date = (
                  SELECT MAX(acs2.snapshot_date)
                  FROM account_snapshots acs2
                  JOIN accounts a2 ON acs2.account_id = a2.id
                  WHERE a2.platform_id = a.platform_id
                    AND acs2.user_id = %s
                    AND acs2.snapshot_date <= %s
                    AND acs2.total_value IS NOT NULL
                    AND acs2.currency = 'USD'
              )
              AND acs.id = (
                  SELECT id FROM account_snapshots
                  WHERE account_id = acs.account_id
                    AND snapshot_date = acs.snapshot_date
                    AND total_value IS NOT NULL
                    AND user_id = acs.user_id
                  ORDER BY created_at DESC LIMIT 1
              )
            GROUP BY p.name
            """,
            (user_id, user_id, snapshot_date),
        ).fetchall()

        grouped: dict[str, float] = defaultdict(float)
        for row in platform_values:
            cat = PLATFORM_CATEGORY.get(row["name"])
            if cat:
                grouped[cat] += row["total_value"] or 0.0

        for category, total_value in grouped.items():
            conn.execute(
                """
                INSERT INTO category_snapshots
                  (id, snapshot_date, category, total_value, currency,
                   source, batch_id, created_at, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_date, category, user_id) DO UPDATE SET
                  total_value = EXCLUDED.total_value,
                  source      = EXCLUDED.source,
                  batch_id    = EXCLUDED.batch_id,
                  created_at  = EXCLUDED.created_at
                """,
                (
                    str(uuid.uuid4()), snapshot_date, category,
                    total_value, "USD", "auto", None, now, user_id,
                ),
            )
            written += 1

    return written
