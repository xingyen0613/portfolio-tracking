"""add price_cache table

Revision ID: 011
Revises: 010
Create Date: 2026-06-14
"""
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS price_cache (
            symbol      TEXT NOT NULL,
            price_date  DATE NOT NULL,
            price       REAL NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'USD',
            source      TEXT NOT NULL,
            fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (symbol, price_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_price_cache_date ON price_cache (price_date)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_price_cache_date")
    op.execute("DROP TABLE IF EXISTS price_cache")
