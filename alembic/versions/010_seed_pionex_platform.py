"""seed pionex platform

Revision ID: 010
Revises: 009
Create Date: 2026-06-09
"""
from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platforms (name, display_name) VALUES
            ('pionex', '派網')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platforms WHERE name = 'pionex'")
