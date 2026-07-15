"""add cancel_at_period_end to subscriptions

Revision ID: 014
Revises: 013
Create Date: 2026-07-14

ECPay's CreditCardPeriodAction Cancel terminates future charges only — the
already-paid period stays usable. Keep status='active' and flag the pending
cancellation here so the UI can show "已排程取消"; the entitlement lapses
naturally when current_period_end passes. Provider-neutral: Stripe's
cancel_at_period_end maps to the same flag.
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscriptions "
        "ADD COLUMN cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN cancel_at_period_end")
