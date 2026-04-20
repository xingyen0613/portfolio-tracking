"""
Yuanta monthly pipeline orchestrator.

Determines the target month (default: last month), checks each step's
checkpoint file, and runs only the steps that haven't completed yet.

Usage:
  uv run python scripts/yuanta_run_pipeline.py
  uv run python scripts/yuanta_run_pipeline.py --month 2026-04
  uv run python scripts/yuanta_run_pipeline.py --force
  uv run python scripts/yuanta_run_pipeline.py --dry-run
"""

import argparse
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from calendar import monthrange

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR      = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"
DERIVED_DIR  = PROJECT_ROOT / "data" / "derived" / "yuanta_poc"
DB_PATH      = PROJECT_ROOT / "data" / "sqlite" / "portfolio.db"
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"

YUANTA_ACCOUNT_ID = 4


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _last_month() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def _months_between(start: str, end: str) -> list[str]:
    """Return list of YYYY-MM strings from start to end inclusive."""
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _earliest_local_month() -> str | None:
    """Return the earliest month that has a PDF or derived data locally."""
    candidates = sorted(
        p.name for p in RAW_DIR.glob("????-??") if p.is_dir()
    ) + sorted(
        p.name for p in DERIVED_DIR.glob("????-??") if p.is_dir()
    )
    return candidates[0] if candidates else None


def _target_months(month_arg: str | None) -> list[str]:
    """Return ordered list of months to process."""
    last = _last_month()
    if month_arg:
        return [month_arg]
    # Auto: find all months from earliest local data to last month
    earliest = _earliest_local_month()
    if not earliest:
        return [last]
    return _months_between(earliest, last)


def _pdf_exists(month: str) -> bool:
    return (RAW_DIR / month / "yuanta_statement.pdf").exists()


def _parsed_exists(month: str) -> bool:
    return (RAW_DIR / month / "parsed.json").exists()


def _holdings_exists(month: str) -> bool:
    return (DERIVED_DIR / month / "daily_holdings.json").exists()


def _prices_exists(month: str) -> bool:
    return (DERIVED_DIR / "prices" / f"{month}.json").exists()


def _net_asset_exists(month: str) -> bool:
    return (DERIVED_DIR / month / "daily_net_asset.json").exists()


def _in_db(month: str) -> bool:
    if not DB_PATH.exists():
        return False
    with sqlite3.connect(DB_PATH) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM account_snapshots "
            "WHERE account_id = ? AND snapshot_date LIKE ? AND total_value IS NOT NULL",
            (YUANTA_ACCOUNT_ID, f"{month}-%"),
        ).fetchone()[0]
    return count > 0


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _uv(script: str) -> list[str]:
    return ["uv", "run", "python", str(SCRIPTS_DIR / script)]


def _run_step(label: str, cmd: list[str], dry_run: bool) -> None:
    cmd_str = " ".join(str(c) for c in cmd)
    print(f"  → [{label}] {cmd_str}", file=sys.stderr)
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"  ✗ [{label}] failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"  ✓ [{label}] done", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Yuanta monthly pipeline orchestrator")
    parser.add_argument("--month",   help="Target month, e.g. 2026-04 (default: last month)")
    parser.add_argument("--force",   action="store_true", help="Ignore checkpoints, re-run all steps")
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    args = parser.parse_args()

    force   = args.force
    dry_run = args.dry_run
    months  = _target_months(args.month)

    suffix = (" [DRY RUN]" if dry_run else "") + (" [FORCE]" if force else "")
    print(f"# yuanta pipeline — {len(months)} month(s): {months[0]} ~ {months[-1]}{suffix}", file=sys.stderr)

    any_work = False
    for month in months:
        # Fast-path: already done
        if not force and _net_asset_exists(month) and _in_db(month):
            print(f"  [skip] {month} already up to date", file=sys.stderr)
            continue

        print(f"\n# --- {month} ---", file=sys.stderr)
        any_work = True

        steps = [
            (
                "gmail",
                not force and _pdf_exists(month),
                _uv("yuanta_gmail_poc.py") + ["--fetch", "--month", month],
            ),
            (
                "pdf_parse",
                not force and _parsed_exists(month),
                _uv("yuanta_pdf_parse_poc.py") + [
                    "--pdf", str(RAW_DIR / month / "yuanta_statement.pdf"),
                    "--parse",
                ],
            ),
            (
                "reconstruct",
                not force and _holdings_exists(month),
                _uv("yuanta_daily_reconstruct_poc.py") + ["--month", month],
            ),
            (
                "price_fetch",
                not force and _prices_exists(month),
                _uv("yuanta_price_fetch_poc.py") + ["--month", month],
            ),
            (
                "net_asset",
                not force and _net_asset_exists(month),
                _uv("yuanta_net_asset_poc.py") + ["--month", month],
            ),
            (
                "insert",
                not force and _in_db(month),
                _uv("yuanta_insert_poc.py") + ["--month", month],
            ),
        ]

        for label, skip, cmd in steps:
            if skip:
                print(f"  [skip] {label}", file=sys.stderr)
            else:
                _run_step(label, cmd, dry_run)

    if not any_work:
        print(f"\n# all months up to date — nothing to do", file=sys.stderr)
    else:
        print(f"\n# done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
