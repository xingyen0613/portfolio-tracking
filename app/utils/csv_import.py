"""CSV parser for historical portfolio data imports.

Accepted CSV format:
  date,total_value
  2024-01-01,50000
  2024-01-02,51200.50

Date formats: YYYY-MM-DD or YYYY/MM/DD (normalized to YYYY-MM-DD).
Extra columns are ignored. Blank lines and lines starting with # are skipped.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date as Date

MAX_ROWS = 5000


@dataclass
class ParseResult:
    rows: list[dict]         # [{date: str, total_value: float}]
    invalid_rows: list[dict] # [{row_num: int, reason: str}]


def parse_csv(file_bytes: bytes) -> ParseResult:
    """Parse CSV bytes, returning valid rows and a list of parsing errors."""
    rows: list[dict] = []
    invalid_rows: list[dict] = []

    try:
        text = file_bytes.decode("utf-8-sig")  # strip UTF-8 BOM if present
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return ParseResult(
            rows=[],
            invalid_rows=[{"row_num": 0, "reason": "Empty file or missing header row"}],
        )

    # Case-insensitive header lookup
    normalized = {k.strip().lower(): k for k in reader.fieldnames if k}
    date_col = normalized.get("date")
    value_col = normalized.get("total_value") or normalized.get("value")

    if not date_col:
        return ParseResult(
            rows=[],
            invalid_rows=[{"row_num": 0, "reason": "Missing 'date' column"}],
        )
    if not value_col:
        return ParseResult(
            rows=[],
            invalid_rows=[{"row_num": 0, "reason": "Missing 'total_value' column"}],
        )

    row_num = 1  # header is row 1
    for raw_row in reader:
        row_num += 1

        if len(rows) >= MAX_ROWS:
            invalid_rows.append({
                "row_num": row_num,
                "reason": f"Exceeded maximum of {MAX_ROWS} rows; remaining rows ignored",
            })
            break

        date_raw = (raw_row.get(date_col) or "").strip()
        value_raw = (raw_row.get(value_col) or "").strip()

        # Skip blank lines and comments
        if not date_raw and not value_raw:
            continue
        if date_raw.startswith("#"):
            continue

        # Normalize and validate date
        date_str = date_raw.replace("/", "-")
        try:
            parsed = Date.fromisoformat(date_str)
            date_str = parsed.isoformat()
        except ValueError:
            invalid_rows.append({"row_num": row_num, "reason": f"Invalid date: '{date_raw}'"})
            continue

        # Validate numeric value
        try:
            total_value = float(value_raw.replace(",", ""))
        except (ValueError, AttributeError):
            invalid_rows.append({
                "row_num": row_num,
                "reason": f"Invalid total_value: '{value_raw}'",
            })
            continue

        rows.append({"date": date_str, "total_value": total_value})

    return ParseResult(rows=rows, invalid_rows=invalid_rows)
