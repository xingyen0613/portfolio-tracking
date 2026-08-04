"""Historical data import endpoint.

POST /api/connectors/{connector_id}/historical-import
  Accepts a CSV file (date, total_value) and writes account_snapshots for
  a specific connector, then rebuilds category_snapshots for the affected dates.

Query parameters (form fields):
  file              - CSV file upload
  currency          - "USD" or "TWD"  (entire CSV uses the same currency)
  conflict_strategy - "skip" (default) or "override"
                        skip:     dates with existing snapshots are left untouched
                        override: existing snapshots for those dates are deleted first
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from app.auth.deps import get_current_user
from app.jobs.rebuild_category_snapshots import rebuild_for_dates
from app.utils.csv_import import parse_csv
from config.db import get_conn

router = APIRouter()

WALLET_PLATFORMS = {"evm_wallet", "sol_wallet", "sui_wallet"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fill_to_today(written_dates: list[str]) -> list[str]:
    """Extend the written dates up to today so carry-forward is continuous.

    A manual/CSV source only has values on the dates present in the file. The
    aggregation query in rebuild_for_dates already carries the most recent
    snapshot forward, but it only runs on the dates it is given — so without
    this, the imported value would vanish from the chart the day after the last
    CSV row. Mirrors the gap-filling in run_batch._aggregate_categories.
    """
    dates = set(written_dates)
    today = date.today().isoformat()
    fill = date.fromisoformat(max(dates)) + timedelta(days=1)
    while fill.isoformat() <= today:
        dates.add(fill.isoformat())
        fill += timedelta(days=1)
    return sorted(dates)


def _get_account_id(conn, platform: str, account_key: str, user_id: str) -> int | None:
    """Read-only lookup — does NOT create the account."""
    row = conn.execute(
        """SELECT a.id FROM accounts a
           JOIN platforms p ON a.platform_id = p.id
           WHERE p.name = %s AND a.account_key = %s AND a.user_id = %s""",
        (platform, account_key, user_id),
    ).fetchone()
    return row["id"] if row else None


def _ensure_account(conn, platform: str, account_key: str, label: str | None, user_id: str) -> int:
    """Ensure the account row exists and return its id."""
    conn.execute(
        """INSERT INTO accounts (platform_id, account_key, label, user_id)
           SELECT id, %s, %s, %s FROM platforms WHERE name = %s
           ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
        (account_key, label, user_id, platform),
    )
    row = conn.execute(
        """SELECT a.id FROM accounts a
           JOIN platforms p ON a.platform_id = p.id
           WHERE p.name = %s AND a.account_key = %s AND a.user_id = %s""",
        (platform, account_key, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not find or create account for connector",
        )
    return row["id"]


@router.post("/{connector_id}/historical-import")
async def import_historical_data(
    connector_id: str,
    file: UploadFile,
    currency: str = Form(...),
    conflict_strategy: str = Form("skip"),
    dry_run: bool = Form(False),
    current_user: dict = Depends(get_current_user),
):
    """Import historical CSV data for a connector.

    CSV must have columns: date (YYYY-MM-DD), total_value (numeric).
    Values are stored in USD; TWD values are converted using historical fx_rates.
    """
    user_id = current_user["id"]

    if currency not in ("USD", "TWD"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "currency must be 'USD' or 'TWD'")
    if conflict_strategy not in ("skip", "override"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "conflict_strategy must be 'skip' or 'override'"
        )

    # Look up connector
    with get_conn() as conn:
        connector = conn.execute(
            """SELECT platform_name, account_key, label
               FROM user_connectors WHERE id = %s AND user_id = %s""",
            (connector_id, user_id),
        ).fetchone()

    if not connector:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found")

    platform = connector["platform_name"]

    if platform in WALLET_PLATFORMS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Historical CSV import is not supported for wallet connectors ({platform}). "
            "Use exchange or brokerage connectors.",
        )

    # Read file with size cap to avoid buffering huge uploads before parsing
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 5 MB limit"
        )

    parse_result = parse_csv(content)

    if not parse_result.rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "detail": "No valid rows found in CSV",
                "invalid_rows": parse_result.invalid_rows,
            },
        )

    # Dry-run: check conflicts without writing anything
    if dry_run:
        with get_conn() as conn:
            account_id = _get_account_id(conn, platform, connector["account_key"], user_id)
            conflicting: list[str] = []
            if account_id is not None:
                for row_data in parse_result.rows:
                    existing = conn.execute(
                        "SELECT 1 FROM account_snapshots WHERE account_id = %s AND snapshot_date = %s LIMIT 1",
                        (account_id, row_data["date"]),
                    ).fetchone()
                    if existing:
                        conflicting.append(row_data["date"])
        return {
            "dry_run": True,
            "total_parsed": len(parse_result.rows),
            "conflicting_dates": conflicting,
            "invalid_rows": parse_result.invalid_rows,
        }

    # Preload fx_rates series for TWD conversion (single query for all dates)
    fx_series = None
    if currency == "TWD":
        from app.utils.fx import get_fx_rates_series
        fx_series = get_fx_rates_series()

    batch_id = str(uuid.uuid4())
    started_at = _now()

    written_dates: list[str] = []
    skipped_dates: list[str] = []

    with get_conn() as conn:
        # Create batch record
        conn.execute(
            "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s, %s, %s, %s)",
            (batch_id, started_at, "running", user_id),
        )

        # Ensure account exists
        account_id = _ensure_account(
            conn, platform, connector["account_key"], connector["label"], user_id
        )

        for row_data in parse_result.rows:
            date_str: str = row_data["date"]
            raw_value: float = row_data["total_value"]

            # Convert to USD (round to 6 dp to avoid float precision noise)
            if currency == "TWD":
                from app.utils.fx import lookup_rate
                rate = lookup_rate(date_str, fx_series)
                value_usd = round(raw_value / rate, 6)
            else:
                value_usd = round(raw_value, 6)

            # Check for existing snapshot on this date
            existing = conn.execute(
                "SELECT id FROM account_snapshots WHERE account_id = %s AND snapshot_date = %s LIMIT 1",
                (account_id, date_str),
            ).fetchone()

            if existing:
                if conflict_strategy == "skip":
                    skipped_dates.append(date_str)
                    continue
                # override: remove all existing snapshots for this account+date
                conn.execute(
                    "DELETE FROM account_snapshots WHERE account_id = %s AND snapshot_date = %s",
                    (account_id, date_str),
                )

            conn.execute(
                """INSERT INTO account_snapshots
                     (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()), batch_id, account_id, date_str,
                    value_usd, "USD", started_at, user_id,
                ),
            )
            written_dates.append(date_str)

        # Mark batch complete
        conn.execute(
            "UPDATE batches SET status = %s, finished_at = %s WHERE id = %s",
            ("success", _now(), batch_id),
        )

    # Rebuild category_snapshots for affected dates (separate transaction after commit).
    # Account-level data is already committed; if rebuild fails the chart may be stale
    # but the underlying data is correct and rebuild will succeed on next auto-batch.
    if written_dates:
        try:
            with get_conn() as conn:
                rebuild_for_dates(conn, user_id, _fill_to_today(written_dates))
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "rebuild_for_dates failed after import %s — chart may be stale", batch_id
            )

    all_dates = written_dates + skipped_dates
    return {
        "import_id": batch_id,
        "written_count": len(written_dates),
        "skipped_count": len(skipped_dates),
        "date_from": min(all_dates) if all_dates else None,
        "date_to": max(all_dates) if all_dates else None,
        "invalid_rows": parse_result.invalid_rows,
        "skipped_dates": skipped_dates,
    }
