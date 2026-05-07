"""user_connectors health: add last_error fields

Revision ID: 006
Revises: 005
Create Date: 2026-05-07
"""
from alembic import op


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_connectors ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute("ALTER TABLE user_connectors ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE user_connectors DROP COLUMN IF EXISTS last_error")
    op.execute("ALTER TABLE user_connectors DROP COLUMN IF EXISTS last_error_at")
