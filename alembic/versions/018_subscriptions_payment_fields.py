"""add payment tracking fields to subscriptions

Revision ID: 018
Revises: 017
Create Date: 2026-08-13

The subscriptions row records only *current* state (status, period end), which
drops three facts we cannot reconstruct later:

- `amount`: the monthly price a subscriber is locked into. It only ever exists
  in ECPAY_PERIOD_AMOUNT at checkout time, so after a price change there is no
  record of what existing subscribers actually pay. Required for
  grandfathering (old subscribers keep the old price).
- `last_payment_at`: the last successful charge. Previously only inferrable by
  subtracting a month from current_period_end, which goes wrong on failed
  charges and retries.
- `started_at`: when the *current* subscription run began. It tracks
  external_id, so cancel-then-resubscribe (a new ECPay order) restarts it while
  monthly renewals of the same order leave it untouched. created_at cannot
  serve this purpose: it survives a comp → ecpay switch and so can predate the
  first payment.

All three are nullable: comp subscriptions have none of them, and rows created
before this migration have no way to backfill from the callbacks they missed.
"""
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE subscriptions ADD COLUMN amount INTEGER")
    op.execute("ALTER TABLE subscriptions ADD COLUMN last_payment_at TEXT")
    op.execute("ALTER TABLE subscriptions ADD COLUMN started_at TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN started_at")
    op.execute("ALTER TABLE subscriptions DROP COLUMN last_payment_at")
    op.execute("ALTER TABLE subscriptions DROP COLUMN amount")
