"""seed fubon platform

Revision ID: 015
Revises: 014
Create Date: 2026-07-15
"""
from alembic import op


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platforms (name, display_name) VALUES
            ('fubon', '富邦證券')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platforms WHERE name = 'fubon'")
