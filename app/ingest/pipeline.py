import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PARSER_VERSION, RAW_DIR as _DEFAULT_RAW_DIR
from config.db import get_conn
from app.storage.sqlite import get_account_id


def _raw_dir() -> Path:
    custom = os.environ.get("RAW_DATA_DIR")
    return Path(custom) if custom else _DEFAULT_RAW_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _store_raw_file(batch_id: str, platform: str, account_key: str,
                    resource_type: str, payload: dict, fetched_at: str) -> tuple[str, str]:
    """Write raw payload to filesystem. Returns (file_path, payload_hash)."""
    date_str = fetched_at[:10]  # YYYY-MM-DD
    ts = fetched_at.replace(":", "").replace("-", "").replace("+", "Z")[:15]
    dir_path = _raw_dir() / date_str / f"batch_{batch_id[:8]}" / platform / account_key
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{resource_type}_{ts}.json"

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    file_path.write_text(content, encoding="utf-8")

    payload_hash = hashlib.sha256(content.encode()).hexdigest()
    return str(file_path), payload_hash


def run_source_pipeline(connector, batch_id: str, user_id: str):
    from app.connectors.base import RunResult

    platform = connector.platform_name
    account_key = connector.account_key
    source_run_id = str(uuid.uuid4())
    started_at = _now()
    snapshot_date = _snapshot_date()

    try:
        account_id = get_account_id(platform, account_key, user_id)
    except ValueError as e:
        return RunResult(source_run_id, platform, account_key, "failed", str(e))

    # Create source_run record
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO source_runs (id, batch_id, account_id, started_at, status, user_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (source_run_id, batch_id, account_id, started_at, "running", user_id),
        )

    try:
        connector.authenticate()
        raw_items = connector.fetch_raw()

        raw_payload_ids = []
        for item in raw_items:
            resource_type = item["resource_type"]
            payload = item["payload"]
            fetched_at = item.get("fetched_at", _now())

            file_path, payload_hash = _store_raw_file(
                batch_id, platform, account_key, resource_type, payload, fetched_at
            )

            raw_payload_id = str(uuid.uuid4())
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO raw_payloads
                       (id, source_run_id, resource_type, file_path, payload_hash, fetched_at, parser_status, payload_json, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (raw_payload_id, source_run_id, resource_type,
                     file_path, payload_hash, fetched_at, "pending",
                     json.dumps(payload), user_id),
                )
            raw_payload_ids.append((raw_payload_id, item))

        # Parse holdings
        holdings = connector.parse_holdings(raw_items)

        # Fetch market prices (only for connectors that opt in, only fills missing prices)
        if getattr(connector, "use_pricer", True):
            from app.valuation.pricer import fetch_prices
            symbols = list({h["platform_symbol"] for h in holdings if h.get("price") is None})
            if symbols:
                prices = fetch_prices(symbols)
                for h in holdings:
                    if h.get("price") is not None:
                        continue  # preserve prices already set by connector (e.g. BlockVision)
                    sym = h["platform_symbol"]
                    p = prices.get(sym)
                    if p is not None:
                        h["price"] = p
                        h["value"] = round(h["quantity"] * p, 8)
                        h["price_source"] = "market"

        total_value = None
        currency = None

        with get_conn() as conn:
            for h in holdings:
                conn.execute(
                    """INSERT INTO normalized_holdings
                       (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                        asset_type, quantity, price, value, original_currency,
                        price_source, snapshot_date, parser_version, chain, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        str(uuid.uuid4()), source_run_id,
                        raw_payload_ids[0][0],  # link to first raw payload
                        h["platform_symbol"],
                        h.get("platform_asset_name"),
                        h["asset_type"],
                        h["quantity"],
                        h.get("price"),
                        h.get("value"),
                        h["original_currency"],
                        h.get("price_source"),
                        snapshot_date,
                        PARSER_VERSION,
                        h.get("chain"),
                        user_id,
                    ),
                )

            # Mark raw payloads as parsed
            conn.execute(
                "UPDATE raw_payloads SET parser_status='parsed' WHERE source_run_id=%s",
                (source_run_id,),
            )

            # Account snapshot
            if holdings:
                currency = holdings[0]["original_currency"]
                values = [h.get("value") for h in holdings if h.get("value") is not None]
                total_value = sum(values) if values else None

            conn.execute(
                """INSERT INTO account_snapshots
                   (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, snapshot_date, batch_id) DO UPDATE SET
                     total_value=EXCLUDED.total_value,
                     currency=EXCLUDED.currency,
                     created_at=EXCLUDED.created_at""",
                (str(uuid.uuid4()), batch_id, account_id,
                 snapshot_date, total_value, currency, _now(), user_id),
            )

        # Mark source_run success
        with get_conn() as conn:
            conn.execute(
                "UPDATE source_runs SET status='success', finished_at=%s WHERE id=%s",
                (_now(), source_run_id),
            )

        return RunResult(source_run_id, platform, account_key, "success")

    except Exception as e:
        with get_conn() as conn:
            conn.execute(
                "UPDATE source_runs SET status='failed', finished_at=%s, error_message=%s WHERE id=%s",
                (_now(), str(e), source_run_id),
            )
        return RunResult(source_run_id, platform, account_key, "failed", str(e))
