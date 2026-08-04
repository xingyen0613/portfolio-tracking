"""seed manual platform

Revision ID: 017
Revises: 016
Create Date: 2026-08-04
"""
from alembic import op


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platforms (name, display_name) VALUES
            ('manual', '手動輸入')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platforms WHERE name = 'manual'")
