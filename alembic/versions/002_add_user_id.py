"""add user_id for multi-tenancy

Revision ID: 002
Revises: 001
Create Date: 2026-05-05
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            email      TEXT UNIQUE,
            google_id  TEXT UNIQUE,
            name       TEXT,
            is_system  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connectors (
            id                TEXT PRIMARY KEY,
            user_id           TEXT NOT NULL REFERENCES users(id),
            platform_name     TEXT NOT NULL,
            account_key       TEXT NOT NULL,
            label             TEXT,
            credentials_json  TEXT,
            status            TEXT NOT NULL DEFAULT 'active',
            last_sync_at      TEXT,
            created_at        TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(user_id, platform_name, account_key)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(id),
            plan               TEXT NOT NULL DEFAULT 'free',
            status             TEXT NOT NULL DEFAULT 'active',
            stripe_customer_id TEXT,
            expires_at         TEXT,
            created_at         TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
    """)

    for table in ["batches", "accounts", "source_runs", "raw_payloads",
                  "normalized_holdings", "account_snapshots", "category_snapshots"]:
        op.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT REFERENCES users(id)")

    # Update UNIQUE constraints to include user_id
    op.execute("ALTER TABLE category_snapshots DROP CONSTRAINT category_snapshots_snapshot_date_category_key")
    op.execute("ALTER TABLE category_snapshots ADD CONSTRAINT category_snapshots_unique UNIQUE(snapshot_date, category, user_id)")

    op.execute("ALTER TABLE accounts DROP CONSTRAINT accounts_platform_id_account_key_key")
    op.execute("ALTER TABLE accounts ADD CONSTRAINT accounts_unique UNIQUE(platform_id, account_key, user_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_unique")
    op.execute("ALTER TABLE accounts ADD CONSTRAINT accounts_platform_id_account_key_key UNIQUE(platform_id, account_key)")

    op.execute("ALTER TABLE category_snapshots DROP CONSTRAINT IF EXISTS category_snapshots_unique")
    op.execute("ALTER TABLE category_snapshots ADD CONSTRAINT category_snapshots_snapshot_date_category_key UNIQUE(snapshot_date, category)")

    for table in ["batches", "accounts", "source_runs", "raw_payloads",
                  "normalized_holdings", "account_snapshots", "category_snapshots"]:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS user_id")

    for table in ["subscriptions", "user_connectors", "users"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
