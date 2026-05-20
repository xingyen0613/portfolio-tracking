"""Yuanta backfill — replay one user's months from existing raw_payloads.

When connector logic changes (e.g. anchor calibration, per-category labels) we
need to regenerate downstream tables (account_snapshots / normalized_holdings)
without re-downloading PDFs from Gmail. This script reads the already-stored
parsed.json from `raw_payloads.payload_json` and re-runs the post-parse
pipeline.

What it does:
  1. Delete the user's existing yuanta account_snapshots + normalized_holdings
     (keeps raw_payloads, source_runs, accounts, user_connectors intact)
  2. For each month's raw_payload in chronological order, re-run
     reconstruct → fetch prices → _write_month_to_db
  3. cum_cash chains across months (anchor correction propagates)

Usage:
    uv run python scripts/yuanta_backfill_from_db.py \\
        --user-id aab8170a-45eb-4099-b204-04fd4c587cc1 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from app.connectors.yuanta_connector import (
    _collect_symbols,
    _extract_other_assets,
    _extract_pledged_stocks,
    _write_month_to_db,
    _now,
)
from config.db import get_conn


def _platform_id(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM platforms WHERE name=%s", (name,)).fetchone()
    if not row:
        raise SystemExit(f"platform {name} not found")
    return row["id"]


def _yuanta_account(conn, user_id: str) -> dict | None:
    pid = _platform_id(conn, "yuanta")
    row = conn.execute(
        "SELECT id, account_key FROM accounts WHERE user_id=%s AND platform_id=%s",
        (user_id, pid),
    ).fetchone()
    return dict(row) if row else None


def _load_raw_payloads(conn, user_id: str, account_id: int) -> list[dict]:
    """Return chronologically ordered raw_payloads for this user's yuanta account."""
    rows = conn.execute(
        """SELECT rp.id, rp.source_run_id, rp.file_path, rp.payload_json
           FROM raw_payloads rp
           JOIN source_runs sr ON sr.id = rp.source_run_id
           WHERE rp.user_id = %s AND sr.account_id = %s
             AND rp.resource_type = 'yuanta_parsed_statement'
           ORDER BY rp.file_path ASC""",
        (user_id, account_id),
    ).fetchall()
    out = []
    for r in rows:
        pj = r["payload_json"]
        if isinstance(pj, str):
            pj = json.loads(pj)
        out.append({
            "raw_payload_id": r["id"],
            "source_run_id": r["source_run_id"],
            "file_path": r["file_path"],
            "parsed": pj,
        })
    return out


def _delete_derived(conn, user_id: str, account_id: int) -> tuple[int, int]:
    """Delete account_snapshots + normalized_holdings for this user's yuanta account.

    Returns (snapshots_deleted, holdings_deleted).
    """
    sn = conn.execute(
        "DELETE FROM account_snapshots WHERE account_id=%s AND user_id=%s",
        (account_id, user_id),
    )
    nh = conn.execute(
        """DELETE FROM normalized_holdings
           WHERE user_id=%s AND source_run_id IN (
             SELECT id FROM source_runs WHERE account_id=%s
           )""",
        (user_id, account_id),
    )
    return sn.rowcount, nh.rowcount


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview deletions and replay plan without writing")
    args = ap.parse_args()

    from yuanta_daily_reconstruct_poc import (
        build_daily_entries, compute_anchor, reconstruct_shares,
    )
    from yuanta_price_fetch_poc import fetch_month as _fetch_prices

    # Phase 1: read-only inspect
    with get_conn() as conn:
        acc = _yuanta_account(conn, args.user_id)
        if not acc:
            print(f"No yuanta account for user {args.user_id}", file=sys.stderr)
            return 1
        account_id = acc["id"]
        payloads = _load_raw_payloads(conn, args.user_id, account_id)
        if not payloads:
            print(f"No yuanta raw_payloads for user {args.user_id}", file=sys.stderr)
            return 1

        print(f"User: {args.user_id}")
        print(f"Yuanta account: id={account_id}, key={acc['account_key']}")
        print(f"Found {len(payloads)} raw_payloads:")
        for p in payloads:
            print(f"  {p['file_path']}  raw_payload_id={p['raw_payload_id']}")

        sn_cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM account_snapshots WHERE account_id=%s AND user_id=%s",
            (account_id, args.user_id),
        ).fetchone()["c"]
        nh_cnt = conn.execute(
            """SELECT COUNT(*) AS c FROM normalized_holdings
               WHERE user_id=%s AND source_run_id IN (
                 SELECT id FROM source_runs WHERE account_id=%s
               )""",
            (args.user_id, account_id),
        ).fetchone()["c"]
        print(f"\nWill delete: {sn_cnt} account_snapshots, {nh_cnt} normalized_holdings")

    if args.dry_run:
        print("(dry-run) — not writing")
        return 0

    # Phase 2: delete + create batch (own commit)
    batch_id = str(uuid.uuid4())
    with get_conn() as conn:
        sn_del, nh_del = _delete_derived(conn, args.user_id, account_id)
        print(f"Deleted: {sn_del} account_snapshots, {nh_del} normalized_holdings")
        conn.execute(
            "INSERT INTO batches (id, started_at, status, user_id) VALUES (%s,%s,%s,%s)",
            (batch_id, _now(), "running", args.user_id),
        )

    # Phase 3: replay months — _write_month_to_db opens its own connection
    cum_cash = Decimal(0)
    total_snapshots = 0
    for p in payloads:
        month = Path(p["file_path"]).parent.name  # "yuanta/2026-04/parsed.json" -> "2026-04"
        parsed = p["parsed"]
        print(f"\n=== Replaying {month} ===")

        anchor_holdings, anchor_margin = compute_anchor(parsed, None)
        shares_series = reconstruct_shares(parsed, anchor_holdings)
        daily_entries = build_daily_entries(
            parsed, shares_series, anchor_holdings, anchor_margin
        )

        other_assets = _extract_other_assets(parsed)
        pledged_stocks = _extract_pledged_stocks(parsed)
        collateral_value = Decimal(
            str(parsed.get("summary", {}).get("collateral_total_value", 0) or 0)
            .replace(",", "")
        )
        official_raw = parsed.get("summary", {}).get("net_asset")
        official_net_asset = (
            Decimal(str(official_raw).replace(",", ""))
            if official_raw not in (None, "")
            else None
        )

        symbols = _collect_symbols(daily_entries)
        symbols = sorted(set(symbols) | {ps["symbol"] for ps in pledged_stocks})
        price_doc = _fetch_prices(month, symbols)
        prices_by_date = price_doc.get("prices", {})

        n, cum_cash = _write_month_to_db(
            month, daily_entries, prices_by_date, other_assets,
            pledged_stocks, collateral_value, official_net_asset,
            batch_id, p["source_run_id"], p["raw_payload_id"],
            account_id, args.user_id, cum_cash,
        )
        total_snapshots += n
        print(f"  wrote {n} snapshots, end_cum_cash={cum_cash}")

    with get_conn() as conn:
        conn.execute(
            "UPDATE batches SET status='success', finished_at=%s WHERE id=%s",
            (_now(), batch_id),
        )
    print(f"\nDone. Total snapshots written: {total_snapshots}")
    print(f"Batch id: {batch_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
