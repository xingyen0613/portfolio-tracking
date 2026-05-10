"""normalized_holdings: add resource_type for sub-account display

Revision ID: 007
Revises: 006
Create Date: 2026-05-10
"""
from alembic import op


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE normalized_holdings ADD COLUMN IF NOT EXISTS resource_type TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE normalized_holdings DROP COLUMN IF EXISTS resource_type")
