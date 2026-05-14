CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS platforms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,   -- e.g. 'binance', 'okx'
    display_name TEXT NOT NULL          -- e.g. 'Binance', 'OKX'
);

CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    account_key TEXT NOT NULL,          -- e.g. 'account_main'
    label       TEXT,                   -- optional display label
    UNIQUE(platform_id, account_key)
);

CREATE TABLE IF NOT EXISTS batches (
    id          TEXT PRIMARY KEY,       -- UUID
    started_at  TEXT NOT NULL,          -- ISO8601
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running'  -- running | success | partial | failed
);

CREATE TABLE IF NOT EXISTS source_runs (
    id          TEXT PRIMARY KEY,       -- UUID
    batch_id    TEXT NOT NULL REFERENCES batches(id),
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',  -- running | success | failed
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw_payloads (
    id              TEXT PRIMARY KEY,   -- UUID
    source_run_id   TEXT NOT NULL REFERENCES source_runs(id),
    resource_type   TEXT NOT NULL,      -- e.g. 'spot', 'earn'
    file_path       TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    parser_status   TEXT NOT NULL DEFAULT 'pending'  -- pending | parsed | failed
);

CREATE TABLE IF NOT EXISTS normalized_holdings (
    id              TEXT PRIMARY KEY,   -- UUID
    source_run_id   TEXT NOT NULL REFERENCES source_runs(id),
    raw_payload_id  TEXT NOT NULL REFERENCES raw_payloads(id),
    platform_symbol TEXT NOT NULL,
    platform_asset_name TEXT,
    asset_type      TEXT NOT NULL,      -- cash | stock | etf | crypto | stablecoin | margin_loan | collateral | futures | option | unknown
    quantity        REAL NOT NULL,
    price           REAL,
    value           REAL,
    original_currency TEXT NOT NULL,
    price_source    TEXT,               -- 'platform' or null
    snapshot_date   TEXT NOT NULL,      -- YYYY-MM-DD
    parser_version  TEXT NOT NULL,
    chain           TEXT                -- e.g. 'ethereum', 'arbitrum' — NULL for non-EVM platforms
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id              TEXT PRIMARY KEY,   -- UUID
    batch_id        TEXT NOT NULL REFERENCES batches(id),
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    snapshot_date   TEXT NOT NULL,
    total_value     REAL,
    currency        TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(account_id, snapshot_date, batch_id)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              TEXT PRIMARY KEY,   -- UUID
    batch_id        TEXT NOT NULL REFERENCES batches(id),
    snapshot_date   TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category_snapshots (
    id              TEXT PRIMARY KEY,   -- UUID
    snapshot_date   TEXT NOT NULL,      -- YYYY-MM-DD
    category        TEXT NOT NULL,      -- crypto | tw_stock | us_stock
    total_value     REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    source          TEXT NOT NULL,      -- auto | manual
    batch_id        TEXT REFERENCES batches(id),  -- NULL for manual
    created_at      TEXT NOT NULL,
    UNIQUE(snapshot_date, category)
);
"""

SEED_PLATFORMS = """
INSERT OR IGNORE INTO platforms (name, display_name) VALUES
    ('binance', 'Binance'),
    ('okx', 'OKX'),
    ('mexc', 'MEXC'),
    ('bybit', 'Bybit'),
    ('yuanta', '元大證券'),
    ('firsttrade', 'FirstTrade'),
    ('sui_wallet', 'SUI Wallet'),
    ('evm_wallet', 'EVM Wallet'),
    ('sol_wallet', 'Solana Wallet'),
    ('ibkr', 'IBKR'),
    ('sinopac', '永豐證券');
"""

SEED_ACCOUNTS = """
INSERT OR IGNORE INTO accounts (platform_id, account_key, label)
SELECT id, 'account_main', 'Main Account' FROM platforms WHERE name IN ('binance', 'okx', 'mexc', 'bybit', 'yuanta', 'firsttrade', 'ibkr');
"""
