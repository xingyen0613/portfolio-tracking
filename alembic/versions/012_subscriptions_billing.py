"""reshape subscriptions table for provider-neutral billing

Revision ID: 012
Revises: 011
Create Date: 2026-07-12

The original `subscriptions` table (created empty in 002, never referenced by any
code) used a Stripe-specific shape. Reshape it into a provider-neutral entitlement
record so PayPal / future providers / comp whitelist all write the same `status`.
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old table is an unused empty stub — safe to drop and recreate cleanly.
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("""
        CREATE TABLE subscriptions (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(id),
            provider           TEXT NOT NULL,            -- 'paypal' | 'comp' | 'stripe' | ...
            external_id        TEXT,                     -- PayPal subscription id; NULL for comp
            status             TEXT NOT NULL DEFAULT 'none',  -- active|trialing|past_due|canceled|none
            current_period_end TEXT,                     -- ISO8601; NULL = no expiry (comp)
            created_at         TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at         TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(user_id)
        )
    """)


def downgrade() -> None:
    # Restore the original Stripe-shaped stub from migration 002.
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("""
        CREATE TABLE subscriptions (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(id),
            plan               TEXT NOT NULL DEFAULT 'free',
            status             TEXT NOT NULL DEFAULT 'active',
            stripe_customer_id TEXT,
            expires_at         TEXT,
            created_at         TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
    """)
