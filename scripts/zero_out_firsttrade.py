"""
將 Firsttrade 持倉歸零：插入一筆 2026-04-28 的空倉快照。
執行方式：uv run python scripts/zero_out_firsttrade.py
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sqlite" / "portfolio.db"
SNAPSHOT_DATE = "2026-04-28"
TIMESTAMP = f"{SNAPSHOT_DATE}T15:00:00.000000+00:00"
FIRSTTRADE_ACCOUNT_ID = 2  # 從 DB 確認

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 確認目前 Firsttrade 最新快照日期
current = conn.execute("""
    SELECT MAX(nh.snapshot_date) as latest
    FROM normalized_holdings nh
    JOIN source_runs sr ON nh.source_run_id = sr.id
    WHERE sr.account_id = ?
""", (FIRSTTRADE_ACCOUNT_ID,)).fetchone()["latest"]
print(f"目前 Firsttrade 最新快照：{current}")
print(f"即將插入歸零快照：{SNAPSHOT_DATE}")

batch_id    = str(uuid.uuid4())
sr_id       = str(uuid.uuid4())
payload_id  = str(uuid.uuid4())
holding_id  = str(uuid.uuid4())

with conn:
    # 1. batch
    conn.execute("""
        INSERT INTO batches (id, started_at, finished_at, status)
        VALUES (?, ?, ?, 'success')
    """, (batch_id, TIMESTAMP, TIMESTAMP))

    # 2. source_run
    conn.execute("""
        INSERT INTO source_runs (id, batch_id, account_id, started_at, finished_at, status)
        VALUES (?, ?, ?, ?, ?, 'success')
    """, (sr_id, batch_id, FIRSTTRADE_ACCOUNT_ID, TIMESTAMP, TIMESTAMP))

    # 3. raw_payload（佔位，代表「這次查帳，帳戶是空的」）
    conn.execute("""
        INSERT INTO raw_payloads (id, source_run_id, resource_type, file_path, payload_hash, fetched_at, parser_status)
        VALUES (?, ?, 'manual', 'manual/firsttrade_zero_2026-04-28', 'zero', ?, 'parsed')
    """, (payload_id, sr_id, TIMESTAMP))

    # 4. normalized_holdings — 一筆 value=0 的現金佔位行（讓查詢能識別這是最新快照）
    conn.execute("""
        INSERT INTO normalized_holdings
            (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
             asset_type, quantity, price, value, original_currency, price_source,
             snapshot_date, parser_version)
        VALUES (?, ?, ?, 'CASH', 'Cash (liquidated)', 'cash', 0.0, 1.0, 0.0, 'USD', 'manual', ?, '1.0.0')
    """, (holding_id, sr_id, payload_id, SNAPSHOT_DATE))

print("✅ 插入完成")

# 驗證
row = conn.execute("""
    SELECT nh.snapshot_date, nh.platform_symbol, nh.value
    FROM normalized_holdings nh
    JOIN source_runs sr ON nh.source_run_id = sr.id
    WHERE sr.account_id = ?
    ORDER BY nh.snapshot_date DESC LIMIT 1
""", (FIRSTTRADE_ACCOUNT_ID,)).fetchone()
print(f"驗證最新快照：{dict(row)}")

conn.close()
