"""seed hyperliquid platform

Revision ID: 016
Revises: 015
Create Date: 2026-08-04
"""
from alembic import op


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platforms (name, display_name) VALUES
            ('hyperliquid', 'Hyperliquid')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platforms WHERE name = 'hyperliquid'")
