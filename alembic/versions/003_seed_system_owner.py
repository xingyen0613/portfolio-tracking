"""seed system owner and backfill user_id

Revision ID: 003
Revises: 002
Create Date: 2026-05-05
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

SYSTEM_OWNER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO users (id, email, name, is_system, created_at)
        VALUES ('{SYSTEM_OWNER_ID}', 'system@portfolio.internal', 'System Owner', TRUE, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO NOTHING
    """)

    for table in ["batches", "accounts", "source_runs", "raw_payloads",
                  "normalized_holdings", "account_snapshots", "category_snapshots"]:
        op.execute(f"UPDATE {table} SET user_id = '{SYSTEM_OWNER_ID}'")

    for table in ["batches", "accounts", "source_runs", "raw_payloads",
                  "normalized_holdings", "account_snapshots", "category_snapshots"]:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")


def downgrade() -> None:
    for table in ["batches", "accounts", "source_runs", "raw_payloads",
                  "normalized_holdings", "account_snapshots", "category_snapshots"]:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN user_id DROP NOT NULL")
        op.execute(f"UPDATE {table} SET user_id = NULL")

    op.execute(f"DELETE FROM users WHERE id = '{SYSTEM_OWNER_ID}'")
