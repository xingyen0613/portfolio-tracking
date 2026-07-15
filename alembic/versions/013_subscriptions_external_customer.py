"""add external_customer_id to subscriptions

Revision ID: 013
Revises: 012
Create Date: 2026-07-13

Stripe's Customer Portal needs the provider-side customer id (cus_...), which is
distinct from the subscription id already stored in external_id. Kept provider-
neutral: any future provider with a customer-level object writes it here too.
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE subscriptions ADD COLUMN external_customer_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN external_customer_id")
